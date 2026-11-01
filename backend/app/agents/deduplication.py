"""Deduplication (agent 07) for transacted prices: which sales are the same physical property.

Order of evidence, strongest first:
  1. same Eircode (unique per address in Ireland)
  2. same normalized address
  3. fuzzy address similarity inside a block, only when nothing vetoes the pair
A union is always refused when it would put two different Eircodes, or two sales on the same
date, in one property. Doubtful pairs go to dedup_candidates for human review; nothing is
deleted and every link can be undone (property_transactions.property_id).
Precision is measured against Eircode ground truth: see evaluate_against_eircode()."""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from itertools import combinations

from rapidfuzz import fuzz

from app.validators.address import NormalizedAddress, normalize_address, normalize_eircode

VERSION = "dedup-txn-1"
AUTO_LINK_SCORE = 95  # calibrated against Eircode truth (docs/ROADMAP.md, Fase 4)
REVIEW_SCORE = 85


@dataclass(frozen=True)
class Txn:
    id: int
    address: str
    eircode: str | None
    sale_date: date
    norm: NormalizedAddress
    region_id: int | None = None  # county; a property never spans two

    @classmethod
    def build(
        cls,
        id: int,
        address: str | None,
        eircode: str | None,
        sale_date: date,
        region_id: int | None = None,
    ) -> "Txn":
        return cls(id, address or "", normalize_eircode(eircode), sale_date,
                   normalize_address(address or ""), region_id)  # fmt: skip


def _digits(norm: NormalizedAddress) -> tuple[str, ...]:
    return tuple(sorted(n.split(":")[-1] for n in norm.numbers))


def untrusted_eircodes(txns: list[Txn]) -> set[str]:
    """Eircodes attached to addresses with different house/unit numbers.

    Real Eircodes identify one address; a code shared by "33 X Road" and "109 Main St" is a
    placeholder or typo in the source (e.g. "A123456") and must not link anything."""
    numbers_by_code: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    for t in txns:
        if t.eircode and t.norm.numbers:
            numbers_by_code[t.eircode].add(_digits(t.norm))
    return {code for code, numbers in numbers_by_code.items() if len(numbers) > 1}


@dataclass(frozen=True)
class ReviewPair:
    a: int  # transaction id
    b: int
    score: float
    vetoes: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class FuzzyLink:
    a: int
    b: int
    score: float


def pair_vetoes(a: NormalizedAddress, b: NormalizedAddress) -> list[str]:
    vetoes = []
    if not a.numbers or not b.numbers:
        # Townland/named-house addresses are shared by many homes: only Eircode can link them.
        vetoes.append("NO_NUMBER")
    if a.numbers != b.numbers:
        vetoes.append("NUMBERS_DIFFER")
    if a.district and b.district and a.district != b.district:
        vetoes.append("DISTRICT_DIFFERS")
    if not a.name or not b.name:
        vetoes.append("NO_NAME")
    return vetoes


def similarity(a: NormalizedAddress, b: NormalizedAddress) -> float:
    return fuzz.token_sort_ratio(a.name, b.name)


def token_diff(a: NormalizedAddress, b: NormalizedAddress) -> str:
    """How two names differ after pairing near-identical long tokens (typos):
    "typo"         only typo-like differences        -> may auto-link
    "one_sided"    one address has extra words       -> human review
    "substitution" different words on both sides     -> different properties
                   ("Walk" vs "Way", "Road" vs "Grove")"""
    b_tokens = set(b.name.split())
    a_only = set(a.name.split()) - b_tokens
    b_only = b_tokens - set(a.name.split())
    for token in sorted(a_only):
        match = next(
            (
                o
                for o in sorted(b_only)
                if min(len(token), len(o)) >= 5 and fuzz.ratio(token, o) >= 85
            ),
            None,
        )
        if match:
            a_only.discard(token)
            b_only.discard(match)
    if not a_only and not b_only:
        return "typo"
    return "substitution" if a_only and b_only else "one_sided"


class _Clusters:
    """Union-find that refuses unions mixing Eircodes, counties, districts or sale dates.

    Checked per cluster, not per pair, so an address without district cannot bridge two
    addresses in different districts."""

    def __init__(self, txns: list[Txn]) -> None:
        self.parent = {t.id: t.id for t in txns}
        self.eircodes = {t.id: {t.eircode} - {None} for t in txns}
        self.districts = {t.id: {t.norm.district} - {None} for t in txns}
        self.regions = {t.id: {t.region_id} - {None} for t in txns}
        self.dates = {t.id: {t.sale_date} for t in txns}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def conflict(self, a: int, b: int) -> str | None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return None
        if self.eircodes[ra] and self.eircodes[rb] and self.eircodes[ra] != self.eircodes[rb]:
            return "EIRCODE_DIFFERS"
        if self.regions[ra] and self.regions[rb] and self.regions[ra] != self.regions[rb]:
            return "REGION_DIFFERS"
        if self.districts[ra] and self.districts[rb] and self.districts[ra] != self.districts[rb]:
            return "DISTRICT_DIFFERS"
        if self.dates[ra] & self.dates[rb]:
            return "SAME_SALE_DATE"
        return None

    def union(self, a: int, b: int) -> str | None:
        """Merge, or return the reason it was refused."""
        reason = self.conflict(a, b)
        if reason:
            return reason
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra
            self.eircodes[ra] |= self.eircodes.pop(rb)
            self.districts[ra] |= self.districts.pop(rb)
            self.regions[ra] |= self.regions.pop(rb)
            self.dates[ra] |= self.dates.pop(rb)
        return None

    def groups(self) -> list[list[int]]:
        out: dict[int, list[int]] = defaultdict(list)
        for x in self.parent:
            out[self.find(x)].append(x)
        return list(out.values())


