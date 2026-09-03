"""Cricket entity extraction: teams (static gazetteer) and players (mined
from the corpus itself, since no fixed player list exists).

spaCy's generic PERSON tagger is unreliable on cricket surnames in short,
headline-style text (verified: it tags "Nepal" as PERSON, "Kirsten" and
"Babar" as ORG). It's still useful as a *seed* — it reliably catches clean
two-token full names like "Rohit Sharma" or "Jasprit Bumrah". Those seeds
become a gazetteer (full name + surname alias, when the surname isn't
ambiguous across two different mined players), which is then matched
directly against text — far higher precision than trusting NER tag-by-tag.
"""
import json
import re
from collections import Counter

import spacy

GAZETTEER_PATH = "player_gazetteer.json"

TEAMS = {
    # Full ICC members
    "India", "Australia", "England", "Pakistan", "South Africa", "New Zealand",
    "Sri Lanka", "West Indies", "Bangladesh", "Zimbabwe", "Ireland", "Afghanistan",
    # Frequently appearing associates
    "Nepal", "Netherlands", "Scotland", "Oman", "Namibia", "Uganda",
    "Papua New Guinea", "Canada", "Kenya", "Hong Kong", "USA", "UAE",
    # IPL franchises
    "Mumbai Indians", "Chennai Super Kings", "Royal Challengers Bangalore",
    "Royal Challengers Bengaluru", "Kolkata Knight Riders", "Delhi Capitals",
    "Punjab Kings", "Rajasthan Royals", "Sunrisers Hyderabad", "Gujarat Titans",
    "Lucknow Super Giants",
    # English counties
    "Derbyshire", "Durham", "Essex", "Glamorgan", "Gloucestershire", "Hampshire",
    "Kent", "Lancashire", "Leicestershire", "Middlesex", "Northamptonshire",
    "Nottinghamshire", "Somerset", "Surrey", "Sussex", "Warwickshire",
    "Worcestershire", "Yorkshire",
    # English women's domestic sides (full names only — nicknames like
    # "Storm"/"Blaze" alone are too ambiguous with common words)
    "Southern Vipers", "Western Storm", "Central Sparks", "Northern Diamonds",
    "The Blaze", "Thunder", "Sunrisers", "Lightning",
}
# Longest-first so e.g. "Royal Challengers Bangalore" matches before "Bangalore" would.
_TEAMS_SORTED = sorted(TEAMS, key=len, reverse=True)
_TEAM_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _TEAMS_SORTED) + r")\b"
)

_STOPWORD_SURNAMES = {
    # common English words that also happen to be cricket surnames — too
    # ambiguous to match as a bare surname alias without full-name context
    "root", "day", "law", "king", "young", "hope", "bond", "may", "cook",
}

_nlp = None


def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_md", disable=["lemmatizer", "textcat"])
    return _nlp


def extract_teams(text):
    return sorted(set(_TEAM_PATTERN.findall(text)))


def mine_player_gazetteer(texts, min_count=1, batch_size=256):
    """Runs NER once over every article's text, keeps clean two-token PERSON
    spans seen at least `min_count` times, and derives an unambiguous-surname
    alias for each. Returns {full_name: [full_name, surname_alias_or_none]}.
    """
    nlp = get_nlp()
    name_counts = Counter()

    for doc in nlp.pipe(texts, batch_size=batch_size):
        for ent in doc.ents:
            if ent.label_ != "PERSON":
                continue
            tokens = ent.text.split()
            if len(tokens) == 2 and all(t.isalpha() and t[0].isupper() for t in tokens):
                name_counts[ent.text] += 1

    surname_to_names = {}
    for full_name, count in name_counts.items():
        if count < min_count:
            continue
        surname = full_name.split()[-1]
        surname_to_names.setdefault(surname, set()).add(full_name)

    gazetteer = {}
    for full_name, count in name_counts.items():
        if count < min_count:
            continue
        surname = full_name.split()[-1]
        unambiguous = len(surname_to_names[surname]) == 1
        usable_surname = (
            surname if unambiguous and surname.lower() not in _STOPWORD_SURNAMES and len(surname) >= 4 else None
        )
        gazetteer[full_name] = {"full_name": full_name, "surname": usable_surname}

    return gazetteer


def save_gazetteer(gazetteer, path=GAZETTEER_PATH):
    with open(path, "w") as f:
        json.dump(gazetteer, f)


def load_gazetteer(path=GAZETTEER_PATH):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def surname_lookup(gazetteer):
    return {v["surname"]: v["full_name"] for v in gazetteer.values() if v["surname"]}


def build_player_pattern(gazetteer):
    names = set()
    for entry in gazetteer.values():
        names.add(entry["full_name"])
        if entry["surname"]:
            names.add(entry["surname"])
    names_sorted = sorted(names, key=len, reverse=True)
    if not names_sorted:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names_sorted) + r")\b")


def extract_players(text, player_pattern, surname_to_full_name):
    """Returns canonical full names mentioned in `text` (surname hits are
    resolved back to their unambiguous full name)."""
    if player_pattern is None:
        return []
    hits = set(player_pattern.findall(text))
    resolved = set()
    for hit in hits:
        resolved.add(surname_to_full_name.get(hit, hit))
    return sorted(resolved)
