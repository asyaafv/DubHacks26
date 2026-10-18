/**
 * Three throwaway design directions, switched with ?theme=a|b|c.
 *
 * A — "Fieldnotes"  : editorial paper; evolves the frontend-landing palette
 *                     (cream #f8f8ef / forest #174b34 / Inter + serif).
 * B — "Clip & Save" : coupon-zine neo-brutalism; ink borders, hard shadows,
 *                     tangerine/lime stickers, dense 3-col coupon grid.
 * C — "Night Vault" : dark fintech command center; glass panels, mint glow,
 *                     mono numerals, data-dense rows.
 */

export type ThemeId = 'a' | 'b' | 'c'

export interface Theme {
  id: ThemeId
  name: string
  /** Ring colors by urgency */
  ring: { soon: string; week: string; later: string; none: string; track: string }
  glow: boolean
  chart: { stroke: string; fill: string; grid: string; tick: string }
}

export const THEMES: Record<ThemeId, Theme> = {
  a: {
    id: 'a',
    name: 'Fieldnotes',
    ring: { soon: '#C2452D', week: '#B98A2F', later: '#174b34', none: '#8fb58a', track: '#E4E0D0' },
    glow: false,
    chart: { stroke: '#174b34', fill: '#8fb58a', grid: '#E4E0D0', tick: '#6b7f72' },
  },
  b: {
    id: 'b',
    name: 'Clip & Save',
    ring: { soon: '#FF5C1C', week: '#F5A800', later: '#141414', none: '#9a9a9a', track: '#EFE3CB' },
    glow: false,
    chart: { stroke: '#141414', fill: '#BCE740', grid: '#E3D5B8', tick: '#141414' },
  },
  c: {
    id: 'c',
    name: 'Night Vault',
    ring: { soon: '#FF7088', week: '#FFC24B', later: '#3DDC97', none: '#2A4335', track: '#1D3127' },
    glow: true,
    chart: { stroke: '#3DDC97', fill: '#3DDC97', grid: '#1D3127', tick: '#6FA08A' },
  },
}

export function themeFromSearch(search: string): Theme {
  const id = new URLSearchParams(search).get('theme')
  return THEMES[(id === 'b' || id === 'c' ? id : 'a') as ThemeId]
}
