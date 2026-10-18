CREATE TABLE redemptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reward_id UUID NOT NULL REFERENCES rewards(id),
    merchant_name TEXT,
    description TEXT,
    saved NUMERIC(10, 2) NOT NULL CHECK (saved >= 0 AND saved <> 'NaN'::NUMERIC),
    redeemed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, reward_id),
    FOREIGN KEY (user_id, reward_id) REFERENCES rewards(user_id, id)
);

CREATE INDEX idx_redemptions_user_date ON redemptions(user_id, redeemed_at);
