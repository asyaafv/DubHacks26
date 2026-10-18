import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop, PopWord, clamp, useCount, useSpring } from '../components/primitives';
import { PlateIcon } from '../components/icons';
import { C, FONT, STROKE, hardShadow } from '../theme';
import { cue } from '../timeline';

const BASE_Y = 860;
const MAX_H = 470;
const ALL = 8.8;
const RESTAURANTS = 1.14;
const BAR_W = 210;

const Bar: React.FC<{ x: number; h: number; color: string; label: string; value: string; valueOpacity?: number }> = ({
  x,
  h,
  color,
  label,
  value,
  valueOpacity = 1,
}) => (
  <>
    <div
      style={{
        position: 'absolute',
        left: x,
        top: BASE_Y - h,
        width: BAR_W,
        height: Math.max(0, h),
        background: color,
        border: `${STROKE}px solid ${C.ink}`,
        borderBottom: 'none',
        borderRadius: '18px 18px 0 0',
        boxShadow: hardShadow(9),
        boxSizing: 'border-box',
      }}
    />
    <div
      style={{
        position: 'absolute',
        left: x - 40,
        width: BAR_W + 80,
        top: BASE_Y - h - 86,
        textAlign: 'center',
        fontFamily: FONT.display,
        fontWeight: 900,
        fontSize: 64,
        color: C.ink,
        opacity: valueOpacity,
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      {value}
    </div>
    <div
      style={{
        position: 'absolute',
        left: x - 60,
        width: BAR_W + 120,
        top: BASE_Y + 22,
        textAlign: 'center',
        fontFamily: FONT.display,
        fontWeight: 800,
        fontSize: 32,
        color: C.ink,
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
      }}
    >
      {label}
    </div>
  </>
);

export const S6Restaurants: React.FC = () => {
  const frame = useCurrentFrame();
  const just = cue('s6', 'just');
  const four = cue('s6', 'four');
  const grow = useSpring(0, { damping: 16, stiffness: 140 });
  const collapse = useSpring(just + 2, { damping: 9, stiffness: 120, mass: 0.8 });
  const restH = interpolate(collapse, [0, 1], [ALL, RESTAURANTS]) * (MAX_H / ALL) * grow;
  const n = useCount(ALL, RESTAURANTS, just + 2, four + 8);
  const plate = useSpring(0, { damping: 9, stiffness: 160 });
  const ghost = interpolate(frame, [just + 4, just + 12], [0, 1], clamp);
  return (
    <Backdrop>
      <AbsoluteFill>
        <div style={{ position: 'absolute', left: 130, top: 170, display: 'flex', alignItems: 'center', gap: 28 }}>
          <div style={{ transform: `scale(${plate}) rotate(${(1 - plate) * -90}deg)` }}>
            <PlateIcon size={150} />
          </div>
          <div style={{ fontFamily: FONT.display, fontWeight: 900, fontSize: 92, color: C.ink, lineHeight: 1, wordSpacing: '0.1em' }}>
            <PopWord at={0}>For</PopWord> <PopWord at={cue('s6', 'restaurants')}>restaurants</PopWord>
          </div>
        </div>
        <div style={{ position: 'absolute', left: 130, top: 400, fontFamily: FONT.display, color: C.ink }}>
          <div style={{ fontSize: 60, fontWeight: 800, color: C.muted }}>
            <PopWord at={just - 4}>it's just</PopWord>
          </div>
          <div
            style={{
              fontSize: 260,
              fontWeight: 900,
              letterSpacing: '-0.04em',
              lineHeight: 1,
              color: C.tangerine,
              WebkitTextStroke: `7px ${C.ink}`,
              textShadow: hardShadow(12),
              fontVariantNumeric: 'tabular-nums',
              opacity: interpolate(frame, [just - 2, just + 2], [0, 1], clamp),
            }}
          >
            {n.toFixed(2)}
          </div>
          <div style={{ fontSize: 44, fontWeight: 800, opacity: interpolate(frame, [four, four + 6], [0, 1], clamp) }}>
            restaurant programs actively used
          </div>
        </div>
        <div
          style={{
            position: 'absolute',
            left: 1440,
            top: BASE_Y - MAX_H,
            width: BAR_W,
            height: MAX_H,
            border: `5px dashed ${C.ink}`,
            borderBottom: 'none',
            borderRadius: '18px 18px 0 0',
            opacity: ghost * 0.35,
            boxSizing: 'border-box',
          }}
        />
        <Bar x={1080} h={MAX_H * grow} color={C.sky} label="All programs" value={ALL.toFixed(1)} />
        <Bar x={1440} h={restH} color={C.tangerine} label="Restaurants" value={RESTAURANTS.toFixed(2)} valueOpacity={interpolate(frame, [four - 2, four + 4], [0, 1], clamp)} />
        <div style={{ position: 'absolute', left: 1000, top: BASE_Y, width: 740, height: STROKE + 2, background: C.ink, borderRadius: 4 }} />
      </AbsoluteFill>
    </Backdrop>
  );
};
