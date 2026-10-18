"""Pure recommendation service plus a thin foundation repository adapter."""
from decimal import Decimal, ROUND_HALF_UP

from backend.app.schemas import ChosenReward, StackResult
from backend.decisions.common import utc
from .domain import dollars, prepare
from .optimizer import optimize


def solve_stacking(request, rewards, cards, merchant, memberships=(), *, now=None,
                   terms=None, time_limit=3.0):
    """No database, clock, web calls, or LLM in monetary evaluation."""
    problem = prepare(request, rewards, cards, list(memberships), merchant, now=now, terms=terms)
    result, status = optimize(problem, time_limit=time_limit)
    chosen, sentences = [], []
    for order, (i, saved) in enumerate(zip(result.selected, result.savings), start=1):
        reward = problem.offers[i].reward
        chosen.append(ChosenReward(reward_id=reward.id, reward=reward,
                                   savings=dollars(saved), applied_order=order))
        label = 'reward cashback (after checkout)' if reward.kind.value == 'cashback' else 'immediate discount'
        expiry = f'; expires {utc(reward.expires_at).isoformat()}' if reward.expires_at else ''
        sentences.append(f'Reward {reward.id}: ${dollars(saved)} {label}{expiry}.')
    card = problem.cards[result.card_index]
    sentences.append(f'Checkout: ${dollars(problem.total)} - ${dollars(problem.total - result.final)} immediate discounts = ${dollars(result.final)}.')
    if card:
        percent = Decimal(problem.rates[result.card_index]) / 1_000_000
        if any(problem.offers[i].terms.suppress_card_cashback for i in result.selected):
            sentences.append(f'{card.name}: card earnings excluded by selected payment terms.')
        else:
            sentences.append(f'{card.name}: {percent}% of ${dollars(result.final)} = ${dollars(result.card_cashback)} card cashback after checkout.')
    sentences.append(f'Total savings: ${dollars(result.total)} (${dollars(result.reward_cashback)} reward cashback; ${dollars(result.card_cashback)} card cashback).')
    sentences.extend(problem.notes)
    if status != 'optimal':
        sentences.append(f'Solver status: {status}; CP-SAT optimality was not established.')
    return StackResult(
        chosen_rewards=chosen, recommended_card=card, card_cashback=dollars(result.card_cashback),
        original_price=dollars(problem.total), final_price=dollars(result.final),
        total_savings=dollars(result.total),
        savings_percent=((Decimal(result.total) * 100 / problem.total).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                         if problem.total else Decimal('0.00')),
        explanation=' '.join(sentences), solver_status=status,
    )


async def load_checkout(repo, request, *, now=None):
    """Use ONLY the foundation's scoped repository; no replacement storage layer.

    list_rewards redacts codes. Explicit owned reads are necessary BEFORE solving
    to enforce the one-code rule, even for rewards that ultimately are not selected.
    """
    now = utc(now)
    merchant = await repo.resolve_merchant(merchant_id=request.merchant_id, domain=request.domain)
    rewards = []
    for summary in await repo.list_rewards(now=now):
        if merchant is None or summary.merchant_id != merchant.id:
            continue
        reward = await repo.get_reward(summary.id, reveal_code=True)
        if reward is not None:
            rewards.append(reward)
    wallet = await repo.get_wallet(now=now)
    return rewards, wallet.cards, merchant, wallet.memberships