@dataclass
class DedupResult:
    groups: list[list[int]]
    fuzzy_links: list[FuzzyLink]
    review: list[ReviewPair]
    stats: dict[str, int]


def cluster(
    txns: list[Txn], auto_link: float = AUTO_LINK_SCORE, review: float = REVIEW_SCORE
) -> DedupResult:
    untrusted = untrusted_eircodes(txns)
    txns = [replace(t, eircode=None) if t.eircode in untrusted else t for t in txns]
    uf = _Clusters(txns)
    stats: dict[str, int] = defaultdict(int)
    stats["untrusted_eircodes"] = len(untrusted)
    review_pairs: list[ReviewPair] = []
    fuzzy_links: list[FuzzyLink] = []

    def link(a: Txn, b: Txn, kind: str, score: float = 100.0) -> None:
        refused = uf.union(a.id, b.id)
        if refused is None:
            stats[f"linked_{kind}"] += 1
        else:
            stats[f"refused_{refused.lower()}"] += 1
            if refused == "SAME_SALE_DATE":  # e.g. units sold together: a human decides
                review_pairs.append(ReviewPair(a.id, b.id, score, (refused,), kind))

    # 1. Same Eircode.
    by_eircode: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        if t.eircode:
            by_eircode[t.eircode].append(t)
    for group in by_eircode.values():
        for other in group[1:]:
            link(group[0], other, "eircode")

    # 2. Same normalized address (needs a number and a name to identify one home).
    by_text: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        if t.norm.name and t.norm.numbers:
            by_text[t.norm.text].append(t)
    for group in by_text.values():
        for other in group[1:]:
            link(group[0], other, "address")

    # 3. Fuzzy, between distinct normalized addresses sharing numbers and a name prefix.
    blocks: dict[tuple, list[Txn]] = defaultdict(list)
    for group in by_text.values():
        rep = group[0]
        blocks[(rep.norm.numbers, rep.norm.name[:3])].append(rep)
    for reps in blocks.values():
        for a, b in combinations(reps, 2):
            if pair_vetoes(a.norm, b.norm):
                continue
            score = similarity(a.norm, b.norm)
            kind = token_diff(a.norm, b.norm)
            if kind == "typo" and score >= auto_link:
                if uf.conflict(a.id, b.id) is None:
                    fuzzy_links.append(FuzzyLink(a.id, b.id, score))
                link(a, b, "fuzzy", score)
            elif kind == "one_sided" and score >= review and uf.find(a.id) != uf.find(b.id):
                if uf.conflict(a.id, b.id) is None:
                    review_pairs.append(ReviewPair(a.id, b.id, score, (), "fuzzy"))
                    stats["review_fuzzy"] += 1

    return DedupResult(uf.groups(), fuzzy_links, review_pairs, dict(stats))


def _pairs(n: int) -> int:
    return n * (n - 1) // 2


def evaluate_against_eircode(
    txns: list[Txn], auto_link: float = AUTO_LINK_SCORE
) -> dict[str, float]:
    """Pair precision/recall of address-only clustering, using Eircode as ground truth.

    Only transactions with a trusted Eircode are used; the Eircode is hidden from the clusterer."""
    untrusted = untrusted_eircodes(txns)
    with_code = [t for t in txns if t.eircode and t.eircode not in untrusted]
    truth = {t.id: t.eircode for t in with_code}
    result = cluster([replace(t, eircode=None) for t in with_code], auto_link=auto_link)
    predicted_pairs = sum(_pairs(len(g)) for g in result.groups)
    true_positive = 0
    for group in result.groups:
        by_code: dict[str, int] = defaultdict(int)
        for tid in group:
            by_code[truth[tid]] += 1
        true_positive += sum(_pairs(n) for n in by_code.values())
    code_sizes: dict[str, int] = defaultdict(int)
    for code in truth.values():
        code_sizes[code] += 1
    truth_pairs = sum(_pairs(n) for n in code_sizes.values())
    return {
        "transactions": len(with_code),
        "predicted_pairs": predicted_pairs,
        "true_pairs": truth_pairs,
        "true_positive_pairs": true_positive,
        "precision": true_positive / predicted_pairs if predicted_pairs else 1.0,
        "recall": true_positive / truth_pairs if truth_pairs else 1.0,
        "review_pairs": len(result.review),
    }
