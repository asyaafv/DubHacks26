"""CP-SAT reward stacking per the README constraint formulation.

Model (integer cents; Decimal only at the boundaries, ROUND_HALF_UP at the
final monetary rounding per docs/person3-contract.md):

  Variables   x_i in {0,1} per eligible reward, y_c in {0,1} per payment card.
  Constraints max one promo code per checkout; non-combinable pairs
              (x_a + x_b <= 1 when neither reward is stackable); min-spend and
              item/category exclusions enforced during candidate construction;
              total reward savings <= cart_total; exactly one card when the
              user has cards.
  Objective   maximize reward savings + card cashback, exactly linearized as
              RATE_SCALE * S + rate(y) * (cart - S) via AddMultiplicationEquality,
              with a strictly-dominated preference term for deterministic
              tie-breaks (higher savings first, then lowest UUID).

Eligibility policy: cart items are PARTIAL and cart_total is authoritative.
A reward's exclusions remove the listed items that match them from that
reward's discountable base; the unlisted remainder stays eligible (the
Hollister fixture's $50.00 savings depend on this reading). Min-spend is
checked against the authoritative cart_total.

If CP-SAT fails or exceeds its 200 ms budget without a feasible solution, a
greedy fallback produces a valid (possibly suboptimal) stack so /stack always
answers during the demo.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException

from backend.app.schemas import (
    Card,
    ChosenReward,
    Merchant,
    Reward,
    RewardKind,
    RewardStatus,
    StackRequest,
    StackResult,
)
from backend.decisions.common import card_rate, utc

CENTS = Decimal('0.01')
SOLVER_TIME_LIMIT_S = 0.2
RATE_SCALE = 10_000  # card rates as percent * 100 basis-point-like integers


class SolverFailed(Exception):
    """CP-SAT returned no feasible solution within the time budget."""


def _cents(value) -> int:
    return int((Decimal(value) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _money(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(CENTS, rounding=ROUND_HALF_UP)


def _plain(value) -> str:
    """Trim trailing zeros without scientific notation (10.00 -> 10, not 1E+1)."""
    return format(Decimal(value).normalize(), 'f')


def _describe(reward: Reward) -> str:
    if reward.kind == RewardKind.percent_off:
        return f"{_plain(reward.value)}% off"
    if reward.kind in (RewardKind.amount_off, RewardKind.cashback):
        return f"${_money(_cents(reward.value))} {reward.kind.value.replace('_', ' ')}"
    return reward.kind.value.replace('_', ' ')


def _label(reward: Reward) -> str:
    base = f"{reward.merchant_name} {_describe(reward)}"
    return f"{base} ({reward.code})" if reward.code else base


def _resolve_merchant(request: StackRequest, merchants: list[Merchant]) -> Merchant | None:
    by_id = None
    if request.merchant_id:
        by_id = next((m for m in merchants if m.id == request.merchant_id), None)
    by_domain = None
    if request.domain:
        domain = request.domain.strip().lower().rstrip('.')
        bare = domain[4:] if domain.startswith('www.') else domain
        by_domain = next(
            (m for m in merchants
             if m.domain in (domain, bare) or domain in m.aliases or bare in m.aliases),
            None,
        )
    if by_id and by_domain and by_id.id != by_domain.id:
        raise HTTPException(400, 'merchant_id and domain resolve to different merchants')
    return by_id or by_domain


def _excluded_cents(reward: Reward, items) -> tuple[int, list[str]]:
    """Cents of listed cart items this reward's exclusions knock out."""
    total, names = 0, []
    for item in items:
        name = (item.name or '').casefold()
        category = (item.category or '').casefold()
        for exclusion in reward.exclusions:
            needle = exclusion.strip().casefold()
            if needle and (needle == category or needle in name):
                total += _cents(Decimal(item.price) * item.quantity)
                names.append(item.name)
                break
    return total, names


def _savings_cents(reward: Reward, base_cents: int) -> int:
    """Savings this reward yields on its eligible base, in cents."""
    if reward.kind == RewardKind.percent_off:
        raw = (Decimal(base_cents) * Decimal(reward.value) / 100).to_integral_value(rounding=ROUND_HALF_UP)
        savings = int(raw)
        if reward.max_discount is not None:
            savings = min(savings, _cents(reward.max_discount))
        return min(savings, base_cents)
    if reward.kind in (RewardKind.amount_off, RewardKind.cashback,
                       RewardKind.free_item, RewardKind.bogo):
        # Face-value convention (free_item/bogo carry value 1.00), capped by base.
        return min(_cents(reward.value), base_cents)
    return 0  # points have no checkout cash value


