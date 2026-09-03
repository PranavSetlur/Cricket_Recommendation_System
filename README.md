# Cricket Article Recommendations System

Pick a cricket article you like, get more like it. Content-based recommendations
over ESPNcricinfo articles, backed by sentence embeddings and a SQLite database
that grows incrementally — no static, one-time dataset.

## How it works

- `db.py` — SQLite schema (`articles.db`). Each article has a unique `url`
  (the dedup key) and a stored sentence-embedding vector.
- `ingest.py` — ingestion, safe to rerun any time:
  - `python ingest.py seed --csv articles_full.csv` — one-time bulk import of
    an existing articles CSV (title, link, summary, date columns).
  - `python ingest.py scrape --pages 5` — scrape the newest N listing pages
    from ESPNcricinfo and insert only articles not already in the database.
- `app.py` — Flask JSON API. Recommendations are computed on demand (cosine
  similarity against the in-memory embedding matrix), not precomputed and
  cached — so a newly ingested article is recommendable immediately, without
  restarting the app.
- `frontend/` — React (Vite) UI that talks to the API.

## Setup

### Backend

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# seed the database (only needed once, or after a fresh clone)
python ingest.py seed --csv articles_full.csv

# pull in newer articles at any time
python ingest.py scrape --pages 5

python app.py
```

The API runs on **http://localhost:5001** (not 5000 — macOS's AirPlay
Receiver squats on port 5000 by default, which will silently swallow
requests).

### Frontend

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api/*` requests to
the Flask backend on port 5001.

## Usage

Search for an article by title or summary, click it, and the right-hand
column shows similar articles ranked by embedding similarity. Click through
to read the full article on ESPNcricinfo.
