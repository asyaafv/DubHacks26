/**
 * Lapse Shared Types
 *
 * AUTO-GENERATED from Pydantic models. Do not edit directly.
 * Regenerate with: python scripts/gen_contracts.py
 */

// =============================================================================
// ENUMS
// =============================================================================

export enum RewardKind {
  percent_off = "percent_off",
  amount_off = "amount_off",
  points = "points",
  free_item = "free_item",
  bogo = "bogo",
  cashback = "cashback",
}

export enum RewardSource {
  email_jsonld = "email_jsonld",
  gliner = "gliner",
  regex = "regex",
  manual = "manual",
  seed = "seed",
}

export enum RewardStatus {
  active = "active",
  needs_review = "needs_review",
  used = "used",
  expired = "expired",
}

export enum CardNetwork {
  visa = "visa",
  mastercard = "mastercard",
  amex = "amex",
  discover = "discover",
}

export enum EventType {
  reward_added = "reward_added",
  reward_expiring = "reward_expiring",
  reward_updated = "reward_updated",
  reward_used = "reward_used",
  sync_complete = "sync_complete",
}

export enum EmailClassification {
  reward = "reward",
  receipt = "receipt",
  promo = "promo",
  other = "other",
}

// =============================================================================
// INTERFACES
// =============================================================================

/** Base merchant model. */
export interface MerchantBase {
  /** Merchant display name */
  name: string;
  /** Primary domain */
  domain: string;
  /** Merchant Category Code (4 digits) */
  mcc: string;
  /** Human-readable category */
  category: string;
}

/** Full merchant record with ID. */
export interface Merchant {
  /** Merchant display name */
  name: string;
  /** Primary domain */
  domain: string;
  /** Merchant Category Code (4 digits) */
  mcc: string;
  /** Human-readable category */
  category: string;
  /** Unique merchant ID */
  id: string;
  /** Alternative domains/names */
  aliases?: string[];
  /** Logo URL for display */
  logo_url?: string | null;
  created_at?: string;
}

/** Request to classify an unknown merchant. */
export interface ClassifyMerchantRequest {
  /** Domain to classify */
  domain: string;
  /** Page title for context */
  page_title?: string | null;
}

/** Merchant classification result. */
export interface ClassifyMerchantResult {
  domain: string;
  /** Matched merchant ID if known */
  merchant_id?: string | null;
  /** Merchant name (inferred if unknown) */
  merchant_name: string;
  /** Inferred category */
  category: string;
  /** Inferred MCC code */
  mcc: string;
  /** Classification confidence */
  confidence: number;
  /** True if merchant was not in database */
  is_new: boolean;
}

/** Per-field extraction confidence scores. */
export interface FieldConfidence {
  value?: number;
  expires_at?: number;
  code?: number;
  min_spend?: number;
  merchant?: number;
}

/** Base reward fields (for creation). */
export interface RewardBase {
  /** Linked merchant ID */
  merchant_id?: string | null;
  /** Merchant name */
  merchant_name: string;
  /** Reward category */
  category: string;
  /** Merchant Category Code */
  mcc: string;
  /** Type of reward */
  kind: RewardKind;
  /** Reward value (percentage or amount) */
  value: number | string;
  /** Currency code */
  currency?: string;
  /** Minimum purchase to apply */
  min_spend?: number | string | null;
  /** Maximum discount cap */
  max_discount?: number | string | null;
  /** Promo/reward code (encrypted at rest) */
  code?: string | null;
  /** Expiration datetime */
  expires_at?: string | null;
  /** Start datetime (if future) */
  starts_at?: string | null;
  /** Can combine with other rewards */
  stackable?: boolean;
  /** Excluded items/categories */
  exclusions?: string[];
}

/** Full reward record. */
export interface Reward {
  /** Linked merchant ID */
  merchant_id?: string | null;
  /** Merchant name */
  merchant_name: string;
  /** Reward category */
  category: string;
  /** Merchant Category Code */
  mcc: string;
  /** Type of reward */
  kind: RewardKind;
  /** Reward value (percentage or amount) */
  value: number | string;
  /** Currency code */
  currency?: string;
  /** Minimum purchase to apply */
  min_spend?: number | string | null;
  /** Maximum discount cap */
  max_discount?: number | string | null;
  /** Promo/reward code (encrypted at rest) */
  code?: string | null;
  /** Expiration datetime */
  expires_at?: string | null;
  /** Start datetime (if future) */
  starts_at?: string | null;
  /** Can combine with other rewards */
  stackable?: boolean;
  /** Excluded items/categories */
  exclusions?: string[];
  /** Unique reward ID */
  id: string;
  /** Owner user ID */
  user_id: string;
  /** How this reward was extracted */
  source: RewardSource;
  /** Source email message ID */
  source_email_id?: string | null;
  field_confidence?: FieldConfidence;
  overall_confidence?: number;
  status?: RewardStatus;
  created_at?: string;
  updated_at?: string;
}

