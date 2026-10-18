import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop, PopWord, clamp, ease, frameWhenCountReaches, useCount, useSpring } from '../components/primitives';
import { C, FONT, hardShadow } from '../theme';
import { cue } from '../timeline';

const ENROLLED = 17.4;
const ACTIVE = 8.8;
const COLS = 6;
const CARD_W = 146;
const CARD_H = 98;
const GAP = 20;
const GRID_X = 880;
const GRID_Y = 330;
const PALETTE = [C.sky, C.lime, C.amber, C.lilac, C.tangerine];

const LoyaltyCard: React.FC<{ i: number; at: number; dimAt: number }> = ({ i, at, dimAt }) => {
  const frame = useCurrentFrame();
  const p = useSpring(at, { damping: 12, stiffness: 200 });
  const fill = Math.min(1, ENROLLED - i);
  const active = Math.max(0, Math.min(1, ACTIVE - i));
  const dim = ease(frame, dimAt + (i % COLS) * 1.2, dimAt + 10 + (i % COLS) * 1.2);
  const fullyIdle = active === 0;
  const row = Math.floor(i / COLS);
  const col = i % COLS;
  const color = PALETTE[(i * 3) % PALETTE.length];
  const lift = active > 0 ? -10 * dim : 16 * dim;
  return (
    <div
      style={{
        position: 'absolute',
        left: GRID_X + col * (CARD_W + GAP),
        top: GRID_Y + row * (CARD_H + GAP),
        width: CARD_W * fill,
        height: CARD_H,
        transform: `translateY(${(1 - p) * -260 + lift}px) rotate(${(1 - p) * (col % 2 ? 18 : -18) + (fullyIdle ? dim * (i % 2 ? 4 : -4) : 0)}deg) scale(${0.6 + 0.4 * p})`,
        opacity: interpolate(frame, [at, at + 2], [0, 1], clamp) * (fullyIdle ? 1 - dim * 0.35 : 1),
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: 14,
          border: `5px solid ${C.ink}`,
          background: color,
          boxShadow: hardShadow(active > 0 ? 6 + dim * 4 : 6 - dim * 3),
          overflow: 'hidden',
        }}
      >
        <div style={{ position: 'absolute', left: 0, right: 0, top: 18, height: 14, background: C.ink }} />
        <div
          style={{
            position: 'absolute',
            left: 16,
            bottom: 14,
            width: 30,
            height: 22,
            borderRadius: 5,
            background: C.paper,
            border: `3px solid ${C.ink}`,
          }}
        />
        {active < 1 && (
          <div style={{ position: 'absolute', top: 0, bottom: 0, left: `${(active / fill) * 100}%`, right: 0, background: C.dust, opacity: dim * 0.88 }} />
        )}
      </div>
      {fill < 1 && (
        <div
          style={{
            position: 'absolute',
            left: '100%',
            top: 0,
            width: CARD_W * (1 - fill),
            height: CARD_H,
            borderRadius: 14,
            border: `4px dashed ${C.ink}`,
            opacity: 0.25,
            boxSizing: 'border-box',
          }}
        />
      )}
    </div>
  );
};

const Stat: React.FC<{ at: number; until: number; value: number; label: string; color: string; top: number }> = ({ at, until, value, label, color, top }) => {
  const frame = useCurrentFrame();
  const n = useCount(0, value, at - 2, until);
  const p = useSpring(at - 2, { damping: 11, stiffness: 170 });
  return (
    <div
      style={{
        position: 'absolute',
        left: 130,
        top,
        display: 'flex',
        alignItems: 'baseline',
        gap: 26,
        fontFamily: FONT.display,
        color: C.ink,
        opacity: interpolate(frame, [at - 2, at + 2], [0, 1], clamp),
        transform: `translateX(${(1 - p) * -80}px)`,
      }}
    >
      <div
        style={{
          fontSize: 190,
          fontWeight: 900,
          letterSpacing: '-0.04em',
          lineHeight: 1,
          color,
          WebkitTextStroke: color === C.ink ? undefined : `6px ${C.ink}`,
          textShadow: color === C.ink ? undefined : hardShadow(9),
          fontVariantNumeric: 'tabular-nums',
          width: 400,
        }}
      >
        {n.toFixed(1)}
      </div>
      <div style={{ fontSize: 50, fontWeight: 800, lineHeight: 1.05, width: 280 }}>{label}</div>
    </div>
  );
};

export const S5Programs: React.FC = () => {
  const frame = useCurrentFrame();
  const seventeen = cue('s5', 'seventeen');
  const programs = cue('s5', 'programs');
  const actively = cue('s5', 'actively');
  const only = cue('s5', 'only');
  const eight = cue('s5', 'eight', 0);
  const cards = Math.ceil(ENROLLED);
  const idle = ease(frame, only, only + 10);
  return (
    <Backdrop>
      <AbsoluteFill>
        <div style={{ position: 'absolute', left: 130, top: 110, fontFamily: FONT.display, fontWeight: 900, fontSize: 76, color: C.ink, wordSpacing: '0.1em' }}>
          <PopWord at={0}>The</PopWord> <PopWord at={cue('s5', 'average')}>average</PopWord>{' '}
          <PopWord at={cue('s5', 'american')} style={{ color: C.tangerine, WebkitTextStroke: `3px ${C.ink}` }}>
            American
          </PopWord>
        </div>
        <Stat at={seventeen} until={programs + 6} value={ENROLLED} label="loyalty programs joined" color={C.ink} top={300} />
        <Stat at={eight} until={eight + 14} value={ACTIVE} label="actively used" color={C.tangerine} top={600} />
        <div
          style={{
            position: 'absolute',
            left: 130,
            top: 560,
            width: 680,
            height: 6,
            background: C.ink,
            borderRadius: 3,
            transform: `scaleX(${ease(frame, actively, actively + 12)})`,
            transformOrigin: 'left',
          }}
        />
        {new Array(cards).fill(0).map((_, i) => (
          <LoyaltyCard key={i} i={i} at={frameWhenCountReaches(i + 0.5, 0, ENROLLED, seventeen - 2, programs + 6) - 1} dimAt={actively} />
        ))}
        <div
          style={{
            position: 'absolute',
            left: GRID_X + 2 * (CARD_W + GAP) + 40,
            top: GRID_Y + 3 * (CARD_H + GAP) + 50,
            fontFamily: FONT.display,
            fontWeight: 800,
            fontSize: 44,
            color: C.ink,
            opacity: idle,
            transform: `translateY(${(1 - idle) * 20}px)`,
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <span style={{ background: C.dust, border: `4px solid ${C.ink}`, borderRadius: 12, padding: '6px 18px', boxShadow: hardShadow(5) }}>
            {(ENROLLED - ACTIVE).toFixed(1)} sitting idle
          </span>
        </div>
      </AbsoluteFill>
    </Backdrop>
  );
};
