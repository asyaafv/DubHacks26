import { RewardKind, RewardSource, RewardStatus, type Reward } from '../types'
import { DEMO_USER } from '../util/demo'

const USER = DEMO_USER.id

function reward(partial: Pick<Reward, 'id' | 'merchant_name' | 'category' | 'mcc' | 'kind' | 'value'> & Partial<Reward>): Reward {
  return {
    user_id: USER,
    merchant_id: null,
    currency: 'USD',
    min_spend: null,
    max_discount: null,
    code: null,
    expires_at: null,
    starts_at: null,
    stackable: true,
    exclusions: [],
    source: RewardSource.seed,
    source_email_id: null,
    field_confidence: {
      value: 0.95,
      expires_at: 0.93,
      code: 0.96,
      min_spend: 0.94,
      merchant: 0.97,
    },
    overall_confidence: 0.95,
    status: RewardStatus.active,
    created_at: '2026-10-12T15:00:00Z',
    updated_at: '2026-10-12T15:00:00Z',
    ...partial,
  }
}

export const MCD_POINTS_ID = '22222222-2222-2222-2222-222222222226'
export const HM_POINTS_ID = '22222222-2222-2222-2222-222222222227'
export const PACSUN_ID = '22222222-2222-2222-2222-222222222228'
export const AERO_ID = '22222222-2222-2222-2222-222222222229'
export const ULTA_POINTS_ID = '22222222-2222-2222-2222-222222222230'
export const ULTA_CARD_ID = '22222222-2222-2222-2222-222222222231'
export const AMEX_ID = '22222222-2222-2222-2222-222222222232'

/** Sketch rewards that are not already in shared/seed. */
export const extraRewards: Reward[] = [
  reward({
    id: MCD_POINTS_ID,
    merchant_id: '11111111-1111-1111-1111-111111111130',
    merchant_name: "McDonald's",
    category: 'Fast Food Restaurants',
    mcc: '5814',
    kind: RewardKind.points,
    value: '500',
    expires_at: '2026-11-15T23:59:59Z',
    code: null,
  }),
  reward({
    id: HM_POINTS_ID,
    merchant_id: '11111111-1111-1111-1111-111111111148',
    merchant_name: 'H&M',
    category: 'Family Clothing Stores',
    mcc: '5651',
    kind: RewardKind.points,
    value: '2000',
    expires_at: '2026-12-01T23:59:59Z',
    min_spend: null,
  }),
  reward({
    id: PACSUN_ID,
    merchant_name: 'PacSun',
    category: 'Family Clothing Stores',
    mcc: '5651',
    kind: RewardKind.bogo,
    value: '0',
    code: 'BOGOJEANS',
    expires_at: '2026-10-29T23:59:59Z',
    stackable: false,
    exclusions: ['Clearance'],
  }),
  reward({
    id: AERO_ID,
    merchant_name: 'Aéropostale',
    category: 'Family Clothing Stores',
    mcc: '5651',
    kind: RewardKind.percent_off,
    value: '50',
    code: 'AERO50',
    expires_at: '2026-11-02T23:59:59Z',
    stackable: false,
    exclusions: ['Doorbusters', 'Gift cards'],
  }),
  reward({
    id: ULTA_POINTS_ID,
    merchant_id: '11111111-1111-1111-1111-111111111136',
    merchant_name: 'Ulta Beauty',
    category: 'Cosmetic Stores',
    mcc: '5977',
    kind: RewardKind.points,
    value: '500',
    expires_at: '2026-11-18T23:59:59Z',
  }),
  reward({
    id: ULTA_CARD_ID,
    merchant_name: 'Ulta Card',
    category: 'Cosmetic Stores',
    mcc: '5977',
    kind: RewardKind.cashback,
    value: '10',
    expires_at: '2026-12-31T23:59:59Z',
    stackable: true,
  }),
  reward({
    id: AMEX_ID,
    merchant_name: 'American Express',
    category: 'Airlines',
    mcc: '4511',
    kind: RewardKind.points,
    value: '0',
    expires_at: '2026-12-31T23:59:59Z',
    stackable: true,
  }),
]

export const VALUE_LABELS: Record<string, string> = {
  [PACSUN_ID]: 'BOGO jeans',
  [AERO_ID]: '50% off select items',
  [AMEX_ID]: 'Flight rewards',
}

export const TERMS_OVERRIDES: Record<string, string> = {
  [MCD_POINTS_ID]: "500 MyMcDonald's points. Can be combined with other rewards.",
  [HM_POINTS_ID]: '2,000 H&M member points. Can be combined with other rewards.',
  [PACSUN_ID]: 'Buy one pair of jeans, get one free. Cannot be combined with other rewards. Excludes clearance.',
  [AERO_ID]: '50% off select items. Cannot be combined with other rewards.',
  [ULTA_POINTS_ID]: '500 Ulta Beauty points. Can be combined with other rewards.',
  [ULTA_CARD_ID]: '10% cashback on Ulta Beauty purchases paid with the Ulta card. Can be combined with other rewards.',
  [AMEX_ID]: 'American Express flight rewards. Redeem toward eligible airfare. Can be combined with other rewards.',
}
