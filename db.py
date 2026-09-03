import sqlite3
from contextlib import contextmanager

import numpy as np

DB_PATH = "articles.db"

TABLES = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    published_date TEXT,
    scraped_at TEXT NOT NULL,
    embedding BLOB NOT NULL,
    content_type TEXT,
    series_id TEXT,
    series_slug TEXT,
    match_id TEXT
);

CREATE TABLE IF NOT EXISTS article_entities (
    article_id INTEGER NOT NULL REFERENCES articles(id),
    entity_type TEXT NOT NULL,   -- 'player' | 'team'
    entity_name TEXT NOT NULL,
    PRIMARY KEY (article_id, entity_type, entity_name)
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_articles_title ON articles(title);
CREATE INDEX IF NOT EXISTS idx_articles_series_id ON articles(series_id);
CREATE INDEX IF NOT EXISTS idx_articles_series_slug ON articles(series_slug);
CREATE INDEX IF NOT EXISTS idx_article_entities_name ON article_entities(entity_name);
"""


@contextmanager
def connect(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path=DB_PATH):
    with connect(db_path) as conn:
        conn.executescript(TABLES)
        # migrate DBs created before content_type/series_id/series_slug/match_id existed
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
        for column in ("content_type", "series_id", "series_slug", "match_id"):
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE articles ADD COLUMN {column} TEXT")
        conn.executescript(INDEXES)
        conn.commit()


def article_exists(conn, url):
    row = conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone()
    return row is not None


def insert_article(
    conn,
    title,
    url,
    summary,
    published_date,
    scraped_at,
    embedding,
    content_type=None,
    series_id=None,
    series_slug=None,
    match_id=None,
):
    """Insert an article. Returns the new row id, or None if the url already existed."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO articles
            (title, url, summary, published_date, scraped_at, embedding,
             content_type, series_id, series_slug, match_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title, url, summary, published_date, scraped_at, embedding.astype(np.float32).tobytes(),
            content_type, series_id, series_slug, match_id,
        ),
    )
    return cur.lastrowid if cur.rowcount > 0 else None


def update_article_metadata(conn, article_id, content_type, series_id, series_slug, match_id):
    conn.execute(
        """
        UPDATE articles SET content_type = ?, series_id = ?, series_slug = ?, match_id = ?
        WHERE id = ?
        """,
        (content_type, series_id, series_slug, match_id, article_id),
    )


def all_series_slugs(conn):
    rows = conn.execute(
        "SELECT DISTINCT series_slug FROM articles WHERE content_type = 'match' AND series_slug IS NOT NULL"
    ).fetchall()
    return [row["series_slug"] for row in rows]


def replace_entities(conn, article_id, entity_pairs):
    """entity_pairs: iterable of (entity_type, entity_name)."""
    conn.execute("DELETE FROM article_entities WHERE article_id = ?", (article_id,))
    conn.executemany(
        "INSERT OR IGNORE INTO article_entities (article_id, entity_type, entity_name) VALUES (?, ?, ?)",
        [(article_id, etype, ename) for etype, ename in entity_pairs],
    )


def get_entities_for_article(conn, article_id):
    rows = conn.execute(
        "SELECT entity_type, entity_name FROM article_entities WHERE article_id = ?", (article_id,)
    ).fetchall()
    return [(row["entity_type"], row["entity_name"]) for row in rows]


def get_entity_overlap(conn, article_id):
    """For every entity on `article_id`, find other articles sharing it.
    Returns {other_article_id: {"players": [...], "teams": [...]}}."""
    entities = get_entities_for_article(conn, article_id)
    if not entities:
        return {}

    overlap = {}
    for entity_type, entity_name in entities:
        rows = conn.execute(
            """
            SELECT article_id FROM article_entities
            WHERE entity_type = ? AND entity_name = ? AND article_id != ?
            """,
            (entity_type, entity_name, article_id),
        ).fetchall()
        for row in rows:
            other_id = row["article_id"]
            bucket = overlap.setdefault(other_id, {"players": [], "teams": []})
            key = "players" if entity_type == "player" else "teams"
            bucket[key].append(entity_name)
    return overlap


def get_same_series(conn, article_id):
    """Returns {other_article_id: True} for articles sharing this article's
    series_id (exact tournament) or, failing that, series_slug."""
    row = conn.execute("SELECT series_id, series_slug FROM articles WHERE id = ?", (article_id,)).fetchone()
    if row is None or (row["series_id"] is None and row["series_slug"] is None):
        return {}

    if row["series_id"] is not None:
        rows = conn.execute(
            "SELECT id FROM articles WHERE series_id = ? AND id != ?", (row["series_id"], article_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id FROM articles WHERE series_slug = ? AND id != ?", (row["series_slug"], article_id)
        ).fetchall()
    return {r["id"]: True for r in rows}


def get_article(conn, article_id):
    return conn.execute("SELECT id, title, url, summary, published_date FROM articles WHERE id = ?", (article_id,)).fetchone()


def get_articles_by_ids(conn, article_ids):
    if not article_ids:
        return {}
    placeholders = ",".join("?" for _ in article_ids)
    rows = conn.execute(
        f"SELECT id, title, url, summary, published_date FROM articles WHERE id IN ({placeholders})",
        article_ids,
    ).fetchall()
    return {row["id"]: row for row in rows}


def search_articles(conn, query, page=1, page_size=10):
    like = f"%{query}%"
    total = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE title LIKE ? OR summary LIKE ?", (like, like)
    ).fetchone()[0]
    offset = (page - 1) * page_size
    rows = conn.execute(
        """
        SELECT id, title, url, summary, published_date FROM articles
        WHERE title LIKE ? OR summary LIKE ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (like, like, page_size, offset),
    ).fetchall()
    return rows, total


def load_embedding_matrix(conn):
    """Returns (ids, embedding_matrix) covering every stored article, for on-demand similarity search."""
    rows = conn.execute("SELECT id, embedding FROM articles ORDER BY id").fetchall()
    if not rows:
        return np.array([], dtype=int), np.zeros((0, 0), dtype=np.float32)
    ids = np.array([row["id"] for row in rows], dtype=int)
    matrix = np.stack([np.frombuffer(row["embedding"], dtype=np.float32) for row in rows])
    return ids, matrix
