# Deploying

Two pieces, deployed separately: the Flask API (Hugging Face Spaces) and the
React frontend (Vercel or Netlify). Both are free, no credit card required.

## 1. Backend — Hugging Face Spaces

Why Spaces and not PythonAnywhere: this app depends on `sentence-transformers`
and `spacy` + the `en_core_web_md` model, which is more than PythonAnywhere's
free-tier disk quota and outbound domain allowlist can reliably handle.
Spaces are built for exactly this kind of ML-dependent app.

1. Create a free account at huggingface.co, then create a new Space:
   - SDK: **Docker**
   - Visibility: your choice
2. The Space gets its own git remote (separate from this project's GitHub
   repo — e.g. `https://huggingface.co/spaces/<you>/<space-name>`).
3. Locally, make sure `articles.db` and `player_gazetteer.json` exist and
   are built from however much of the corpus you want live (see the main
   README for `ingest.py seed` / `backfill-metadata` / `backfill-entities`).
   These two files are intentionally gitignored in the **GitHub** repo (they're
   generated, not source) — but the Space needs them baked into its image, so:
   ```
   git remote add space https://huggingface.co/spaces/<you>/<space-name>
   git add -f articles.db player_gazetteer.json Dockerfile .dockerignore
   git commit -m "Deploy: include built db + gazetteer"
   git push space main
   ```
   (`-f` overrides the root `.gitignore` for this commit only — these files
   still won't get pushed to the GitHub `origin` remote.)
4. The Space builds the Dockerfile automatically. First build takes a while
   (installing torch + spaCy model). Once it's up, note its URL — something
   like `https://<you>-<space-name>.hf.space`.
5. Sanity check: `curl https://<you>-<space-name>.hf.space/api/articles?page_size=1`

## 2. Frontend — Vercel (or Netlify)

1. Push this repo to GitHub (already done via `origin`) if not already.
2. In Vercel: New Project → import the GitHub repo → set **Root Directory**
   to `frontend`. It auto-detects Vite.
3. Add an environment variable: `VITE_API_BASE` = the Space URL from step 1
   above (no trailing slash), e.g. `https://<you>-<space-name>.hf.space`.
4. Deploy. Vercel gives you a URL — that's the live site.

Netlify: same idea — root directory `frontend`, build command `npm run build`,
publish directory `dist`, same `VITE_API_BASE` env var.

## Updating after this initial deploy

- **Backend code change**: `git push space main` again from the main repo
  (Spaces rebuild on push).
- **New articles ingested**: run `ingest.py` locally against `articles.db`,
  then `git add -f articles.db player_gazetteer.json && git commit && git push space main`
  — the DB is baked into the image, not fetched at runtime.
- **Frontend change**: push to GitHub `origin`; Vercel/Netlify redeploy
  automatically on push if the project is connected to the repo.