def _build_candidates(rewards, request, now, cart_cents):
    """Split rewards into solver candidates and explained exclusions."""
    candidates, excluded = [], []
    for reward in rewards:
        if reward.status != RewardStatus.active:
            excluded.append((reward, f"status is {reward.status.value}"))
            continue
        if reward.starts_at and utc(reward.starts_at) > now:
            excluded.append((reward, f"not valid until {utc(reward.starts_at).date()}"))
            continue
        if reward.expires_at and utc(reward.expires_at) <= now:
            excluded.append((reward, f"expired on {utc(reward.expires_at).date()}"))
            continue
        if reward.min_spend is not None and _cents(reward.min_spend) > cart_cents:
            excluded.append((
                reward,
                f"requires ${_money(_cents(reward.min_spend))} minimum spend, cart is ${_money(cart_cents)}",
            ))
            continue
        excluded_cents, excluded_names = _excluded_cents(reward, request.items)
        base_cents = max(cart_cents - excluded_cents, 0)
        if base_cents == 0:
            excluded.append((reward, 'every cart item matches its exclusions'))
            continue
        savings = _savings_cents(reward, base_cents)
        if savings <= 0:
            excluded.append((reward, 'no cash value at checkout'))
            continue
        candidates.append({
            'reward': reward,
            'savings': savings,
            'base': base_cents,
            'excluded_items': excluded_names,
        })
    # Deterministic order: biggest savings first, then lowest UUID.
    candidates.sort(key=lambda c: (-c['savings'], str(c['reward'].id)))
    return candidates, excluded


def _solve_cpsat(candidates, ranked_cards, cart_cents):
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    n, m = len(candidates), len(ranked_cards)
    x = [model.NewBoolVar(f'reward_{i}') for i in range(n)]
    y = [model.NewBoolVar(f'card_{j}') for j in range(m)]

    if m:
        model.AddExactlyOne(y)  # exactly one payment card

    coded = [x[i] for i in range(n) if candidates[i]['reward'].code]
    if len(coded) > 1:
        model.Add(sum(coded) <= 1)  # max one promo code per checkout

    for i in range(n):  # non-combinable pairs: neither explicitly stackable
        for j in range(i + 1, n):
            if not candidates[i]['reward'].stackable and not candidates[j]['reward'].stackable:
                model.Add(x[i] + x[j] <= 1)

    savings = model.NewIntVar(0, cart_cents, 'reward_savings')
    model.Add(savings == sum(candidates[i]['savings'] * x[i] for i in range(n)))
    remaining = model.NewIntVar(0, cart_cents, 'remaining')
    model.Add(remaining == cart_cents - savings)

    max_rate = max((c['rate_scaled'] for c in ranked_cards), default=0)
    rate = model.NewIntVar(0, max_rate, 'rate')
    model.Add(rate == sum(ranked_cards[j]['rate_scaled'] * y[j] for j in range(m)))
    cashback_product = model.NewIntVar(0, max_rate * cart_cents, 'cashback_product')
    model.AddMultiplicationEquality(cashback_product, [rate, remaining])

    # main == RATE_SCALE * total savings in cents (rewards + cashback), exact.
    main = RATE_SCALE * savings + cashback_product
    # Preference term strictly below one unit of main: deterministic tie-break
    # toward earlier candidates/cards in their sorted orders.
    scale = (n + m + 1) ** 2
    preference = sum((n - i) * x[i] for i in range(n)) + sum((m - j) * y[j] for j in range(m))
    model.Maximize(main * scale + preference)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_S
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 0
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SolverFailed(solver.StatusName(status))

    chosen = [i for i in range(n) if solver.Value(x[i]) == 1]
    card_index = next((j for j in range(m) if solver.Value(y[j]) == 1), None)
    return chosen, card_index, 'optimal' if status == cp_model.OPTIMAL else 'feasible'


def _solve_greedy(candidates, ranked_cards, cart_cents):
    """Valid (not necessarily optimal) stack when CP-SAT is unavailable."""
    chosen, total, used_code = [], 0, False
    for i, candidate in enumerate(candidates):  # already sorted by savings desc
        reward = candidate['reward']
        if reward.code and used_code:
            continue
        if not reward.stackable and any(not candidates[k]['reward'].stackable for k in chosen):
            continue
        if total + candidate['savings'] > cart_cents:
            continue
        chosen.append(i)
        total += candidate['savings']
        used_code = used_code or bool(reward.code)
    return chosen, (0 if ranked_cards else None), 'greedy_fallback'


