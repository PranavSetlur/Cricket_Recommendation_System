#!/usr/bin/env python
"""Offline recall@K evaluation for the recommender.

Ground truth is implicit: articles that share a player entity or a
series_id are treated as relevant to each other (a proxy label, not a true
one, but a strong enough one for cricket to be meaningful — two articles
mentioning Virat Kohli, or from the same tournament, are near-certainly
related). For every query article with at least one such relevant article,
computes recall@K three ways so the effect of the entity/series bonuses is
a real, comparable number instead of a vibe:

  - random baseline    (sanity floor)
  - embedding only      (the old pure-cosine-similarity approach)
  - blended (shipped)   (embedding + player/team/series bonuses)

Usage: python evaluate.py [--k 10] [--sample 300]
"""
import argparse
import random

import db
from recommend import Recommender


def build_relevance_sets(conn):
    """article_id -> set of other article_ids considered relevant (shares a
    player entity or a series_id)."""
    relevant = {}

    player_rows = conn.execute(
        "SELECT article_id, entity_name FROM article_entities WHERE entity_type = 'player'"
    ).fetchall()
    by_player = {}
    for row in player_rows:
        by_player.setdefault(row["entity_name"], set()).add(row["article_id"])
    for article_ids in by_player.values():
        if len(article_ids) < 2:
            continue
        for aid in article_ids:
            relevant.setdefault(aid, set()).update(article_ids - {aid})

    series_rows = conn.execute(
        "SELECT id, series_id FROM articles WHERE series_id IS NOT NULL"
    ).fetchall()
    by_series = {}
    for row in series_rows:
        by_series.setdefault(row["series_id"], set()).add(row["id"])
    for article_ids in by_series.values():
        if len(article_ids) < 2:
            continue
        for aid in article_ids:
            relevant.setdefault(aid, set()).update(article_ids - {aid})

    return relevant


def recall_at_k(recommended_ids, relevant_ids, k):
    if not relevant_ids:
        return None
    hits = len(set(recommended_ids[:k]) & relevant_ids)
    return hits / min(k, len(relevant_ids))


def evaluate(conn, recommender, relevance, k, sample_size, use_bonuses, all_ids):
    query_ids = list(relevance.keys())
    if len(query_ids) > sample_size:
        query_ids = random.sample(query_ids, sample_size)

    recalls = []
    for article_id in query_ids:
        if article_id not in recommender.id_to_position:
            continue
        ranked = recommender.recommend(conn, article_id, top_n=k, use_bonuses=use_bonuses)
        recommended_ids = [r["id"] for r in ranked]
        recalls.append(recall_at_k(recommended_ids, relevance[article_id], k))

    return sum(recalls) / len(recalls) if recalls else 0.0


def evaluate_random(relevance, k, sample_size, all_ids):
    query_ids = list(relevance.keys())
    if len(query_ids) > sample_size:
        query_ids = random.sample(query_ids, sample_size)

    recalls = []
    for article_id in query_ids:
        candidates = [aid for aid in all_ids if aid != article_id]
        recommended_ids = random.sample(candidates, min(k, len(candidates)))
        recalls.append(recall_at_k(recommended_ids, relevance[article_id], k))
    return sum(recalls) / len(recalls) if recalls else 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--sample", type=int, default=300)
    args = parser.parse_args()

    with db.connect() as conn:
        recommender = Recommender(conn)
        relevance = build_relevance_sets(conn)
        all_ids = [int(x) for x in recommender.ids]

        print(f"Query articles with ground truth (shared player or series_id): {len(relevance)} / {len(all_ids)}")
        print(f"Evaluating recall@{args.k} on a sample of up to {args.sample}...\n")

        random_score = evaluate_random(relevance, args.k, args.sample, all_ids)
        embedding_only = evaluate(conn, recommender, relevance, args.k, args.sample, use_bonuses=False, all_ids=all_ids)
        blended = evaluate(conn, recommender, relevance, args.k, args.sample, use_bonuses=True, all_ids=all_ids)

        print(f"random baseline:        {random_score:.3f}")
        print(f"embedding only (old):    {embedding_only:.3f}")
        print(f"blended (shipped):       {blended:.3f}")


if __name__ == "__main__":
    main()
