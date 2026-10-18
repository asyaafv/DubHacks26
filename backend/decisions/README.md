# Decisions Module (Person 3)

Data storage, stacking optimization, lookup, and real-time sync.

## Ownership

- Postgres + pgvector schema & queries
- pgcrypto for reward code encryption
- `GET/POST /wallet`
- `POST /stack` - CP-SAT stacking engine
- `POST /lookup` - Reward ranking
- `GET /sync` - Polling endpoint
- `GET /events` - SSE real-time updates
- Daily expiry job

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Postgres + pgvector                     │
├─────────────┬─────────────┬─────────────┬──────────────────┤
│   rewards   │    cards    │ memberships │    merchants     │
│  (encrypted │             │             │   (embeddings)   │
│    codes)   │             │             │                  │
└─────────────┴─────────────┴─────────────┴──────────────────┘
        ↑                           ↑
        │                           │
   ┌────┴────┐                 ┌────┴────┐
   │ Stacking│                 │  Lookup │
   │ (CP-SAT)│                 │ (score) │
   └─────────┘                 └─────────┘
```

## Database Schema

See `docs/schema.sql` for full DDL.

Key tables:
- `users` - User accounts
- `rewards` - Extracted rewards (code encrypted via pgcrypto)
- `cards` - Payment cards with category rates (JSONB)
- `memberships` - Store loyalty memberships
- `merchants` - Merchant catalog with embeddings (pgvector)

## CP-SAT Stacking Engine

### Constraint Formulation

```
Variables:
  x_i ∈ {0, 1}  for each applicable reward i

Objective:
  maximize: Σ(savings_i × x_i) + card_cashback

Constraints:
  1. Non-combinable pairs: x_a + x_b ≤ 1
     (when neither reward has stackable=True)
  
  2. Min spend: Σ(min_spend_i × x_i) ≤ cart_total
     (only apply rewards where min_spend is met)
  
  3. Max one promo code: Σ(has_code_i × x_i) ≤ 1
     (most checkouts only accept one code)
  
  4. Exclusions: Skip rewards that exclude cart items
```

### Implementation

```python
from ortools.sat.python import cp_model

def solve_stacking(
    rewards: list[Reward],
    cart_total: Decimal,
    cart_items: list[CartItem],
    cards: list[Card],
    merchant: Merchant | None
) -> StackResult:
    model = cp_model.CpModel()
    
    # Create boolean variable for each reward
    x = {}
    for i, reward in enumerate(rewards):
        x[i] = model.NewBoolVar(f'reward_{i}')
    
    # Constraint 1: Non-combinable pairs
    for i, r1 in enumerate(rewards):
        for j, r2 in enumerate(rewards):
            if i < j and not r1.stackable and not r2.stackable:
                model.Add(x[i] + x[j] <= 1)
    
    # Constraint 2: Min spend must be met
    for i, reward in enumerate(rewards):
        if reward.min_spend and reward.min_spend > cart_total:
            model.Add(x[i] == 0)
    
    # Constraint 3: Max one promo code
    promo_code_rewards = [i for i, r in enumerate(rewards) if r.code]
    if len(promo_code_rewards) > 1:
        model.Add(sum(x[i] for i in promo_code_rewards) <= 1)
    
    # Calculate savings for each reward
    savings = []
    for i, reward in enumerate(rewards):
        s = calculate_savings(reward, cart_total)
        savings.append(int(s * 100))  # Convert to cents for integer math
    
    # Objective: maximize total savings
    model.Maximize(sum(savings[i] * x[i] for i, _ in enumerate(rewards)))
    
    # Solve
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    
    # Build result
    chosen = []
    total_savings = Decimal("0")
    order = 1
    
    for i, reward in enumerate(rewards):
        if solver.Value(x[i]) == 1:
            s = Decimal(savings[i]) / 100
            chosen.append(ChosenReward(
                reward_id=reward.id,
                reward=reward,
                savings=s,
                applied_order=order
            ))
            total_savings += s
            order += 1
    
    # Find best card
    best_card, card_cashback = find_best_card(
        cards, merchant, cart_total - total_savings
    )
    
    # Build explanation
    explanation = build_explanation(chosen, best_card, card_cashback)
    
    return StackResult(
        chosen_rewards=chosen,
        recommended_card=best_card,
        card_cashback=card_cashback,
        original_price=cart_total,
        final_price=cart_total - total_savings,
        total_savings=total_savings + card_cashback,
        savings_percent=(total_savings + card_cashback) / cart_total * 100,
        explanation=explanation,
        solver_status="optimal" if status == cp_model.OPTIMAL else "feasible"
    )
```

### Brute Force Cross-Check

For small reward sets (≤8), verify CP-SAT solution with brute force:

```python
from itertools import combinations

def brute_force_verify(rewards: list[Reward], cart_total: Decimal) -> Decimal:
    """Verify optimal solution with brute force enumeration."""
    best_savings = Decimal("0")
    
    for r in range(1, len(rewards) + 1):
        for combo in combinations(enumerate(rewards), r):
            if is_valid_combination([rw for _, rw in combo]):
                savings = sum(calculate_savings(rw, cart_total) for _, rw in combo)
                best_savings = max(best_savings, savings)
    
    return best_savings
