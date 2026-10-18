import React from 'react';
import { C } from '../theme';

type P = { size?: number; style?: React.CSSProperties };
const sw = 6;

export const StoreIcon: React.FC<P> = ({ size = 96, style }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={style}>
    <path d="M14 42 V86 H86 V42" fill={C.paper} stroke={C.ink} strokeWidth={sw} strokeLinejoin="round" />
    <path
      d="M10 40 L20 14 H80 L90 40 Q90 50 80 50 Q70 50 70 40 Q70 50 60 50 Q50 50 50 40 Q50 50 40 50 Q30 50 30 40 Q30 50 20 50 Q10 50 10 40 Z"
      fill={C.tangerine}
      stroke={C.ink}
      strokeWidth={sw}
      strokeLinejoin="round"
    />
    <rect x="40" y="62" width="20" height="24" fill={C.sky} stroke={C.ink} strokeWidth={sw} strokeLinejoin="round" />
  </svg>
);

export const AppIcon: React.FC<P> = ({ size = 96, style }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={style}>
    <rect x="26" y="8" width="48" height="84" rx="10" fill={C.paper} stroke={C.ink} strokeWidth={sw} />
    <rect x="34" y="22" width="14" height="14" rx="3" fill={C.tangerine} stroke={C.ink} strokeWidth={4} />
    <rect x="52" y="22" width="14" height="14" rx="3" fill={C.lime} stroke={C.ink} strokeWidth={4} />
    <rect x="34" y="40" width="14" height="14" rx="3" fill={C.sky} stroke={C.ink} strokeWidth={4} />
    <rect x="52" y="40" width="14" height="14" rx="3" fill={C.amber} stroke={C.ink} strokeWidth={4} />
    <line x1="44" y1="80" x2="56" y2="80" stroke={C.ink} strokeWidth={sw} strokeLinecap="round" />
  </svg>
);

export const CardIcon: React.FC<P & { fill?: string }> = ({ size = 96, style, fill = C.sky }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={style}>
    <rect x="6" y="20" width="88" height="60" rx="9" fill={fill} stroke={C.ink} strokeWidth={sw} />
    <rect x="6" y="34" width="88" height="11" fill={C.ink} />
    <rect x="16" y="56" width="18" height="12" rx="3" fill={C.amber} stroke={C.ink} strokeWidth={4} />
    <line x1="56" y1="64" x2="82" y2="64" stroke={C.ink} strokeWidth={5} strokeLinecap="round" />
  </svg>
);

export const Bill: React.FC<{ w?: number; style?: React.CSSProperties; fill?: string }> = ({ w = 220, style, fill = C.lime }) => (
  <svg width={w} height={w * 0.5} viewBox="0 0 200 100" style={style}>
    <rect x="4" y="4" width="192" height="92" rx="10" fill={fill} stroke={C.ink} strokeWidth={6} />
    <rect x="16" y="16" width="168" height="68" rx="6" fill="none" stroke={C.ink} strokeWidth={3} strokeDasharray="6 6" />
    <ellipse cx="100" cy="50" rx="26" ry="26" fill={C.paper} stroke={C.ink} strokeWidth={5} />
    <text x="100" y="62" textAnchor="middle" fontFamily="Archivo, sans-serif" fontWeight={900} fontSize={34} fill={C.ink}>
      $
    </text>
    <circle cx="36" cy="50" r="7" fill={C.ink} />
    <circle cx="164" cy="50" r="7" fill={C.ink} />
  </svg>
);

export const Person: React.FC<P & { fill?: string }> = ({ size = 40, style, fill = C.sky }) => (
  <svg width={size} height={size} viewBox="0 0 40 40" style={style}>
    <circle cx="20" cy="12" r="8" fill={fill} stroke={C.ink} strokeWidth={3.5} />
    <path d="M6 38 Q6 22 20 22 Q34 22 34 38 Z" fill={fill} stroke={C.ink} strokeWidth={3.5} strokeLinejoin="round" />
  </svg>
);

export const PlateIcon: React.FC<P> = ({ size = 120, style }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" style={style}>
    <circle cx="50" cy="52" r="30" fill={C.paper} stroke={C.ink} strokeWidth={sw} />
    <circle cx="50" cy="52" r="17" fill={C.amber} stroke={C.ink} strokeWidth={4} />
    <path d="M10 18 V40 M4 18 V34 Q4 40 10 40 Q16 40 16 34 V18 M10 40 V86" stroke={C.ink} strokeWidth={5} strokeLinecap="round" fill="none" />
    <path d="M90 18 Q80 26 80 44 H90 V86" stroke={C.ink} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" fill={C.dust} />
  </svg>
);

export const BrowserWindow: React.FC<{ w?: number; style?: React.CSSProperties }> = ({ w = 560, style }) => {
  const h = w * 0.66;
  return (
    <svg width={w} height={h} viewBox="0 0 300 198" style={style}>
      <rect x="4" y="4" width="292" height="190" rx="14" fill={C.paper} stroke={C.ink} strokeWidth={6} />
      <path d="M4 18 Q4 4 18 4 H282 Q296 4 296 18 V40 H4 Z" fill={C.lilac} stroke={C.ink} strokeWidth={6} strokeLinejoin="round" />
      <circle cx="24" cy="22" r="6" fill={C.tangerine} stroke={C.ink} strokeWidth={3} />
      <circle cx="44" cy="22" r="6" fill={C.amber} stroke={C.ink} strokeWidth={3} />
      <circle cx="64" cy="22" r="6" fill={C.lime} stroke={C.ink} strokeWidth={3} />
      <rect x="86" y="13" width="190" height="18" rx="9" fill={C.paper} stroke={C.ink} strokeWidth={3} />
      <rect x="22" y="58" width="120" height="16" rx="4" fill={C.ink} />
      <rect x="22" y="84" width="200" height="10" rx="4" fill={C.dust} />
      <rect x="22" y="102" width="170" height="10" rx="4" fill={C.dust} />
      <rect x="22" y="132" width="78" height="44" rx="8" fill={C.sky} stroke={C.ink} strokeWidth={4} />
      <rect x="112" y="132" width="78" height="44" rx="8" fill={C.lime} stroke={C.ink} strokeWidth={4} />
      <rect x="202" y="132" width="78" height="44" rx="8" fill={C.amber} stroke={C.ink} strokeWidth={4} />
    </svg>
  );
};