/** Reward creation payload. */
export interface RewardCreate {
  /** Linked merchant ID */
  merchant_id?: string | null;
  /** Merchant name */
  merchant_name: string;
  /** Reward category */
  category: string;
  /** Merchant Category Code */
  mcc: string;
  /** Type of reward */
  kind: RewardKind;
  /** Reward value (percentage or amount) */
  value: number | string;
  /** Currency code */
  currency?: string;
  /** Minimum purchase to apply */
  min_spend?: number | string | null;
  /** Maximum discount cap */
  max_discount?: number | string | null;
  /** Promo/reward code (encrypted at rest) */
  code?: string | null;
  /** Expiration datetime */
  expires_at?: string | null;
  /** Start datetime (if future) */
  starts_at?: string | null;
  /** Can combine with other rewards */
  stackable?: boolean;
  /** Excluded items/categories */
  exclusions?: string[];
  source?: RewardSource;
  source_email_id?: string | null;
  field_confidence?: FieldConfidence | null;
}

/** Cashback rate for a specific category or MCC. */
export interface CategoryRate {
  /** Category name */
  category?: string | null;
  /** Matching MCC codes */
  mcc_codes?: string[];
  /** Cashback rate (percentage) */
  rate: number | string;
}

/** Payment card for cashback tracking. */
export interface CardBase {
  /** Card issuer */
  issuer: string;
  /** Card network */
  network: CardNetwork;
  /** Card product name */
  name: string;
  /** Base cashback rate (%) */
  base_rate: number | string;
  /** Bonus category rates */
  category_rates?: CategoryRate[];
}

/** Full card record. */
export interface Card {
  /** Card issuer */
  issuer: string;
  /** Card network */
  network: CardNetwork;
  /** Card product name */
  name: string;
  /** Base cashback rate (%) */
  base_rate: number | string;
  /** Bonus category rates */
  category_rates?: CategoryRate[];
  /** Unique card ID */
  id: string;
  /** Owner user ID */
  user_id: string;
  /** Last 4 digits (display only) */
  last_four?: string | null;
  /** Demo card flag */
  is_demo?: boolean;
  created_at?: string;
}

/** Store membership/loyalty program. */
export interface MembershipBase {
  /** Linked merchant ID */
  merchant_id?: string | null;
  /** Merchant name */
  merchant_name: string;
  /** Membership program name */
  program_name: string;
  /** Membership tier */
  tier?: string | null;
  /** Membership number (encrypted) */
  member_id?: string | null;
  /** Membership benefits */
  benefits?: string[];
  /** Annual reward rate (%) */
  annual_reward_rate?: number | string | null;
  /** Membership expiration */
  expires_at?: string | null;
}

/** Full membership record. */
export interface Membership {
  /** Linked merchant ID */
  merchant_id?: string | null;
  /** Merchant name */
  merchant_name: string;
  /** Membership program name */
  program_name: string;
  /** Membership tier */
  tier?: string | null;
  /** Membership number (encrypted) */
  member_id?: string | null;
  /** Membership benefits */
  benefits?: string[];
  /** Annual reward rate (%) */
  annual_reward_rate?: number | string | null;
  /** Membership expiration */
  expires_at?: string | null;
  /** Unique membership ID */
  id: string;
  /** Owner user ID */
  user_id: string;
  is_active?: boolean;
  created_at?: string;
}

/** User's complete wallet state. */
export interface Wallet {
  /** User ID */
  user_id: string;
  /** Payment cards */
  cards?: Card[];
  /** Store memberships */
  memberships?: Membership[];
  /** Number of active rewards */
  active_rewards_count?: number;
  /** Rewards expiring in 3 days */
  expiring_soon_count?: number;
}

/** Wallet update payload. */
export interface WalletUpdate {
  add_cards?: CardBase[];
  remove_card_ids?: string[];
  add_memberships?: MembershipBase[];
  remove_membership_ids?: string[];
}