def solve_stack(
    request: StackRequest,
    *,
    user_id,
    rewards: list[Reward],
    cards: list[Card],
    merchants: list[Merchant],
    now=None,
) -> StackResult:
    """Pure stacking decision over already-loaded rewards/cards/merchants."""
    now = utc(now)
    cart_cents = _cents(request.cart_total)
    merchant = _resolve_merchant(request, merchants)

    mine = [r for r in rewards if r.user_id == user_id]
    if request.merchant_id:
        scoped = [r for r in mine if r.merchant_id == request.merchant_id]
    elif merchant:
        scoped = [r for r in mine if r.merchant_id == merchant.id]
    else:
        scoped = mine

    candidates, excluded = _build_candidates(scoped, request, now, cart_cents)

    category = merchant.category if merchant else None
    mcc = merchant.mcc if merchant else None
    ranked_cards = sorted(
        ({
            'card': card,
            'rate': card_rate(card, category, mcc),
            'rate_scaled': int((card_rate(card, category, mcc) * 100).to_integral_value(rounding=ROUND_HALF_UP)),
        } for card in cards if card.user_id == user_id),
        key=lambda c: (-c['rate_scaled'], str(c['card'].id)),
    )

    try:
        chosen_indices, card_index, solver_status = _solve_cpsat(candidates, ranked_cards, cart_cents)
    except Exception:  # noqa: BLE001 - any solver failure degrades to greedy
        chosen_indices, card_index, solver_status = _solve_greedy(candidates, ranked_cards, cart_cents)

    chosen_set = set(chosen_indices)
    chosen_rewards, explanations, reward_savings_cents = [], [], 0
    for order, i in enumerate(sorted(chosen_indices), start=1):
        candidate = candidates[i]
        reward = candidate['reward']
        chosen_rewards.append(ChosenReward(
            reward_id=reward.id,
            reward=reward,
            savings=_money(candidate['savings']),
            applied_order=order,
        ))
        reward_savings_cents += candidate['savings']
        note = f"Applied {_label(reward)}: saves ${_money(candidate['savings'])}"
        if candidate['excluded_items']:
            note += f" on ${_money(candidate['base'])} eligible (excluded: {', '.join(candidate['excluded_items'])})"
        explanations.append(note + '.')

    alternatives = []
    chosen_has_code = any(candidates[i]['reward'].code for i in chosen_set)
    for i, candidate in enumerate(candidates):
        if i in chosen_set:
            continue
        reward = candidate['reward']
        if reward.code and chosen_has_code:
            reason = 'only one promo code can be applied per checkout'
        elif not reward.stackable and any(not candidates[k]['reward'].stackable for k in chosen_set):
            reason = 'not stackable with the chosen reward'
        else:
            reason = 'lower total savings than the chosen combination'
        explanations.append(f"Skipped {_label(reward)} (${_money(candidate['savings'])}): {reason}.")
        alternatives.append(ChosenReward(
            reward_id=reward.id,
            reward=reward,
            savings=_money(candidate['savings']),
            applied_order=0,
        ))
    for reward, reason in excluded:
        explanations.append(f"Excluded {_label(reward)}: {reason}.")

    best_card = None
    cashback_cents = 0
    remaining_cents = cart_cents - reward_savings_cents
    if card_index is not None:
        entry = ranked_cards[card_index]
        best_card = entry['card']
        cashback_cents = int((Decimal(entry['rate']) * remaining_cents / 100)
                             .to_integral_value(rounding=ROUND_HALF_UP))
        where = f"MCC {mcc} ({category})" if merchant else 'this purchase'
        explanations.append(
            f"Pay with {best_card.name}: {_plain(entry['rate'])}% back on {where}"
            f" → ${_money(cashback_cents)} cashback."
        )
        for other in ranked_cards:
            if other['card'].id != best_card.id:
                explanations.append(
                    f"Skipped {other['card'].name}: earns only {_plain(other['rate'])}% here."
                )

    total_savings_cents = reward_savings_cents + cashback_cents
    total_savings = _money(total_savings_cents)
    savings_percent = (
        (Decimal(total_savings_cents) / cart_cents * 100).quantize(CENTS, rounding=ROUND_HALF_UP)
        if cart_cents else Decimal('0.00')
    )

    parts = [
        f"Applied {c.reward.code or _describe(c.reward)} for {_describe(c.reward)} (${c.savings} savings)"
        for c in chosen_rewards
    ]
    if best_card and cashback_cents:
        parts.append(f"Use {best_card.name} for ${_money(cashback_cents)} cashback")
    summary = '. '.join(parts) + f". Total savings: ${total_savings} ({savings_percent}%)." \
        if parts else f"No applicable rewards. Total savings: ${total_savings}."

    return StackResult(
        chosen_rewards=chosen_rewards,
        recommended_card=best_card,
        card_cashback=_money(cashback_cents),
        original_price=_money(cart_cents),
        final_price=_money(cart_cents - reward_savings_cents),
        total_savings=total_savings,
        savings_percent=savings_percent,
        explanation=summary,
        explanations=explanations,
        alternatives=alternatives,
        solver_status=solver_status,
    )
