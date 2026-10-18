-- Lapse Database Schema
-- Postgres + pgvector + pgcrypto
-- 
-- Historical baseline, preserved as migrations/001_initial.sql.
-- For the current schema run: python -m backend.decisions.storage migrate
-- See docs/database-setup.md; do not apply this file separately.

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================================================
-- USERS
-- =============================================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    email_hash TEXT NOT NULL,  -- For routing inbound emails (e.g., "user123" part of user123@lapse.app)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email_hash ON users(email_hash);

-- =============================================================================
-- MERCHANTS
-- =============================================================================

CREATE TABLE merchants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    mcc TEXT NOT NULL,  -- 4-digit Merchant Category Code
    category TEXT NOT NULL,
    aliases TEXT[] DEFAULT '{}',
    logo_url TEXT,
    embedding vector(384),  -- MiniLM all-MiniLM-L6-v2 embeddings
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_merchants_domain ON merchants(domain);
CREATE INDEX idx_merchants_mcc ON merchants(mcc);
CREATE INDEX idx_merchants_embedding ON merchants USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- =============================================================================
-- REWARDS
-- =============================================================================

-- Enum types
CREATE TYPE reward_kind AS ENUM (
    'percent_off',
    'amount_off',
    'points',
    'free_item',
    'bogo',
    'cashback'
);

CREATE TYPE reward_source AS ENUM (
    'email_jsonld',
    'gliner',
    'regex',
    'manual',
    'seed'
);

CREATE TYPE reward_status AS ENUM (
    'active',
    'needs_review',
    'used',
    'expired'
);

CREATE TABLE rewards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    merchant_id UUID REFERENCES merchants(id),
    merchant_name TEXT NOT NULL,
    category TEXT NOT NULL,
    mcc TEXT NOT NULL,
    kind reward_kind NOT NULL,
    value NUMERIC(10, 2) NOT NULL,
    currency TEXT DEFAULT 'USD',
    min_spend NUMERIC(10, 2),
    max_discount NUMERIC(10, 2),
    code_encrypted BYTEA,  -- Encrypted via pgcrypto
    expires_at TIMESTAMPTZ,
    starts_at TIMESTAMPTZ,
    stackable BOOLEAN DEFAULT FALSE,
    exclusions TEXT[] DEFAULT '{}',
    source reward_source NOT NULL,
    source_email_id TEXT,
    field_confidence JSONB DEFAULT '{"value": 1.0, "expires_at": 1.0, "code": 1.0, "min_spend": 1.0, "merchant": 1.0}',
    overall_confidence NUMERIC(3, 2) DEFAULT 1.0,
    status reward_status DEFAULT 'active',
    embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_rewards_user_id ON rewards(user_id);
CREATE INDEX idx_rewards_user_status ON rewards(user_id, status);
CREATE INDEX idx_rewards_merchant ON rewards(merchant_id);
CREATE INDEX idx_rewards_expires ON rewards(expires_at) WHERE status = 'active';
CREATE INDEX idx_rewards_embedding ON rewards USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER rewards_updated_at
    BEFORE UPDATE ON rewards
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- CARDS
-- =============================================================================

CREATE TYPE card_network AS ENUM (
    'visa',
    'mastercard',
    'amex',
    'discover'
);

CREATE TABLE cards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issuer TEXT NOT NULL,
    network card_network NOT NULL,
    name TEXT NOT NULL,
    last_four TEXT,
    base_rate NUMERIC(4, 2) NOT NULL,
    category_rates JSONB DEFAULT '[]',  -- Array of {category, mcc_codes, rate}
    is_demo BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cards_user_id ON cards(user_id);

CREATE TRIGGER cards_updated_at
    BEFORE UPDATE ON cards
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- MEMBERSHIPS
-- =============================================================================

CREATE TABLE memberships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    merchant_id UUID REFERENCES merchants(id),
    merchant_name TEXT NOT NULL,
    program_name TEXT NOT NULL,
    tier TEXT,
    member_id_encrypted BYTEA,  -- Encrypted via pgcrypto
    benefits TEXT[] DEFAULT '{}',
    annual_reward_rate NUMERIC(4, 2),
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_memberships_user_id ON memberships(user_id);
CREATE INDEX idx_memberships_merchant ON memberships(merchant_id);

CREATE TRIGGER memberships_updated_at
    BEFORE UPDATE ON memberships
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- PROCESSED EMAILS (Deduplication)
-- =============================================================================

CREATE TABLE processed_emails (
    message_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    classification TEXT NOT NULL,  -- reward, receipt, promo, other
    rewards_extracted INTEGER DEFAULT 0,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_processed_emails_user ON processed_emails(user_id);

-- =============================================================================
-- EVENTS (for SSE)
-- =============================================================================

CREATE TYPE event_type AS ENUM (
    'reward_added',
    'reward_expiring',
    'reward_updated',
    'reward_used',
    'sync_complete'
);

CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type event_type NOT NULL,
    reward_id UUID REFERENCES rewards(id),
    data JSONB DEFAULT '{}',
    delivered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_user_pending ON events(user_id, delivered) WHERE NOT delivered;
CREATE INDEX idx_events_created ON events(created_at);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Encrypt a value with pgcrypto
CREATE OR REPLACE FUNCTION encrypt_value(plaintext TEXT, key TEXT)
RETURNS BYTEA AS $$
BEGIN
    RETURN pgp_sym_encrypt(plaintext, key);
END;
$$ LANGUAGE plpgsql;

-- Decrypt a value with pgcrypto
CREATE OR REPLACE FUNCTION decrypt_value(ciphertext BYTEA, key TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN pgp_sym_decrypt(ciphertext, key);
END;
$$ LANGUAGE plpgsql;

-- Find rewards expiring within N hours
CREATE OR REPLACE FUNCTION get_expiring_rewards(hours_ahead INTEGER DEFAULT 24)
RETURNS TABLE (
    id UUID,
    user_id UUID,
    merchant_name TEXT,
    expires_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT r.id, r.user_id, r.merchant_name, r.expires_at
    FROM rewards r
    WHERE r.status = 'active'
      AND r.expires_at BETWEEN NOW() AND NOW() + (hours_ahead || ' hours')::INTERVAL
    ORDER BY r.expires_at;
END;
$$ LANGUAGE plpgsql;

-- Mark expired rewards
CREATE OR REPLACE FUNCTION expire_rewards()
RETURNS INTEGER AS $$
DECLARE
    affected INTEGER;
BEGIN
    UPDATE rewards
    SET status = 'expired', updated_at = NOW()
    WHERE status = 'active' AND expires_at < NOW();
    
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- SEED DATA INSERTION HELPER
-- =============================================================================

-- Insert demo user
INSERT INTO users (id, email, email_hash)
VALUES ('00000000-0000-0000-0000-000000000001', 'demo@lapse.app', 'demo')
ON CONFLICT (id) DO NOTHING;

-- Note: Seed merchants and rewards should be inserted via the seed JSON files
-- using the backend's seed loading mechanism.

-- =============================================================================
-- ROW LEVEL SECURITY (RLS) - Optional for production
-- =============================================================================

-- Uncomment to enable RLS
-- ALTER TABLE rewards ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE cards ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE events ENABLE ROW LEVEL SECURITY;

-- CREATE POLICY rewards_user_policy ON rewards
--     FOR ALL
--     USING (user_id = current_setting('app.user_id')::UUID);

-- COMMENT ON POLICY rewards_user_policy ON rewards IS 
--     'Users can only access their own rewards. Set app.user_id before queries.';
