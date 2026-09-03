#!/usr/bin/env python
"""Incremental ingestion for the cricket article database.

    python ingest.py seed --csv articles_full.csv
        One-time bulk import of the existing scraped corpus into articles.db.

    python ingest.py scrape --pages 5
        Fetch the newest N listing pages from ESPNcricinfo and insert only
        articles not already in the database.

    python ingest.py backfill-metadata
        Re-parse `url` for every existing row into content_type/series_id/
        series_slug/match_id. Safe to rerun.

    python ingest.py backfill-entities
        Mine a player-name gazetteer from the whole corpus (spaCy PERSON
        NER, run once) and (re)extract player/team entities for every
        article using it. Safe to rerun; overwrites player_gazetteer.json
        and each article's stored entities.

All commands are safe to rerun (dedup happens on `url`).
"""
import argparse
from datetime import datetime, timezone

import pandas as pd
import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer

import db
import entities
import metadata

LISTING_URL = "https://www.espncricinfo.com/ci/content/story/news.html"
BASE_URL = "https://www.espncricinfo.com"

_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed(texts):
    return get_model().encode(texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True)


def scrape_page(soup):
    articles = []
    titles, urls, summaries, dates = [], [], [], []

    for el in soup.find_all("h2", class_="ds-text-title-s ds-font-bold ds-text-typo"):
        titles.append(el.text.strip())
        link_tag = el.find_parent("a")
        urls.append(BASE_URL + link_tag["href"] if link_tag else "")

    for el in soup.find_all("p", class_="ds-text-compact-s ds-text-typo-mid2 ds-mt-1"):
        summaries.append(el.text.strip())

    for el in soup.find_all("div", class_="ds-leading-[0] ds-text-typo-mid3 ds-mt-1"):
        dates.append(el.text.strip().split("•")[0])

    for title, url, summary, date in zip(titles, urls, summaries, dates):
        articles.append({"title": title, "url": url, "summary": summary, "date": date})
    return articles


def fetch_pages(num_pages):
    articles = []
    for page_num in range(1, num_pages + 1):
        response = requests.get(f"{LISTING_URL}?page={page_num}")
        soup = BeautifulSoup(response.content, "html.parser")
        page_articles = scrape_page(soup)
        if not page_articles:
            break
        articles.extend(page_articles)
    return articles


def resolve_metadata(conn, records):
    """Parses url metadata for each record, resolving `story` articles'
    series_slug against the vocabulary of known `/series/` slugs (including
    ones discovered earlier in this same batch)."""
    parsed = [metadata.parse_url(r["url"]) for r in records]
    vocabulary = set(db.all_series_slugs(conn))
    vocabulary.update(raw_slug for content_type, _, raw_slug, _ in parsed if content_type == "match" and raw_slug)
    vocabulary = metadata.build_series_vocabulary(vocabulary)

    resolved = []
    for content_type, series_id, raw_slug, match_id in parsed:
        if content_type == "match":
            series_slug = raw_slug
        else:
            series_slug = metadata.guess_series_slug(raw_slug, vocabulary) if raw_slug else None
        resolved.append((content_type, series_id, series_slug, match_id))
    return resolved


def extract_entities_for(conn, article_id, title, summary, player_pattern, surname_to_full_name):
    text = f"{title}. {summary}"
    pairs = [("team", t) for t in entities.extract_teams(text)]
    pairs += [("player", p) for p in entities.extract_players(text, player_pattern, surname_to_full_name)]
    db.replace_entities(conn, article_id, pairs)


