-- Baseline 001 is the original docs/schema.sql, kept immutable.
ALTER TABLE merchants ADD CONSTRAINT merchants_domain_unique UNIQUE(domain);
ALTER TABLE merchants ADD CONSTRAINT merchants_mcc_valid CHECK(mcc ~ '^[0-9]{4}$');
ALTER TABLE rewards ALTER COLUMN value TYPE numeric(18,6);
ALTER TABLE rewards ALTER COLUMN min_spend TYPE numeric(18,2);
ALTER TABLE rewards ALTER COLUMN max_discount TYPE numeric(18,2);
ALTER TABLE rewards ADD CONSTRAINT reward_value_valid CHECK(value >= 0);
ALTER TABLE rewards ADD CONSTRAINT reward_min_valid CHECK(min_spend IS NULL OR min_spend >= 0);
ALTER TABLE rewards ADD CONSTRAINT reward_max_valid CHECK(max_discount IS NULL OR max_discount >= 0);
ALTER TABLE rewards ADD CONSTRAINT reward_dates_valid CHECK(starts_at IS NULL OR expires_at IS NULL OR starts_at < expires_at);
ALTER TABLE rewards ADD CONSTRAINT reward_confidence_valid CHECK(overall_confidence BETWEEN 0 AND 1);
ALTER TABLE rewards ADD CONSTRAINT rewards_owner_id_unique UNIQUE(user_id,id);
ALTER TABLE rewards ADD COLUMN dedupe_key text;
CREATE UNIQUE INDEX rewards_user_dedupe ON rewards(user_id,dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX rewards_changes ON rewards(user_id,updated_at,id);
ALTER TABLE processed_emails DROP CONSTRAINT processed_emails_pkey;
ALTER TABLE processed_emails ADD PRIMARY KEY(user_id,message_id);
ALTER TABLE processed_emails ADD COLUMN content_hash text;
ALTER TABLE processed_emails ADD CONSTRAINT processed_email_class_valid CHECK(classification IN ('reward','receipt','promo','other'));
ALTER TABLE processed_emails ADD CONSTRAINT processed_email_count_valid CHECK(rewards_extracted >= 0);
CREATE UNIQUE INDEX processed_email_content ON processed_emails(user_id,content_hash) WHERE content_hash IS NOT NULL;
ALTER TABLE cards ALTER COLUMN base_rate TYPE numeric(9,6);
ALTER TABLE cards ADD CONSTRAINT card_rate_valid CHECK(base_rate BETWEEN 0 AND 100);
ALTER TABLE cards ADD CONSTRAINT card_category_array CHECK(jsonb_typeof(category_rates)='array');
ALTER TABLE memberships ALTER COLUMN annual_reward_rate TYPE numeric(9,6);
ALTER TABLE memberships ADD CONSTRAINT membership_rate_valid CHECK(annual_reward_rate BETWEEN 0 AND 100);
ALTER TABLE events ADD COLUMN sequence bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE events ADD CONSTRAINT event_sequence_unique UNIQUE(sequence);
ALTER TABLE events ADD COLUMN dedupe_key text;
ALTER TABLE events DROP CONSTRAINT events_reward_id_fkey;
ALTER TABLE events ADD CONSTRAINT event_reward_owner FOREIGN KEY(user_id,reward_id) REFERENCES rewards(user_id,id);
CREATE INDEX events_replay ON events(user_id,sequence);
CREATE UNIQUE INDEX events_dedupe ON events(user_id,dedupe_key) WHERE dedupe_key IS NOT NULL;
-- Import ledger makes repeat seeding non-destructive, even after wallet deletions.
CREATE TABLE seed_imports (user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dataset text NOT NULL, imported_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(user_id,dataset));
-- Supersede unsafe global mutation/decryption helpers with scoped repository APIs.
DROP FUNCTION get_expiring_rewards(integer);
DROP FUNCTION expire_rewards();
DROP FUNCTION encrypt_value(text,text);
DROP FUNCTION decrypt_value(bytea,text);

ALTER TABLE users ADD CONSTRAINT users_email_hash_unique UNIQUE(email_hash);
ALTER TABLE rewards ADD CONSTRAINT reward_currency_valid CHECK(currency ~ '^[A-Z]{3}$');
ALTER TABLE rewards ADD CONSTRAINT reward_mcc_valid CHECK(mcc ~ '^[0-9]{4}$');
ALTER TABLE events ALTER COLUMN created_at SET DEFAULT clock_timestamp();
-- A waiting writer must use mutation time, not its pre-lock transaction start.
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
