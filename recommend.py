"""Blended recommendation scoring: embedding similarity as the baseline,
with bonuses for shared players/teams/series so entity and structural
overlap dominate ranking instead of raw sentence-embedding similarity over
thin (title + one-line teaser) text. Shared by app.py and evaluate.py so
the eval harness always measures exactly what's shipped.
"""
import numpy as np

import db

# Bonus weights added on top of raw cosine similarity (~[-1, 1]).
PLAYER_MATCH_WEIGHT = 2.0
TEAM_MATCH_WEIGHT = 0.4
SAME_SERIES_WEIGHT = 1.5


class Recommender:
    def __init__(self, conn):
        self.ids = np.array([], dtype=int)
        self.matrix = np.zeros((0, 0), dtype=np.float32)
        self.norms = np.array([], dtype=np.float32)
        self.id_to_position = {}
        self.count = -1
        self.reload(conn)

    def reload(self, conn):
        self.ids, self.matrix = db.load_embedding_matrix(conn)
        norms = np.linalg.norm(self.matrix, axis=1)
        norms[norms == 0] = 1e-10
        self.norms = norms
        self.id_to_position = {int(aid): i for i, aid in enumerate(self.ids)}
        self.count = len(self.ids)

    def refresh_if_stale(self, conn):
        count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        if count != self.count:
            self.reload(conn)

    def recommend(self, conn, article_id, top_n=5, use_bonuses=True):
        """Returns a list of dicts: id, score, matched_players, matched_teams, same_series."""
        if article_id not in self.id_to_position or self.matrix.shape[0] < 2:
            return []

        pos = self.id_to_position[article_id]
        query_vec = self.matrix[pos]
        query_norm = self.norms[pos]
        with np.errstate(all="ignore"):
            similarities = (self.matrix @ query_vec) / (self.norms * query_norm)
        similarities[pos] = -np.inf

        scores = {int(aid): float(similarities[i]) for i, aid in enumerate(self.ids) if i != pos}
        matched_players = {}
        matched_teams = {}
        same_series_ids = set()

        if use_bonuses:
            for other_id, overlap in db.get_entity_overlap(conn, article_id).items():
                if other_id not in scores:
                    continue
                bonus = len(overlap["players"]) * PLAYER_MATCH_WEIGHT + len(overlap["teams"]) * TEAM_MATCH_WEIGHT
                scores[other_id] += bonus
                matched_players[other_id] = overlap["players"]
                matched_teams[other_id] = overlap["teams"]

            for other_id in db.get_same_series(conn, article_id):
                if other_id not in scores:
                    continue
                scores[other_id] += SAME_SERIES_WEIGHT
                same_series_ids.add(other_id)

        top_ids = sorted(scores, key=scores.get, reverse=True)[:top_n]
        return [
            {
                "id": rec_id,
                "score": scores[rec_id],
                "matched_players": matched_players.get(rec_id, []),
                "matched_teams": matched_teams.get(rec_id, []),
                "same_series": rec_id in same_series_ids,
            }
            for rec_id in top_ids
        ]
