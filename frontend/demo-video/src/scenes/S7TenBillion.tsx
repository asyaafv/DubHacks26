import React from 'react';
import { AbsoluteFill, interpolate, random, useCurrentFrame } from 'remotion';
import { Backdrop, Marker, PopWord, Stamp, clamp, useSpring } from '../components/primitives';
import { C, FONT, hardShadow } from '../theme';
import { cue } from '../timeline';

const BRICK_H = 30;
const BRICK_W = 150;

const Stack: React.FC<{ x: number; bricks: number; start: number; end: number; seed: number }> = ({ x, bricks, start, end, seed }) => {
  const frame = useCurrentFrame();
  return (
    <>
      {new Array(bricks).fill(0).map((_, i) => {
        const at = start + (i / bricks) * (end - start) + random(`brick-${seed}-${i}`) * 4;
        const p = interpolate(frame, [at, at + 8], [0, 1], { ...clamp, easing: (t) => 1 - (1 - t) ** 3 });
        const jitter = (random(`bx-${seed}-${i}`) - 0.5) * 18;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: x + jitter,
              top: 1080 - (i + 1) * BRICK_H,
              width: BRICK_W,
              height: BRICK_H,
              background: C.lime,
              border: `4px solid ${C.ink}`,
              borderRadius: 6,
              boxSizing: 'border-box',
              opacity: p,
              transform: `translateY(${(1 - p) * -360}px) rotate(${(1 - p) * (seed % 2 ? 12 : -12)}deg)`,
            }}
          >
            <div style={{ position: 'absolute', left: BRICK_W / 2 - 18, width: 28, top: -2, bottom: -2, background: C.amber, borderLeft: `3px solid ${C.ink}`, borderRight: `3px solid ${C.ink}` }} />
          </div>
        );
      })}
    </>
  );
};

const STACKS = [
  { x: 40, bricks: 13 },
  { x: 210, bricks: 9 },
  { x: 380, bricks: 5 },
  { x: 1390, bricks: 6 },
  { x: 1560, bricks: 10 },
  { x: 1730, bricks: 14 },
];

const DIGIT_H = 300;

const Odometer: React.FC<{ value: number; velocity: number }> = ({ value, velocity }) => {
  const steps = new Array(11).fill(0).map((_, i) => String(i));
  return (
    <div style={{ height: DIGIT_H, overflow: 'hidden', width: 360, textAlign: 'center' }}>
      <div style={{ transform: `translateY(${-value * DIGIT_H}px)`, filter: `blur(${Math.min(10, velocity * 22)}px)` }}>
        {steps.map((s) => (
          <div key={s} style={{ height: DIGIT_H, lineHeight: `${DIGIT_H}px` }}>
            {s}
          </div>
        ))}
      </div>
    </div>
  );
};

export const S7TenBillion: React.FC = () => {
  const frame = useCurrentFrame();
  const americans = cue('s7', 'americans');
  const miss = cue('s7', 'miss');
  const ten = cue('s7', 'ten');
  const billion = cue('s7', 'billion');
  const loyalty = cue('s7', 'loyalty');
  const savings = cue('s7', 'savings');
  const every = cue('s7', 'every');
  const roll = (f: number) => interpolate(f, [ten - 6, billion + 6], [0, 10], { ...clamp, easing: (t) => 1 - (1 - t) ** 4 });
  const v = roll(frame);
  const velocity = Math.abs(roll(frame) - roll(frame - 1));
  const numIn = useSpring(ten - 8, { damping: 12, stiffness: 160 });
  const settle = useSpring(billion + 6, { damping: 7, stiffness: 260, mass: 0.5 });
  const pop = 1 + interpolate(settle, [0, 0.5, 1], [0, 0.07, 0]);
  return (
    <Backdrop>
      <AbsoluteFill>
        {STACKS.map((s, i) => (
          <Stack key={i} x={s.x} bricks={s.bricks} start={miss + i * 3} end={billion + 18 + i * 2} seed={i} />
        ))}
        <div style={{ position: 'absolute', left: 130, top: 110 }}>
          <Stamp at={0} bg={C.lilac} rotate={-3} size={40}>
            Antavo estimate
          </Stamp>
        </div>
        <AbsoluteFill style={{ alignItems: 'center', top: 250, fontFamily: FONT.display, color: C.ink }}>
          <div style={{ fontSize: 74, fontWeight: 800, wordSpacing: '0.1em' }}>
            <PopWord at={americans}>Americans</PopWord> <PopWord at={miss}>miss out</PopWord>{' '}
            <PopWord at={cue('s7', 'up')}>on up to</PopWord>
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              marginTop: 10,
              fontWeight: 900,
              fontSize: DIGIT_H,
              letterSpacing: '-0.05em',
              lineHeight: 1,
              color: C.tangerine,
              WebkitTextStroke: `8px ${C.ink}`,
              textShadow: hardShadow(12),
              opacity: interpolate(frame, [ten - 8, ten - 4], [0, 1], clamp),
              transform: `scale(${(0.6 + 0.4 * numIn) * pop})`,
            }}
          >
            <span>$</span>
            <Odometer value={v} velocity={velocity} />
            <span style={{ fontSize: 170, marginLeft: 30, color: C.ink, WebkitTextStroke: 'none', textShadow: 'none', letterSpacing: '-0.03em' }}>
              {'BILLION'.split('').map((ch, i) => (
                <PopWord key={i} at={billion + i * 1.2} from={80}>
                  {ch}
                </PopWord>
              ))}
            </span>
          </div>
          <div style={{ fontSize: 80, fontWeight: 900, marginTop: 10, display: 'flex', alignItems: 'center', gap: 34 }}>
            <PopWord at={loyalty - 3}>in</PopWord>
            <PopWord at={loyalty}>
              <Marker at={savings}>loyalty savings</Marker>
            </PopWord>
            <Stamp at={every} bg={C.tangerine} color={C.paper} rotate={-7} size={50}>
              every year
            </Stamp>
          </div>
        </AbsoluteFill>
      </AbsoluteFill>
    </Backdrop>
  );
};
