import hashlib
import re

_ALIAS_SLUG_MAX_LENGTH = 30
_ALIAS_DIGEST_LENGTH = 8


def make_alias(name: str, country: str, offer_id: int) -> str:
    """Детерминированный alias: один и тот же запрос всегда даёт один и тот же alias."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:_ALIAS_SLUG_MAX_LENGTH]
    key = f"{name.casefold()}|{country}|{offer_id}"
    digest = hashlib.sha1(key.encode()).hexdigest()[:_ALIAS_DIGEST_LENGTH]
    return f"{slug or 'campaign'}-{digest}"


def stream_name(country: str) -> str:
    return f"{country} flow"