/** Individual cart item for stacking calculation. */
export interface CartItem {
  /** Item name */
  name: string;
  /** Item category */
  category?: string | null;
  /** Item price */
  price: number | string;
  quantity?: number;
}

/** Request to calculate optimal reward stacking. */
export interface StackRequest {
  /** User ID */
  user_id: string;
  /** Merchant ID if known */
  merchant_id?: string | null;
  /** Merchant domain if ID unknown */
  domain?: string | null;
  /** Total cart value */
  cart_total: number | string;
  /** Cart items (for exclusion matching) */
  items?: CartItem[];
}

/** A reward chosen by the stacking solver. */
export interface ChosenReward {
  reward_id: string;
  reward: Reward;
  /** Savings from this reward */
  savings: number | string;
  /** Order in which to apply */
  applied_order: number;
}

/** Optimal stacking result from CP-SAT solver. */
export interface StackResult {
  /** Rewards to use, in order */
  chosen_rewards: ChosenReward[];
  /** Best card for this purchase */
  recommended_card?: Card | null;
  /** Cashback from card */
  card_cashback?: number | string;
  /** Original cart total */
  original_price: number | string;
  /** Price after all discounts */
  final_price: number | string;
  /** Total savings (rewards + cashback) */
  total_savings: number | string;
  /** Savings as percentage */
  savings_percent: number | string;
  /** Human-readable explanation of stacking */
  explanation: string;
  /** Other rewards that could be used but weren't optimal */
  alternatives?: ChosenReward[];
  /** CP-SAT solver status */
  solver_status?: string;
}

/** Request to find relevant rewards for a merchant. */
export interface LookupRequest {
  /** User ID */
  user_id: string;
  merchant_id?: string | null;
  domain?: string | null;
  /** Optional text query for semantic search */
  query?: string | null;
  limit?: number;
}

/** Reward with relevance score breakdown. */
export interface ScoredReward {
  reward: Reward;
  /** Final ranking score */
  score: number;
  /** Score from value_usd */
  value_component: number;
  /** Score from merchant/category match */
  match_component: number;
  /** Score from expiry urgency */
  urgency_component: number;
  days_until_expiry?: number | null;
}

/** Top rewards for a merchant lookup. */
export interface LookupResult {
  merchant: Merchant | null;
  /** Top rewards by score */
  rewards: ScoredReward[];
  /** Total rewards available for user */
  total_available: number;
}

/** Email attachment metadata (Postmark-compatible). */
export interface InboundEmailAttachment {
  Name: string;
  /** Base64-encoded content */
  Content: string;
  ContentType: string;
  ContentLength: number;
}

/** Postmark inbound webhook payload (subset of fields we use). */
export interface InboundEmail {
  /** Unique message ID */
  MessageID: string;
  /** Sender info with Email and Name */
  FromFull: Record<string, any>;
  /** Recipients */
  ToFull: Record<string, any>[];
  Subject: string;
  TextBody?: string | null;
  HtmlBody?: string | null;
  /** Email date string */
  Date: string;
  /** Hash for user routing */
  MailboxHash?: string;
  Attachments?: InboundEmailAttachment[];
  Headers?: Record<string, string>[];
}

/** Result of processing an inbound email. */
export interface InboundResult {
  message_id: string;
  classification: EmailClassification;
  rewards_extracted?: number;
  reward_ids?: string[];
  needs_review?: boolean;
  processing_time_ms?: number;
}

/** Request to inject a demo/test email. */
export interface DemoInjectRequest {
  /** Filename from shared/seed/emails/ */
  eml_filename: string;
  /** Override user ID */
  user_id?: string | null;
}

/** SSE event payload. */
export interface Event {
  event_type: EventType;
  timestamp?: string;
  user_id: string;
  reward_id?: string | null;
  data?: Record<string, any>;
}

/** Polling sync response. */
export interface SyncResponse {
  user_id: string;
  rewards?: Reward[];
  wallet: Wallet;
  last_sync?: string;
  pending_events?: Event[];
}

/** Standardized error response. */
export interface ErrorDetail {
  /** Error code */
  error: string;
  /** Human-readable message */
  message: string;
  details?: Record<string, any>;
}

/** Health check response. */
export interface HealthCheck {
  status?: string;
  version?: string;
  timestamp?: string;
  services?: Record<string, string>;
}
