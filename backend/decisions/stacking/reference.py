"""Independent exhaustive oracle: no CP-SAT imports or solver result reuse."""
from dataclasses import dataclass
from itertools import product

from .domain import Problem, SCALE, urgency


@dataclass(frozen=True)
class Evaluation:
    selected: tuple[int, ...]
    card_index: int
    savings: tuple[int, ...]
    final: int
    reward_cashback: int
    card_cashback: int
    total: int
    key: tuple


def evaluate(problem: Problem, selected, card_index):
    """Replay one checkout using Python integers, including allocation and payment."""
    selected = tuple(sorted(selected))
    offers = [problem.offers[i] for i in selected]
    if sum(bool(o.reward.code) for o in offers) > 1:
        return None
    for i, a in enumerate(offers):
        for b in offers[i + 1:]:
            if not (a.reward.stackable and b.reward.stackable):
                return None
            if a.terms.compatible_reward_ids is not None and b.reward.id not in a.terms.compatible_reward_ids:
                return None
            if b.terms.compatible_reward_ids is not None and a.reward.id not in b.terms.compatible_reward_ids:
                return None
    card = problem.cards[card_index]
    for o in offers:
        t = o.terms
        if ((t.allowed_card_ids is not None and (card is None or card.id not in t.allowed_card_ids))
                or (t.allowed_networks is not None and (card is None or card.network.value not in t.allowed_networks))
                or (t.allowed_issuers is not None and (card is None or card.issuer.casefold() not in
                                                      {s.casefold() for s in t.allowed_issuers}))):
            return None
    balances = list(problem.balances)
    savings, reward_cashback = [], 0
    for o in offers:
        base = sum(balances[i] for i in o.buckets)
        raw = (base * o.percent + SCALE // 2) // SCALE if o.percent is not None else o.amount
        saved = min(base, raw, o.cap)
        savings.append(saved)
        if o.reward.kind.value == 'cashback':
            reward_cashback += saved
            continue
        # Floor proportional shares, then distribute remaining pennies in stable
        # cart-line order. Aggregate reward rounding occurs ONCE, half up.
        allocated = {i: saved * balances[i] // max(base, 1) for i in o.buckets}
        pennies = saved - sum(allocated.values())
        for i in o.buckets:
            extra = int(pennies > 0 and balances[i] > allocated[i])
            balances[i] -= allocated[i] + extra
            pennies -= extra
        assert pennies == 0
    final = sum(balances)
    cb = 0 if any(o.terms.suppress_card_cashback for o in offers) else (
        final * problem.rates[card_index] + SCALE // 2) // SCALE
    total = problem.total - final + reward_cashback + cb
    priority = sorted(range(len(problem.offers)), key=lambda i: urgency(problem.offers[i].reward))
    key = (total, problem.total - final, -len(selected),
           tuple(int(i in selected) for i in priority), -card_index)
    return Evaluation(selected, card_index, tuple(savings), final, reward_cashback, cb, total, key)


def exhaustive(problem: Problem):
    """Enumerate ALL subsets AND payment options against the complete objective."""
    if len(problem.offers) > 8 or len(problem.cards) > 33:
        raise ValueError('Reference evaluator is bounded to eight eligible rewards')
    best = None
    for bits in product((False, True), repeat=len(problem.offers)):
        selected = tuple(i for i, bit in enumerate(bits) if bit)
        for card in range(len(problem.cards)):
            candidate = evaluate(problem, selected, card)
            if candidate is not None and (best is None or candidate.key > best.key):
                best = candidate
    return best
