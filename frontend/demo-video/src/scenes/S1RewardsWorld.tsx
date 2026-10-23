import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { noise2D } from '@remotion/noise';
import { Backdrop, Headline, Marker, PopWord, clamp, useSpring } from '../components/primitives';
import { C, FONT, hardShadow } from '../theme';
import { cue } from '../timeline';

const CHIPS: { label: string; bg: string; x: number; y: number }[] = [
  { label: '2× points', bg: C.sky, x: 330, y: 200 },
  { label: '$5 off', bg: C.lime, x: 820, y: 150 },
  { label: '10% back', bg: C.amber, x: 1330, y: 190 },
  { label: 'Free coffee', bg: C.lilac, x: 1690, y: 330 },
  { label: 'Gold tier', bg: C.amber, x: 1640, y: 870 },
  { label: 'BOGO', bg: C.tangerine, x: 1170, y: 930 },
  { label: '+500 pts', bg: C.sky, x: 680, y: 900 },
  { label: '3% cashback', bg: C.lime, x: 260, y: 800 },
];

const Chip: React.FC<{ i: number; label: string; bg: string; x: number; y: number }> = ({ i, label, bg, x, y }) => {
  const frame = useCurrentFrame();
  const at = 1 + i * 2.2;
  const p = useSpring(at, { damping: 11, stiffness: 170 });
  const a = (frame / 22 + i) * 1.1;
  const cx = 960 + (x - 960) * (0.35 + 0.65 * p) + Math.cos(a) * 14;
  const cy = 540 + (y - 540) * (0.35 + 0.65 * p) + Math.sin(a) * 10 + noise2D(`chip${i}`, frame / 40, 0) * 8;
  return (
    <div
      style={{
        position: 'absolute',
        left: cx,
        top: cy,
        transform: `translate(-50%, -50%) scale(${p}) rotate(${noise2D(`rot${i}`, frame / 60, 1) * 10 - 4}deg)`,
        background: bg,
        border: `5px solid ${C.ink}`,
        borderRadius: 16,
        boxShadow: hardShadow(6),
        padding: '14px 26px',
        fontFamily: FONT.display,
        fontWeight: 800,
        fontSize: 38,
        color: C.ink,
        whiteSpace: 'nowrap',
        textTransform: 'uppercase',
        letterSpacing: '0.02em',
      }}
    >
      {label}
    </div>
  );
};

export const S1RewardsWorld: React.FC = () => {
  const frame = useCurrentFrame();
  const push = interpolate(frame, [0, 60], [1, 1.07], clamp);
  const rewards = cue('s1', 'rewards');
  const world = cue('s1', 'world');
  return (
    <Backdrop>
      <AbsoluteFill style={{ transform: `scale(${push})` }}>
        {CHIPS.map((c, i) => (
          <Chip key={c.label} i={i} {...c} />
        ))}
        <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}>
          <Headline size={120} style={{ marginBottom: 8 }}>
            <PopWord at={0}>We</PopWord> <PopWord at={cue('s1', 'live')}>live</PopWord>{' '}
            <PopWord at={cue('s1', 'in')}>in</PopWord> <PopWord at={cue('s1', 'a')}>a</PopWord>
          </Headline>
          <Headline size={200}>
            <PopWord at={rewards} rotate={-6}>
              <Marker at={rewards + 3}>rewards</Marker>
            </PopWord>{' '}
            <PopWord at={world} rotate={8} style={{ color: C.tangerine, WebkitTextStroke: `4px ${C.ink}`, textShadow: hardShadow(8) }}>
              world.
            </PopWord>
          </Headline>
        </AbsoluteFill>
      </AbsoluteFill>
    </Backdrop>
  );
};
