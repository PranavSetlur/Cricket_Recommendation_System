FROM python:3.11-slim

WORKDIR /app
ENV HOME=/app
ENV PORT=7860

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_md

COPY app.py db.py entities.py metadata.py recommend.py ingest.py ./
# Pre-built at deploy time (see DEPLOY.md) — avoids re-running the multi-minute
# embedding + spaCy NER pipeline on every container start.
COPY articles.db player_gazetteer.json ./

EXPOSE 7860
CMD ["python", "app.py"]
