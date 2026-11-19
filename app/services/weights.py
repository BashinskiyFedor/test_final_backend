from collections.abc import Sequence

from app.core.errors import InvalidInputError
from app.models.stream import StreamOffer

TOTAL_WEIGHT = 100


class WeightError(InvalidInputError):
    pass


def recalc_weights(offers: Sequence[StreamOffer]) -> None:
    """Пересчитывает доли активных офферов так, чтобы в сумме было 100%.

    Запиненные доли не трогаются, остаток делится поровну между остальными
    (остаток от деления раздаётся по одному проценту первым офферам).
    Неактивные офферы получают 0% и теряют пин.
    """
    for offer in offers:
        if not offer.active:
            offer.deactivate()

    active = [o for o in offers if o.active]
    pinned_total = sum(o.share for o in active if o.pinned)
    free = [o for o in active if not o.pinned]
    if not free:
        return

    remaining = TOTAL_WEIGHT - pinned_total
    if remaining < len(free):
        raise WeightError(
            f"Недостаточно свободного веса: запиненные офферы занимают {pinned_total}%, "
            f"а ещё нужно распределить {len(free)} офф."
        )
    base, extra = divmod(remaining, len(free))
    for i, offer in enumerate(free):
        offer.share = base + (1 if i < extra else 0)
