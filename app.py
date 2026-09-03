import os

from flask import Flask, jsonify, request
from flask_cors import CORS

import db
from recommend import Recommender

app = Flask(__name__)
CORS(app)

with db.connect() as _conn:
    db.init_db()
    _recommender = Recommender(_conn)


def row_to_dict(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "url": row["url"],
        "summary": row["summary"],
        "published_date": row["published_date"],
    }


@app.route("/api/articles")
def list_articles():
    query = request.args.get("search", "")
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(int(request.args.get("page_size", 10)), 50)

    with db.connect() as conn:
        rows, total = db.search_articles(conn, query, page=page, page_size=page_size)

    return jsonify(
        {
            "articles": [row_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "total_pages": (total + page_size - 1) // page_size,
        }
    )


@app.route("/api/articles/<int:article_id>")
def get_article(article_id):
    with db.connect() as conn:
        row = db.get_article(conn, article_id)
    if row is None:
        return jsonify({"error": "article not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/api/articles/<int:article_id>/recommendations")
def get_recommendations(article_id):
    top_n = min(int(request.args.get("n", 5)), 50)

    with db.connect() as conn:
        article = db.get_article(conn, article_id)
        if article is None:
            return jsonify({"error": "article not found"}), 404

        _recommender.refresh_if_stale(conn)
        ranked = _recommender.recommend(conn, article_id, top_n=top_n)

        rows_by_id = db.get_articles_by_ids(conn, [r["id"] for r in ranked])
        recommendations = []
        for r in ranked:
            row = rows_by_id.get(r["id"])
            if row is None:
                continue
            rec = row_to_dict(row)
            rec["matched_players"] = r["matched_players"]
            rec["matched_teams"] = r["matched_teams"]
            rec["same_series"] = r["same_series"]
            recommendations.append(rec)

    return jsonify({"article": row_to_dict(article), "recommendations": recommendations})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
