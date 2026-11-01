"""Deterministic normalization of Irish addresses and Eircodes for matching.

Normalized forms are used only for comparison; the original text is always kept as published."""

import re
import unicodedata
from dataclasses import dataclass

# Long and short forms map to one canonical token, so "Street"/"St" (and "Saint"/"St") compare
# equal without guessing which one was meant.
CANONICAL = {
    "street": "st", "saint": "st", "road": "rd", "avenue": "ave", "av": "ave",
    "drive": "dr", "court": "ct", "crescent": "cres", "cresent": "cres", "terrace": "terr",
    "tce": "terr", "square": "sq", "gardens": "gdns", "gdn": "gdns", "grove": "gr",
    "lane": "ln", "place": "pl", "park": "pk", "upper": "upr", "lower": "lwr",
    "mount": "mt", "north": "n", "south": "s", "east": "e", "west": "w",
    "apartment": "apt", "apartments": "apt", "flat": "apt", "unit": "apt",
}  # fmt: skip
# Structural words that carry no identity for matching.
DROP = {"no", "number", "the", "co", "county", "dublin", "ireland", "apt", "block"}
# A number right after one of these is a labelled number ("apt:2", "block:6"), so
# "Apartment 2 Block 6" and "Block 2 Apartment 6" stay different.
UNIT_LABELS = {"apt", "block"}
_DISTRICT = re.compile(r"\b(?:dublin|d)\s*(\d{1,2}w?)\b")
_EIRCODE = re.compile(r"^[A-Z]\d[\dW][A-Z\d]{4}$")


@dataclass(frozen=True)
class NormalizedAddress:
    text: str  # canonical tokens, original order
    numbers: tuple[str, ...]  # labelled house/unit numbers, sorted (order-insensitive)
    name: str  # non-number tokens without structural words, for fuzzy comparison
    district: str | None  # Dublin postal district ("8", "6w"), if written


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_address(raw: str) -> NormalizedAddress:
    text = strip_accents(raw).lower()
    district_match = _DISTRICT.search(text)
    district = district_match.group(1) if district_match else None
    text = _DISTRICT.sub(" ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [CANONICAL.get(t, t) for t in text.split()]
    numbers = []
    for i, token in enumerate(tokens):
        if not any(ch.isdigit() for ch in token):
            continue
        j = i - 1
        while j >= 0 and tokens[j] in ("no", "number"):
            j -= 1
        label = tokens[j] if j >= 0 and tokens[j] in UNIT_LABELS else None
        numbers.append(f"{label}:{token}" if label else token)
    name_tokens = [t for t in tokens if t not in DROP and not any(ch.isdigit() for ch in t)]
    if district:
        tokens.append(f"d{district}")  # same street in another district is another address
    return NormalizedAddress(
        text=" ".join(tokens),
        numbers=tuple(sorted(numbers)),
        name=" ".join(name_tokens),
        district=district,
    )


def normalize_eircode(raw: str | None) -> str | None:
    """Uppercase without spaces if it has a valid Eircode shape, else None."""
    if not raw:
        return None
    code = re.sub(r"\s+", "", raw).upper()
    return code if _EIRCODE.match(code) else None
