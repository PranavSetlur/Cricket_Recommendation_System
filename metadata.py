"""Parses ESPNcricinfo's own URL structure into structured article metadata."""
import re

STORY_RE = re.compile(r"/story/([a-z0-9-]+)-(\d+)$")
SERIES_RE = re.compile(r"/series/([a-z0-9-]+)-(\d+)/(?:([a-z0-9-]+)-(\d+)/)?")


def parse_url(url):
    """Returns (content_type, series_id, raw_slug, match_id).

    `raw_slug` is the series slug for `match` articles (final, authoritative)
    or the bare story slug for `story` articles (needs `guess_series_slug`
    against a vocabulary to become a usable series_slug, since story URLs
    carry no numeric series ID to anchor to)."""
    m = SERIES_RE.search(url)
    if m:
        series_slug, series_id, _match_slug, match_id = m.groups()
        return "match", series_id, series_slug, match_id

    m = STORY_RE.search(url)
    if m:
        slug, _story_id = m.groups()
        return "story", None, slug, None

    return "story", None, None, None


def build_series_vocabulary(series_slugs):
    """De-duplicated, longest-first list of known series slugs for prefix matching."""
    return sorted(set(s for s in series_slugs if s), key=len, reverse=True)


def guess_series_slug(story_slug, vocabulary):
    """Best-effort tournament tag for a `story` article: does its slug start
    with (a normalized form of) a known series slug? Longest match wins so
    e.g. 'icc-men-s-t20-world-cup-2024' is preferred over 't20-world-cup-2024'
    when both are present in the vocabulary and both match."""
    normalized = story_slug.replace("icc-men-s-", "").replace("icc-", "")
    for candidate in vocabulary:
        candidate_normalized = candidate.replace("icc-men-s-", "").replace("icc-", "")
        if normalized.startswith(candidate_normalized) or story_slug.startswith(candidate):
            return candidate
    return None
