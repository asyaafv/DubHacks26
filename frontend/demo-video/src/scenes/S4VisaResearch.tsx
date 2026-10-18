import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Backdrop, PopWord, Stamp, clamp, formatNumber, useCount, useSpring } from '../components/primitives';
import { Person } from '../components/icons';
import { C, FONT, hardShadow } from '../theme';
import { cue } from '../timeline';

const COLS = 16;
const ROWS = 10;
const PALETTE = [C.sky, C.lilac, C.lime, C.amber, C.tangerine];

const Crowd: React.FC<{ start: number; end: number }> = ({ start, end }) => {
  const frame = useCurrentFrame();
  const cells = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const order = (c + r * 0.6) / (COLS + ROWS * 0.6);
      const at = start + order * (end - start);
      const p = interpolate(frame, [at, at + 7], [0, 1], { ...clamp, easing: (x) => 1 - (1 - x) ** 3 });
      const overshoot = p < 1 ? 1 + Math.sin(p * Math.PI) * 0.35 : 1;
      cells.push(
        <div
          key={`${r}-${c}`}
          style={{
            position: 'absolute',
            left: c * 50,
            top: r * 62,
            transform: `scale(${p * overshoot}) translateY(${(1 - p) * 20}px)`,
            opacity: p,
          }}
        >
          <Person size={44} fill={PALETTE[(c * 7 + r * 3) % PALETTE.length]} />
        </div>,
      );
    }
  }
  return <div style={{ position: 'absolute', left: 1040, top: 230, width: COLS * 50, height: ROWS * 62 }}>{cells}</div>;
};

export const S4VisaResearch: React.FC = () => {
  const research = cue('s4', 'research');
  const countFrom = cue('s4', 'twenty-two');
  const consumers = cue('s4', 'consumers');
  const n = useCount(0, 22000, countFrom - 4, consumers + 2);
  const frame = useCurrentFrame();
  const numP = useSpring(countFrom - 4, { damping: 12, stiffness: 150 });
  const plus = useSpring(consumers - 4, { damping: 8, stiffness: 240 });
  const panelP = useSpring(research - 6, { damping: 14, stiffness: 120 });
  return (
    <Backdrop>
      <AbsoluteFill>
        <div style={{ position: 'absolute', left: 140, top: 200 }}>
          <Stamp at={0} bg="#1A1F71" color={C.paper} rotate={-3} size={40}>
            Visa research
          </Stamp>
        </div>
        <div style={{ position: 'absolute', left: 140, top: 330, fontFamily: FONT.display, color: C.ink }}>
          <div style={{ fontSize: 56, fontWeight: 800, color: C.muted }}>
            <PopWord at={cue('s4', 'across')}>across</PopWord>
          </div>
          <div
            style={{
              fontSize: 180,
              fontWeight: 900,
              letterSpacing: '-0.04em',
              lineHeight: 1,
              fontVariantNumeric: 'tabular-nums',
              opacity: interpolate(frame, [countFrom - 4, countFrom], [0, 1], clamp),
              transform: `scale(${0.7 + 0.3 * numP})`,
              transformOrigin: 'left center',
              display: 'flex',
              alignItems: 'flex-start',
            }}
          >
            {formatNumber(Math.round(n / 10) * 10)}
            <span
              style={{
                color: C.tangerine,
                WebkitTextStroke: `5px ${C.ink}`,
                textShadow: hardShadow(7),
                transform: `scale(${plus}) rotate(${(1 - plus) * 90}deg)`,
                display: 'inline-block',
                marginLeft: 6,
              }}
            >
              +
            </span>
          </div>
          <div style={{ fontSize: 80, fontWeight: 900, marginTop: 6 }}>
            <PopWord at={consumers}>consumers</PopWord>
          </div>
        </div>
        <div
          style={{
            position: 'absolute',
            left: 1000,
            top: 190,
            width: 880,
            height: 700,
            background: C.paper,
            border: `6px solid ${C.ink}`,
            borderRadius: 30,
            boxShadow: hardShadow(12),
            transform: `translateY(${(1 - panelP) * 80}px) rotate(${(1 - panelP) * 4}deg)`,
            opacity: panelP,
          }}
        />
        <Crowd start={countFrom - 4} end={consumers + 2} />
      </AbsoluteFill>
    </Backdrop>
  );
};
