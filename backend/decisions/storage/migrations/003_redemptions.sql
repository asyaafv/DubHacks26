-- Savings tracking: one row per redeemed reward (README "NEW: Savings tracking").
CREATE TABLE redemptions (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reward_id uuid NOT NULL,
    merchant_name text,
    description text,
    saved numeric(10,2) NOT NULL,
    redeemed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT redemption_saved_valid CHECK (saved >= 0),
    -- Composite owner FK: a redemption can never reference another user's reward.
    CONSTRAINT redemption_reward_owner FOREIGN KEY (user_id, reward_id)
        REFERENCES rewards(user_id, id)
);
CREATE INDEX redemptions_user_time ON redemptions(user_id, redeemed_at);
-- One redemption per reward makes POST /rewards/{id}/redeem idempotent at the DB.
CREATE UNIQUE INDEX redemptions_reward_once ON redemptions(user_id, reward_id);