def insert_new_articles(conn, records):
    """records: iterable of dicts with title/url/summary/date. Returns count inserted."""
    new_records = [r for r in records if not db.article_exists(conn, r["url"])]
    if not new_records:
        return 0

    texts = [f"{r['title']}. {r['summary']}" for r in new_records]
    embeddings = embed(texts)
    metas = resolve_metadata(conn, new_records)

    gazetteer = entities.load_gazetteer()
    player_pattern = entities.build_player_pattern(gazetteer)
    surname_to_full_name = entities.surname_lookup(gazetteer)

    inserted = 0
    scraped_at = datetime.now(timezone.utc).isoformat()
    for record, embedding, (content_type, series_id, series_slug, match_id) in zip(new_records, embeddings, metas):
        article_id = db.insert_article(
            conn,
            title=record["title"],
            url=record["url"],
            summary=record["summary"],
            published_date=record["date"],
            scraped_at=scraped_at,
            embedding=embedding,
            content_type=content_type,
            series_id=series_id,
            series_slug=series_slug,
            match_id=match_id,
        )
        if article_id is not None:
            inserted += 1
            extract_entities_for(conn, article_id, record["title"], record["summary"], player_pattern, surname_to_full_name)
    conn.commit()
    return inserted


def cmd_seed(args):
    df = pd.read_csv(args.csv).dropna(subset=["title", "link"]).fillna("")
    records = df.rename(columns={"link": "url", "date": "date"}).to_dict("records")
    records = [{"title": r["title"], "url": r["url"], "summary": r["summary"], "date": r["date"]} for r in records]

    db.init_db()
    with db.connect() as conn:
        total_inserted = 0
        batch_size = 256
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            inserted = insert_new_articles(conn, batch)
            total_inserted += inserted
            print(f"[{i + len(batch)}/{len(records)}] inserted {inserted} (total {total_inserted})")
    print(f"Done. Inserted {total_inserted} new articles out of {len(records)}.")


def cmd_scrape(args):
    db.init_db()
    articles = fetch_pages(args.pages)
    print(f"Scraped {len(articles)} article listings from {args.pages} page(s).")
    with db.connect() as conn:
        inserted = insert_new_articles(conn, articles)
    print(f"Inserted {inserted} new articles ({len(articles) - inserted} already existed).")


def cmd_backfill_metadata(_args):
    db.init_db()
    with db.connect() as conn:
        rows = conn.execute("SELECT id, url FROM articles ORDER BY id").fetchall()
        records = [{"url": r["url"]} for r in rows]
        metas = resolve_metadata(conn, records)
        for row, (content_type, series_id, series_slug, match_id) in zip(rows, metas):
            db.update_article_metadata(conn, row["id"], content_type, series_id, series_slug, match_id)
        conn.commit()
    print(f"Backfilled metadata for {len(rows)} articles.")


def cmd_backfill_entities(_args):
    db.init_db()
    with db.connect() as conn:
        rows = conn.execute("SELECT id, title, summary FROM articles ORDER BY id").fetchall()
        texts = [f"{r['title']}. {r['summary']}" for r in rows]

        print(f"Mining player gazetteer from {len(rows)} articles (one-time NER pass, may take a few minutes)...")
        gazetteer = entities.mine_player_gazetteer(texts)
        entities.save_gazetteer(gazetteer)
        print(f"Mined {len(gazetteer)} candidate player names -> {entities.GAZETTEER_PATH}")

        player_pattern = entities.build_player_pattern(gazetteer)
        surname_to_full_name = entities.surname_lookup(gazetteer)

        for i, row in enumerate(rows):
            extract_entities_for(conn, row["id"], row["title"], row["summary"], player_pattern, surname_to_full_name)
            if i % 2000 == 0:
                print(f"[{i}/{len(rows)}] entities extracted")
                conn.commit()
        conn.commit()
    print(f"Backfilled entities for {len(rows)} articles.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Bulk import an existing articles CSV")
    seed_parser.add_argument("--csv", default="articles_full.csv")
    seed_parser.set_defaults(func=cmd_seed)

    scrape_parser = subparsers.add_parser("scrape", help="Scrape the newest listing pages for new articles")
    scrape_parser.add_argument("--pages", type=int, default=3)
    scrape_parser.set_defaults(func=cmd_scrape)

    backfill_metadata_parser = subparsers.add_parser("backfill-metadata", help="Re-parse url metadata for all rows")
    backfill_metadata_parser.set_defaults(func=cmd_backfill_metadata)

    backfill_entities_parser = subparsers.add_parser(
        "backfill-entities", help="Mine the player gazetteer and re-extract entities for all rows"
    )
    backfill_entities_parser.set_defaults(func=cmd_backfill_entities)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