```

## Lookup Ranking

### Formula

```
score = value_usd × match × (1 + exp(-days_left/3))
```

Where:
- `value_usd`: Estimated USD value of reward (normalized 0-1)
- `match`: Merchant match score (1.0 exact, 0.7 category, 0.5 other)
- `urgency`: Exponential urgency based on days until expiry

### Implementation

```python
import math

def rank_rewards(
    rewards: list[Reward],
    merchant: Merchant | None,
    limit: int = 3
) -> list[ScoredReward]:
    now = datetime.utcnow()
    scored = []
    
    for reward in rewards:
        # Value component (0-1, assume max ~$50 value)
        if reward.kind == RewardKind.percent_off:
            value_usd = float(reward.value) / 2  # Assume ~50% utilization
        elif reward.kind in (RewardKind.amount_off, RewardKind.cashback):
            value_usd = float(reward.value)
        else:
            value_usd = 5.0  # Default for free items, BOGO, points
        
        value_component = min(value_usd / 50.0, 1.0)
        
        # Match component
        match_component = 0.5
        if merchant:
            if reward.merchant_id == merchant.id:
                match_component = 1.0
            elif reward.category == merchant.category:
                match_component = 0.7
        
        # Urgency component
        days_until_expiry = None
        urgency_component = 1.0
        if reward.expires_at:
            delta = reward.expires_at - now
            days_until_expiry = max(0, delta.days)
            urgency_component = 1 + math.exp(-days_until_expiry / 3.0)
        
        score = value_component * match_component * urgency_component
        
        scored.append(ScoredReward(
            reward=reward,
            score=score,
            value_component=value_component,
            match_component=match_component,
            urgency_component=urgency_component,
            days_until_expiry=days_until_expiry
        ))
    
    # Sort by score descending
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:limit]
```

## SSE Events

### Event Types

| Type | Trigger |
|------|---------|
| `reward_added` | New reward inserted |
| `reward_expiring` | Reward expires in <24 hours |
| `reward_updated` | Reward status changed |
| `reward_used` | Reward marked as used |
| `sync_complete` | Initial connection established |

### Implementation

```python
from fastapi import Request
from fastapi.responses import StreamingResponse
import asyncio

async def event_generator(user_id: UUID):
    # Send initial sync event
    yield format_sse(Event(
        event_type=EventType.sync_complete,
        user_id=user_id,
        data={"message": "Connected"}
    ))
    
    # Subscribe to Postgres NOTIFY channel
    # Or poll for changes every few seconds
    while True:
        events = await get_pending_events(user_id)
        for event in events:
            yield format_sse(event)
        await asyncio.sleep(5)

def format_sse(event: Event) -> str:
    return f"event: {event.event_type.value}\ndata: {event.model_dump_json()}\n\n"

@app.get("/events")
async def sse_events(request: Request, x_user_id: str = Header(None)):
    user_id = get_user_id(x_user_id)
    return StreamingResponse(
        event_generator(user_id),
        media_type="text/event-stream"
    )
```

## Daily Expiry Job

```python
async def expire_rewards():
    """Mark expired rewards and notify users."""
    now = datetime.utcnow()
    
    # Mark expired
    expired = await db.execute("""
        UPDATE rewards 
        SET status = 'expired', updated_at = NOW()
        WHERE status = 'active' AND expires_at < $1
        RETURNING id, user_id
    """, now)
    
    # Queue expiring notifications (24 hours)
    expiring = await db.fetch("""
        SELECT id, user_id, expires_at 
        FROM rewards
        WHERE status = 'active' 
        AND expires_at BETWEEN $1 AND $2
    """, now, now + timedelta(hours=24))
    
    for reward in expiring:
        await queue_event(Event(
            event_type=EventType.reward_expiring,
            user_id=reward['user_id'],
            reward_id=reward['id'],
            data={"expires_at": reward['expires_at'].isoformat()}
        ))
```

## Encryption (pgcrypto)

Reward codes are encrypted at rest:

```sql
-- Encrypt
INSERT INTO rewards (code_encrypted, ...)
VALUES (pgp_sym_encrypt($1, $encryption_key), ...);

-- Decrypt
SELECT pgp_sym_decrypt(code_encrypted, $encryption_key) as code
FROM rewards WHERE id = $1;
```

## Acceptance Criteria

- [ ] All queries filtered by `user_id`
- [ ] Reward codes encrypted at rest
- [ ] CP-SAT solver respects all constraints
- [ ] Brute force cross-check for small sets
- [ ] Explanation text generated from solver output
- [ ] Lookup returns top 3 by ranking formula
- [ ] SSE events sent on reward changes
- [ ] Expired rewards marked daily
- [ ] Sync endpoint returns changes since timestamp

## Dependencies

```
ortools>=9.8.0
asyncpg>=0.29.0
sqlalchemy[asyncio]>=2.0.0
pgvector>=0.2.0
```

## Notes

- **Never use LLM for math**: Explanation text is templated, not generated
- **Assume NOT stackable**: Unless reward explicitly says stackable
- **pgcrypto key**: Store in environment variable, not in code
- **384-dim vectors**: Use `vector(384)` type for MiniLM embeddings
