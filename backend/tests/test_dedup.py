"""Synthetic addresses modelled on real PPR patterns (no real records)."""

from datetime import date

from app.agents.deduplication import Txn, cluster, evaluate_against_eircode
from app.validators.address import normalize_address, normalize_eircode


def t(id, address, sale_date, eircode=None):
    return Txn.build(id, address, eircode, date.fromisoformat(sale_date))


def same(result, a, b):
    return any(a in g and b in g for g in result.groups)


def test_normalize_address():
    n = normalize_address("Apartment No 7, Saint Example's Court, Dublin 6w")
    assert n.numbers == ("apt:7",)
    assert n.district == "6w"
    assert n.name == "st example s ct"
    assert normalize_address("7 St. Example's Ct, D6W").name == n.name
    assert normalize_address("Teach Ó Néill, Baile").name == "teach o neill baile"
    assert normalize_address("38/39 Sample St").numbers == ("38", "39")


def test_normalize_eircode():
    assert normalize_eircode("d08 xy12") == "D08XY12"
    assert normalize_eircode("D6W AB12") == "D6WAB12"
    assert normalize_eircode("12345") is None


def test_repeat_sale_with_formatting_differences_is_linked():
    r = cluster([
        t(1, "12 Example Road, Rathsample, Dublin 6", "2012-05-01"),
        t(2, "12 EXAMPLE RD, RATHSAMPLE, DUBLIN 6", "2019-07-15"),
    ])  # fmt: skip
    assert same(r, 1, 2)


def test_typo_is_linked_by_fuzzy_match():
    r = cluster([
        t(1, "22 Luttrelstown Sample Court, Castleknock", "2013-01-10"),
        t(2, "22 Luttrellstown Sample Court, Castleknock", "2021-03-02"),
    ])  # fmt: skip
    assert same(r, 1, 2)
    assert [(link.a, link.b) for link in r.fuzzy_links] == [(1, 2)]


def test_neighbouring_apartments_are_never_merged():
    r = cluster([
        t(1, "Apartment 4, Sample Court, Dublin 2", "2015-02-01"),
        t(2, "Apartment 5, Sample Court, Dublin 2", "2016-03-01"),
        t(3, "4 Sample Court, Dublin 2", "2018-04-01"),
    ])  # fmt: skip
    assert not same(r, 1, 2)
    # "Apartment 4" (unit in a block) vs "4" (could be a house): not provably the same.
    assert not same(r, 1, 3)


def test_unit_and_block_numbers_keep_their_roles():
    r = cluster([
        t(1, "Apartment 2 Block 6, Sample Priory", "2019-01-01"),
        t(2, "Block 2 Apt 6, Sample Priory", "2023-01-01"),
    ])  # fmt: skip
    assert not same(r, 1, 2)


def test_different_street_type_is_a_different_property():
    r = cluster([
        t(1, "7 Golden Sample Walk, Rush", "2021-01-01"),
        t(2, "7 Golden Sample Way, Rush", "2024-01-01"),
    ])  # fmt: skip
    assert not same(r, 1, 2)
    assert r.review == []


def test_townland_address_without_number_needs_eircode():
    r = cluster([
        t(1, "Sampletown, Newcastle, Dublin", "2022-01-01"),
        t(2, "Sampletown, Newcastle, Dublin", "2023-06-01"),
    ])  # fmt: skip
    assert not same(r, 1, 2)


def test_same_street_in_different_districts_is_not_merged():
    r = cluster([
        t(1, "10 Main Street, Dublin 8", "2014-01-01"),
        t(2, "10 Main Street, Dublin 6", "2017-01-01"),
    ])  # fmt: skip
    assert not same(r, 1, 2)


def test_address_without_district_cannot_bridge_two_districts():
    r = cluster([
        t(1, "10 Main Street, Dublin 8", "2014-01-01"),
        t(2, "10 Main Street", "2016-01-01"),
        t(3, "10 Main Street, Dublin 6", "2017-01-01"),
    ])  # fmt: skip
    assert not same(r, 1, 3)


def test_different_eircodes_block_identical_addresses():
    r = cluster([
        t(1, "1 Sample Lane", "2016-01-01", "D08AB12"),
        t(2, "1 Sample Lane", "2020-01-01", "D08CD34"),
    ])  # fmt: skip
    assert not same(r, 1, 2)
    assert r.stats["refused_eircode_differs"] == 1


def test_same_eircode_links_different_spellings():
    r = cluster([
        t(1, "Rose Sample Cottage, Howth", "2011-01-01", "D13AB12"),
        t(2, "The Rose Sample Cottage, Howth Road", "2022-01-01", "D13AB12"),
    ])  # fmt: skip
    assert same(r, 1, 2)


def test_units_sold_on_same_date_go_to_review_not_merged():
    r = cluster([
        t(1, "Unit 1, Test Quay, Dublin 1", "2024-03-10"),
        t(2, "Unit 1, Test Quay, Dublin 1", "2024-03-10"),
    ])  # fmt: skip
    assert not same(r, 1, 2)
    assert [(p.a, p.b, p.vetoes) for p in r.review] == [(1, 2, ("SAME_SALE_DATE",))]


def test_moderate_similarity_goes_to_review():
    r = cluster([
        t(1, "5 Sample Park Avenue, Lucan", "2012-01-01"),
        t(2, "5 Sample Park, Lucan", "2019-01-01"),
    ])  # fmt: skip
    assert not same(r, 1, 2)
    assert [p.reason for p in r.review] == ["fuzzy"]


def test_evaluation_uses_eircode_as_truth():
    txns = [
        t(1, "3 Sample Grove, Dublin 9", "2016-01-01", "D09AA11"),
        t(2, "3 Sample Grove, Dublin 9", "2021-01-01", "D09AA11"),
        t(3, "4 Sample Grove, Dublin 9", "2021-02-01", "D09BB22"),
    ]
    m = evaluate_against_eircode(txns)
    assert (m["precision"], m["recall"], m["true_pairs"]) == (1.0, 1.0, 1)


def test_placeholder_eircode_does_not_merge_different_addresses():
    r = cluster([
        t(1, "33 Sample Road, Dublin 7", "2025-10-24", "A123456"),
        t(2, "109 Main Street, Swords", "2025-12-22", "A123456"),
        t(3, "33 Sample Rd, Dublin 7", "2015-01-01"),
    ])  # fmt: skip
    assert not same(r, 1, 2)
    assert same(r, 1, 3)  # the address still links the real repeat sale
    assert r.stats["untrusted_eircodes"] == 1
