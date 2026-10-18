import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { evolvePath, getLength, getPointAtLength } from '@remotion/paths';
import { Backdrop, PopWord, Sparks, clamp, ease, useSpring } from '../components/primitives';
import { AppIcon, CardIcon, StoreIcon } from '../components/icons';
import { C, FONT, STROKE, hardShadow } from '../theme';
import { cue } from '../timeline';

const VALUE = { x: 1430, y: 540, r: 200 };

const NODES = [
  { key: 'store', label: 'store', y: 230, bg: C.sky, Icon: StoreIcon },
  { key: 'app', label: 'app', y: 540, bg: C.lilac, Icon: AppIcon },
  { key: 'card', label: 'card', y: 850, bg: C.amber, Icon: CardIcon },
] as const;

const NODE_X = 120;
const NODE_W = 470;
const NODE_H = 170;

const pathFor = (y: number) => {
  const x0 = NODE_X + NODE_W + 10;
  const x1 = VALUE.x - VALUE.r - 26;
  return `M ${x0} ${y} C ${x0 + 300} ${y}, ${x1 - 330} ${VALUE.y}, ${x1} ${VALUE.y}`;
};

const Node: React.FC<{ at: number; label: string; y: number; bg: string; Icon: React.FC<{ size?: number }> }> = ({
  at,
  label,
  y,
  bg,
  Icon,
}) => {
  const p = useSpring(at, { damping: 11, stiffness: 190 });
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: NODE_X,
        top: y - NODE_H / 2,
        width: NODE_W,
        height: NODE_H,
        display: 'flex',
        alignItems: 'center',
        gap: 26,
        padding: '0 30px',
        boxSizing: 'border-box',
        background: bg,
        border: `${STROKE}px solid ${C.ink}`,
        borderRadius: 26,
        boxShadow: hardShadow(10),
        opacity: interpolate(frame, [at, at + 3], [0, 1], clamp),
        transform: `translateX(${(1 - p) * -120}px) scale(${0.7 + 0.3 * p}) rotate(${(1 - p) * -8}deg)`,
      }}
    >
      <div
        style={{
          width: 120,
          height: 120,
          borderRadius: 22,
          background: C.paper,
          border: `5px solid ${C.ink}`,
          display: 'grid',
          placeItems: 'center',
          flexShrink: 0,
        }}
      >
        <Icon size={98} />
      </div>
      <div style={{ fontFamily: FONT.display, color: C.ink, lineHeight: 0.95 }}>
        <div style={{ fontWeight: 700, fontSize: 36, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Every</div>
        <div style={{ fontWeight: 900, fontSize: 84, letterSpacing: '-0.02em' }}>{label}</div>
      </div>
    </div>
  );
};

const Connector: React.FC<{ at: number; d: string; seed: number; valueAt: number }> = ({ at, d, seed, valueAt }) => {
  const frame = useCurrentFrame();
  const drawn = ease(frame, at, at + 16);
  const { strokeDasharray, strokeDashoffset } = evolvePath(drawn, d);
  const len = getLength(d);
  const flowing = frame > at + 10;
  const coins = flowing
    ? [0, 1, 2].map((k) => {
        const speed = frame > valueAt ? 18 : 26;
        const t = (((frame - at - 10) / speed + k / 3 + seed * 0.11) % 1 + 1) % 1;
        const pt = getPointAtLength(d, t * len * Math.min(1, drawn));
        const fadeIn = interpolate(frame, [at + 10, at + 18], [0, 1], clamp);
        return { ...pt, o: fadeIn * interpolate(t, [0, 0.08, 0.9, 1], [0, 1, 1, 0]), k };
      })
    : [];
  return (
    <g>
      <path d={d} fill="none" stroke={C.ink} strokeWidth={10} strokeLinecap="round" strokeDasharray={strokeDasharray} strokeDashoffset={strokeDashoffset} />
      {coins.map((c) => (
        <g key={c.k} transform={`translate(${c.x} ${c.y})`} opacity={c.o}>
          <circle r={22} fill={C.lime} stroke={C.ink} strokeWidth={5} />
          <text y={10} textAnchor="middle" fontFamily={FONT.display} fontWeight={900} fontSize={28} fill={C.ink}>
            $
          </text>
        </g>
      ))}
    </g>
  );
};

