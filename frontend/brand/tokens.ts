/**
 * Lapse brand tokens (TypeScript mirror of tokens.css).
 * Derived from frontend/landingPage.html (preserved on branch `frontend-landing`).
 */

export const palette = {
  forest: '#174b34',
  forestDeep: '#103b29',
  green: '#3e6b29',
  sage: '#dfe9d5',
  sage2: '#c8dbbd',
  mint: '#edf3e8',
  cream: '#f8f8ef',
  ink: '#173b2b',
  muted: '#657d70',
  line: 'rgba(23, 75, 52, 0.14)',
  white: 'rgba(255, 255, 250, 0.82)',
} as const

export const accent = {
  default: palette.forest,
  hover: palette.forestDeep,
  soft: palette.mint,
} as const

/** Expiry urgency ramp: calm -> warning -> urgent. */
export const urgency = {
  calm: '#3e6b29',
  warn: '#b97e1e',
  urgent: '#c2492f',
  calmSoft: '#e3edde',
  warnSoft: '#f6ecd7',
  urgentSoft: '#f8e3dc',
} as const

export const fonts = {
  display: "Georgia, 'Times New Roman', serif",
  body: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
} as const

export const radii = {
  sm: '12px',
  md: '16px',
  lg: '24px',
  pill: '999px',
} as const

export const shadows = {
  card: '0 10px 35px rgba(31, 69, 44, 0.045)',
  float: '0 18px 55px rgba(31, 69, 44, 0.1)',
} as const

export type Urgency = keyof typeof urgency
