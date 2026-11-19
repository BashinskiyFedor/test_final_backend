import pytest

from app.models import StreamOffer
from app.services.weights import WeightError, recalc_weights


def offers(count: int) -> list[StreamOffer]:
    return [StreamOffer.draft(i, f"Offer {i}") for i in range(1, count + 1)]


def shares(items: list[StreamOffer]) -> list[int]:
    return [o.share for o in items]


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, [100]), (3, [34, 33, 33]), (4, [25, 25, 25, 25]), (7, [15, 15, 14, 14, 14, 14, 14])],
)
def test_weights_split_evenly_and_sum_to_100(count, expected):
    items = offers(count)
    recalc_weights(items)
    assert shares(items) == expected


def test_pinned_weight_is_kept_and_rest_is_shared():
    items = offers(5)
    recalc_weights(items)
    items[0].share, items[0].pinned = 25, True
    recalc_weights(items)
    assert shares(items) == [25, 19, 19, 19, 18]


def test_inactive_offers_get_zero_and_lose_pin():
    items = offers(3)
    items[0].pinned = True
    items[0].active = False
    recalc_weights(items)
    assert shares(items) == [0, 50, 50]
    assert not items[0].pinned


def test_not_enough_free_weight_raises():
    items = offers(3)
    items[0].share, items[0].pinned = 99, True
    with pytest.raises(WeightError):
        recalc_weights(items)


def test_no_active_offers_is_a_noop():
    items = offers(2)
    for o in items:
        o.active = False
    recalc_weights(items)
    assert shares(items) == [0, 0]