const ValueNode: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const p = useSpring(at, { damping: 9, stiffness: 160, mass: 0.8 });
  const ghost = interpolate(frame, [0, 10], [0, 1], clamp) * (1 - Math.min(1, p * 1.5));
  const pulse = frame > at + 14 ? 1 + Math.sin((frame - at) / 4) * 0.02 : 1;
  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: VALUE.x - VALUE.r,
          top: VALUE.y - VALUE.r,
          width: VALUE.r * 2,
          height: VALUE.r * 2,
          borderRadius: '50%',
          border: `6px dashed ${C.ink}`,
          opacity: ghost * 0.5,
          display: 'grid',
          placeItems: 'center',
          fontFamily: FONT.display,
          fontWeight: 900,
          fontSize: 160,
          color: C.ink,
          transform: `rotate(${frame * 0.8}deg)`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: VALUE.x - VALUE.r,
          top: VALUE.y - VALUE.r,
          width: VALUE.r * 2,
          height: VALUE.r * 2,
          borderRadius: '50%',
          background: C.tangerine,
          border: `${STROKE + 2}px solid ${C.ink}`,
          boxShadow: hardShadow(14),
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          transform: `scale(${p * pulse}) rotate(${(1 - p) * 30}deg)`,
          fontFamily: FONT.display,
          color: C.paper,
        }}
      >
        <div style={{ fontWeight: 900, fontSize: 150, lineHeight: 0.9, WebkitTextStroke: `5px ${C.ink}`, textShadow: hardShadow(6) }}>$</div>
        <div style={{ fontWeight: 900, fontSize: 82, letterSpacing: '-0.02em', WebkitTextStroke: `3px ${C.ink}`, textShadow: hardShadow(5) }}>
          VALUE
        </div>
      </div>
      <Sparks at={at + 4} x={VALUE.x + 150} y={VALUE.y - 150} size={110} angle={-45} spread={40} />
      <Sparks at={at + 6} x={VALUE.x - 150} y={VALUE.y + 150} size={90} angle={135} spread={35} color={C.tangerine} />
    </>
  );
};

export const S2Flowchart: React.FC = () => {
  const cues = { store: cue('s2', 'store'), app: cue('s2', 'app'), card: cue('s2', 'card') };
  const valueAt = cue('s2', 'value');
  const handing = cue('s2', 'handing');
  const frame = useCurrentFrame();
  const arrow = ease(frame, cues.store + 14, cues.store + 20);
  const tipX = VALUE.x - VALUE.r - 20;
  return (
    <Backdrop>
      <AbsoluteFill>
        <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
          {NODES.map((n, i) => (
            <Connector key={n.key} at={cues[n.key] + 4} d={pathFor(n.y)} seed={i} valueAt={valueAt} />
          ))}
          <path
            d={`M ${tipX - 34} ${VALUE.y - 26} L ${tipX} ${VALUE.y} L ${tipX - 34} ${VALUE.y + 26}`}
            fill="none"
            stroke={C.ink}
            strokeWidth={10}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={arrow}
          />
        </svg>
        {NODES.map((n) => (
          <Node key={n.key} at={cues[n.key]} label={n.label} y={n.y} bg={n.bg} Icon={n.Icon} />
        ))}
        <div
          style={{
            position: 'absolute',
            left: VALUE.x - 300,
            width: 600,
            top: VALUE.y - VALUE.r - 130,
            textAlign: 'center',
            fontFamily: FONT.display,
            fontWeight: 800,
            fontSize: 54,
            color: C.ink,
          }}
        >
          <PopWord at={handing}>is handing you</PopWord>
        </div>
        <ValueNode at={valueAt} />
      </AbsoluteFill>
    </Backdrop>
  );
};
