# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import difflib
import logging
import re
import unicodedata

_logger = logging.getLogger(__name__)


def normalize_region_name(value):
    """Normalise a province name for matching: case, spaces, accents, punctuation.

    Also strips parenthesis content and common stopwords.
    """
    if not value:
        return ""
    text = str(value)
    # remove parenthesis content
    text = re.sub(r"\s*\([^)]*\)", " ", text)
    # unicode normalize and strip diacritics
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # remove punctuation
    text = re.sub(r"[\.,;:\-\/()\[\]\\\"]+", " ", text)
    # lowercase and collapse spaces
    text = " ".join(text.lower().split())
    # remove common stopwords
    stopwords = {
        "provincia",
        "prov",
        "de",
        "del",
        "la",
        "el",
        "islas",
        "illes",
        "comunidad",
        "autonoma",
        "autonoma",
        "autónoma",
    }
    tokens = [t for t in text.split() if t not in stopwords]
    return " ".join(tokens)


def find_state(env, country, region):
    """
    Return the province matching Region within the country,
    if any.

    env: Odoo environment (to query res.country.state)
    country: res.country record or falsy
    region: raw region string from Agora
    """
    if not country or not region:
        return env["res.country.state"]

    normalized_region = normalize_region_name(region)
    if not normalized_region:
        return env["res.country.state"]

    candidates = env["res.country.state"].search([("country_id", "=", country.id)])
    if not candidates:
        return env["res.country.state"]

    # Precompute normalized forms for candidates
    candidate_map = []
    for s in candidates:
        name = s.name or ""
        norm_full = normalize_region_name(name)
        # also remove parenthesis content for a cleaner form
        name_no_paren = re.sub(r"\s*\([^)]*\)", "", name)
        norm_no_paren = normalize_region_name(name_no_paren)
        tokens = {t for t in norm_no_paren.split() if len(t) > 1}
        candidate_map.append(
            {
                "state": s,
                "name": name,
                "norm_full": norm_full,
                "norm_no_paren": norm_no_paren,
                "tokens": tokens,
            }
        )

    # 1) Exact normalized match
    match = _match_exact(candidate_map, normalized_region)
    if match:
        return match

    # 2) Match against name without parenthesis
    match = _match_no_paren(candidate_map, normalized_region)
    if match:
        return match

    # 3) Substring match (both ways)
    match = _match_substring(candidate_map, normalized_region)
    if match:
        return match

    # 4) Token intersection ratio
    match = _match_token_ratio(candidate_map, normalized_region)
    if match:
        return match

    # 5) Fuzzy matching as last resort
    match = _match_fuzzy(candidate_map, normalized_region, region)
    if match:
        return match

    # No reliable match
    return env["res.country.state"]


def _match_exact(candidate_map, normalized_region):
    for c in candidate_map:
        if c["norm_full"] == normalized_region:
            return c["state"]
    return None


def _match_no_paren(candidate_map, normalized_region):
    for c in candidate_map:
        if c["norm_no_paren"] == normalized_region:
            return c["state"]
    return None


def _match_substring(candidate_map, normalized_region):
    for c in candidate_map:
        if (
            normalized_region in c["norm_no_paren"]
            or c["norm_no_paren"] in normalized_region
        ):
            return c["state"]
    return None


def _match_token_ratio(candidate_map, normalized_region):
    region_tokens = {t for t in normalized_region.split() if len(t) > 1}
    best_token_score = (None, 0.0)
    for c in candidate_map:
        if not region_tokens or not c["tokens"]:
            continue
        inter = region_tokens.intersection(c["tokens"])
        score = len(inter) / min(len(region_tokens), len(c["tokens"]))
        if score > best_token_score[1]:
            best_token_score = (c["state"], score)
    if best_token_score[1] >= 0.66:
        return best_token_score[0]
    return None


def _match_fuzzy(candidate_map, normalized_region, region):
    best_fuzzy = (None, 0.0)
    for c in candidate_map:
        ratio = difflib.SequenceMatcher(
            None, normalized_region, c["norm_no_paren"]
        ).ratio()
        if ratio > best_fuzzy[1]:
            best_fuzzy = (c["state"], ratio)

    if best_fuzzy[1] >= 0.86:
        _logger.info(
            "region_matcher.find_state: fuzzy matched region '%s' -> '%s' (score=%.2f)",
            region,
            best_fuzzy[0].name if best_fuzzy[0] else None,
            best_fuzzy[1],
        )
        return best_fuzzy[0]

    return None
