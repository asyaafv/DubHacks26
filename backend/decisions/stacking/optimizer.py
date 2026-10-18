"""CP-SAT models binary rewards, sequential cents, allocation, AND card choice."""
from time import monotonic

from ortools.sat.python import cp_model

from .domain import SCALE, Problem, card_allowed, compatible, urgency
from .reference import evaluate, exhaustive


class VerificationError(RuntimeError):
    pass


class SolverUnavailable(RuntimeError):
    pass


def optimize(problem: Problem, *, time_limit=3.0):
    if time_limit < 0:
        raise ValueError('Solver time limit cannot be negative')
    model = cp_model.CpModel()
    upper = problem.total

    def money(name):
        return model.new_int_var(0, upper, name)

    def rounded(base, percent, name):
        result = money(name)
        model.add_division_equality(result, base * percent + SCALE // 2, SCALE)
        return result

    xs = [model.new_bool_var(f'reward_{i}') for i in range(len(problem.offers))]
    ys = [model.new_bool_var(f'card_{i}') for i in range(len(problem.cards))]
    model.add_exactly_one(ys)
    model.add(sum(x for x, o in zip(xs, problem.offers) if o.reward.code) <= 1)
    for i, a in enumerate(problem.offers):
        for j, b in enumerate(problem.offers[:i]):
            if not compatible(a, b):
                model.add(xs[i] + xs[j] <= 1)
        for j, card in enumerate(problem.cards):
            if not card_allowed(a, card):
                model.add(xs[i] + ys[j] <= 1)
    balances = list(problem.balances)
    reward_cbs = []
    amounts = []
    for idx, (x, o) in enumerate(zip(xs, problem.offers)):
        base = money(f'eligible_{idx}')
        model.add(base == sum(balances[j] for j in o.buckets))
        raw = rounded(base, o.percent, f'raw_{idx}') if o.percent is not None else o.amount
        capped = money(f'capped_{idx}')
        model.add_min_equality(capped, [base, raw, o.cap])
        saved = money(f'saved_{idx}')
        model.add(saved == capped).only_enforce_if(x)
        model.add(saved == 0).only_enforce_if(x.Not())
        amounts.append(saved)
        if o.reward.kind.value == 'cashback':
            reward_cbs.append(saved)
            continue
        # Proportional allocation allows overlapping exclusion scopes to compound
        # against actual remaining merchandise, never the original subtotal twice.
        denominator = model.new_int_var(1, max(upper, 1), f'denom_{idx}')
        model.add_max_equality(denominator, [base, 1])
        shares = {}
        for j in o.buckets:
            numerator = model.new_int_var(0, upper * problem.balances[j], f'product_{idx}_{j}')
            model.add_multiplication_equality(numerator, [saved, balances[j]])
            shares[j] = money(f'share_{idx}_{j}')
            model.add_division_equality(shares[j], numerator, denominator)
        remaining = money(f'pennies_{idx}')
        model.add(remaining == saved - sum(shares.values()))
        updated = list(balances)
        for j in o.buckets:
            positive = model.new_bool_var(f'positive_{idx}_{j}')
            capacity = model.new_bool_var(f'capacity_{idx}_{j}')
            extra = model.new_bool_var(f'extra_{idx}_{j}')
            model.add(remaining >= 1).only_enforce_if(positive)
            model.add(remaining == 0).only_enforce_if(positive.Not())
            model.add(balances[j] >= shares[j] + 1).only_enforce_if(capacity)
            model.add(balances[j] <= shares[j]).only_enforce_if(capacity.Not())
            model.add_min_equality(extra, [positive, capacity])
            updated[j] = money(f'balance_{idx}_{j}')
            model.add(updated[j] == balances[j] - shares[j] - extra)
            next_remaining = money(f'pennies_after_{idx}_{j}')
            model.add(next_remaining == remaining - extra)
            remaining = next_remaining
        model.add(remaining == 0)
        balances = updated
    final = money('checkout_price')
    model.add(final == sum(balances))
    suppress = model.new_bool_var('suppress_card_earnings')
    suppressors = [x for x, o in zip(xs, problem.offers) if o.terms.suppress_card_cashback]
    model.add_max_equality(suppress, suppressors or [0])
    card_cb = money('card_cashback')
    for j, percentage in enumerate(problem.rates):
        raw_cb = rounded(final, percentage, f'card_raw_{j}')
        model.add(card_cb == raw_cb).only_enforce_if([ys[j], suppress.Not()])
    model.add(card_cb == 0).only_enforce_if(suppress)
    total = model.new_int_var(0, upper * (len(reward_cbs) + 2), 'complete_savings')
    model.add(total == upper - final + sum(reward_cbs) + card_cb)
    # Strict lexicographic phases: no urgency weight can ever cost a cent.
    objectives = [total, upper - final, -sum(xs)]
    objectives += [xs[i] for i in sorted(range(len(xs)), key=lambda i: urgency(problem.offers[i].reward))]
    objectives += [-sum(i * y for i, y in enumerate(ys))]
    deadline = monotonic() + time_limit
    best, status_name = None, 'unknown'
    for objective in objectives:
        remaining_time = deadline - monotonic()
        if remaining_time <= 0:
            status_name = 'feasible' if best else 'unknown'
            break
        model.maximize(objective)
        solver = cp_model.CpSolver()
        # OR-Tools 9.15 duplicate-column presolve aborts on some variable
        # division/allocation models. Disable presolve; search remains CP-SAT.
        solver.parameters.cp_model_presolve = False
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        solver.parameters.max_time_in_seconds = remaining_time
        status = solver.solve(model)
        if status == cp_model.MODEL_INVALID:
            raise VerificationError('Invalid CP-SAT model: ' + model.validate())
        if status == cp_model.INFEASIBLE:
            raise VerificationError('Model rejected the always-valid empty checkout baseline')
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            status_name = 'feasible' if best else 'unknown'
            break
        selected = tuple(i for i, x in enumerate(xs) if solver.value(x))
        card = next(i for i, y in enumerate(ys) if solver.value(y))
        best = evaluate(problem, selected, card)
        if (best is None or best.total != solver.value(total) or best.final != solver.value(final)
                or best.card_cashback != solver.value(card_cb)
                or best.savings != tuple(solver.value(amounts[i]) for i in selected)):
            raise VerificationError('CP-SAT arithmetic disagrees with independent replay')
        if status != cp_model.OPTIMAL:
            status_name = 'feasible'
            break
        model.add(objective == solver.value(objective))
        status_name = 'optimal'
    if len(problem.offers) <= 8:
        reference = exhaustive(problem)
        if best is None:
            return reference, 'reference_verified_solver_timeout'
        if best.key != reference.key and status_name == 'optimal':
            raise VerificationError('CP-SAT optimum disagrees with exhaustive reference')
        if best.key > reference.key:
            raise VerificationError('CP-SAT candidate exceeds exhaustive reference')
    if best is None:
        raise SolverUnavailable('CP-SAT timed out without a feasible recommendation')
    return best, status_name
