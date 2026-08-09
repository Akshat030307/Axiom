from dataclasses import dataclass
from datetime import datetime, timezone

BASE_SCORE = 0.5
_HIGH_TRUST_TLDS = {"gov", "edu"}
_MODERATE_TRUST_TLDS = {"org"}
_HTTPS_BONUS = 0.02
_RECENT_BONUS = 0.10        # published within the last year
_STALE_PENALTY = -0.05      # published more than 3 years ago
_CORROBORATION_PER_SOURCE = 0.10
_MAX_CORROBORATION_BONUS = 0.30
_SOURCE_TYPE_WEIGHT = {"academic": 0.15, "data": 0.10, "web": 0.0}

_DATE_FORMATS = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m", "%Y")


@dataclass(frozen=True)
class CredibilitySignals:
    domain: str
    url: str
    source_type: str
    publication_date: str | None
    corroboration_count: int  # distinct OTHER sources with a cosine-similar evidence claim


def _parse_date(value: str) -> datetime | None:
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _domain_score(domain: str, url: str) -> float:
    tld = domain.lower().rsplit(".", 1)[-1] if domain else ""
    score = 0.0
    if tld in _HIGH_TRUST_TLDS:
        score += 0.10
    elif tld in _MODERATE_TRUST_TLDS:
        score += 0.05
    if url.lower().startswith("https://"):
        score += _HTTPS_BONUS
    return score


def _recency_score(publication_date: str | None) -> float:
    if not publication_date:
        return 0.0  # missing date is neutral, not penalized — many authoritative pages don't expose one
    parsed = _parse_date(publication_date)
    if parsed is None:
        return 0.0
    age_days = (datetime.now(timezone.utc) - parsed).days
    if age_days < 0:
        return 0.0  # future-dated (clock skew, bad parse) — ignore rather than reward or punish
    if age_days <= 365:
        return _RECENT_BONUS
    if age_days <= 3 * 365:
        return 0.0
    return _STALE_PENALTY


def _corroboration_score(corroboration_count: int) -> float:
    return min(corroboration_count * _CORROBORATION_PER_SOURCE, _MAX_CORROBORATION_BONUS)


def score_source(signals: CredibilitySignals) -> float:
    """Deterministic, side-effect-free — Correction #9 requires credibility
    scoring to be a pure function, unlike the I/O-doing nodes elsewhere in
    the graph. The PRD names the inputs worth using (Correction #8: sources
    were normalized out of evidence specifically so corroboration could be
    counted) but doesn't give a formula — this is a from-scratch design:
    a neutral 0.5 base, small bumps for high-trust TLDs/HTTPS/recency, up to
    +0.30 for independent corroboration (capped at 3 corroborating sources),
    and a source_type weight that's currently inert (every source is "web"
    until academic/data researchers exist). Clamped to [0, 1].
    """
    score = BASE_SCORE
    score += _domain_score(signals.domain, signals.url)
    score += _recency_score(signals.publication_date)
    score += _corroboration_score(signals.corroboration_count)
    score += _SOURCE_TYPE_WEIGHT.get(signals.source_type, 0.0)
    return max(0.0, min(1.0, score))
