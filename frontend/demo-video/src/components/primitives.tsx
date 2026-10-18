import React from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from 'remotion';
import { C, FONT, STROKE, hardShadow } from '../theme';

export const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

export const useSpring = (delay: number, config: Parameters<typeof spring>[0]['config'] = {}, durationInFrames?: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping: 14, stiffness: 160, mass: 0.7, ...config }, durationInFrames });
};

export const ease = (frame: number, from: number, to: number, out: [number, number] = [0, 1], easing = Easing.bezier(0.22, 1, 0.36, 1)) =>
  interpolate(frame, [from, to], out, { ...clamp, easing });

export const Backdrop: React.FC<{ color?: string; dot?: string; children?: React.ReactNode }> = ({
  color = C.paper,
  dot = 'rgba(20,20,20,0.09)',
  children,
}) => {
  const frame = useCurrentFrame();
  const drift = frame * 0.35;
  return (
    <AbsoluteFill
      style={{
        backgroundColor: color,
        backgroundImage: `radial-gradient(${dot} 2.2px, transparent 2.6px)`,
        backgroundSize: '34px 34px',
        backgroundPosition: `${drift}px ${drift * 0.6}px`,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

// Word that springs up into place starting at `at` (frames).
export const PopWord: React.FC<{
  at: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
  rotate?: number;
  from?: number;
}> = ({ at, children, style, rotate = 0, from = 60 }) => {
  const p = useSpring(at, { damping: 12, stiffness: 180 });
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [at, at + 4], [0, 1], clamp);
  return (
    <span
      style={{
        display: 'inline-block',
        opacity,
        transform: `translateY(${(1 - p) * from}px) scale(${0.6 + 0.4 * p}) rotate(${(1 - p) * rotate}deg)`,
        transformOrigin: '50% 80%',
        ...style,
      }}
    >
      {children}
    </span>
  );
};

// Highlighter swipe that grows behind its children.
export const Marker: React.FC<{ at: number; color?: string; children: React.ReactNode; skew?: number; inset?: string }> = ({
  at,
  color = C.lime,
  children,
  skew = -4,
  inset = '52% -0.12em 4% -0.12em',
}) => {
  const frame = useCurrentFrame();
  const w = ease(frame, at, at + 9);
  const [top, right, bottom, left] = inset.split(' ');
  return (
    <span style={{ position: 'relative', display: 'inline-block' }}>
      <span
        style={{
          position: 'absolute',
          top,
          right,
          bottom,
          left,
          background: color,
          transform: `scaleX(${w}) skewX(${skew}deg)`,
          transformOrigin: 'left center',
          borderRadius: 10,
          zIndex: 0,
        }}
      />
      <span style={{ position: 'relative', zIndex: 1 }}>{children}</span>
    </span>
  );
};

export const Stamp: React.FC<{
  at: number;
  bg?: string;
  color?: string;
  rotate?: number;
  size?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ at, bg = C.sky, color = C.ink, rotate = -4, size = 34, children, style }) => {
  const p = useSpring(at, { damping: 9, stiffness: 220, mass: 0.6 });
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 14,
        padding: `${size * 0.36}px ${size * 0.7}px`,
        background: bg,
        color,
        border: `${STROKE - 1}px solid ${C.ink}`,
        borderRadius: 14,
        boxShadow: hardShadow(6),
        fontFamily: FONT.display,
        fontWeight: 900,
        fontSize: size,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        opacity: interpolate(frame, [at, at + 3], [0, 1], clamp),
        transform: `scale(${interpolate(p, [0, 1], [1.8, 1])}) rotate(${rotate}deg)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export const formatNumber = (n: number, decimals = 0) =>
  n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

const countEasing = Easing.bezier(0.16, 1, 0.3, 1);

export const countAt = (frame: number, from: number, to: number, start: number, end: number) =>
  interpolate(frame, [start, end], [from, to], { ...clamp, easing: countEasing });

// First frame at which a count from `start` to `end` reaches `value`.
export const frameWhenCountReaches = (value: number, from: number, to: number, start: number, end: number) => {
  for (let f = start; f <= end; f += 0.25) {
    if (countAt(f, from, to, start, end) >= value) return f;
  }
  return end;
};

export const useCount = (from: number, to: number, start: number, end: number) => countAt(useCurrentFrame(), from, to, start, end);

// The three spark ticks from the Lapse icon, drawn outward from a point.
export const Sparks: React.FC<{
  at: number;
  x: number;
  y: number;
  size?: number;
  color?: string;
  angle?: number;
  spread?: number;
  count?: number;
  width?: number;
}> = ({ at, x, y, size = 80, color = C.ink, angle = -45, spread = 45, count = 3, width = 12 }) => {
  const frame = useCurrentFrame();
  const t = ease(frame, at, at + 12);
  const fade = interpolate(frame, [at + 30, at + 44], [1, 0.85], clamp);
  return (
    <svg style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible', pointerEvents: 'none' }} width={1} height={1}>
      {new Array(count).fill(0).map((_, i) => {
        const a = ((angle - spread + (i * 2 * spread) / Math.max(1, count - 1)) * Math.PI) / 180;
        const r0 = size * (0.55 + 0.45 * t);
        const r1 = r0 + size * 0.55 * t;
        return (
          <line
            key={i}
            x1={x + Math.cos(a) * r0}
            y1={y + Math.sin(a) * r0}
            x2={x + Math.cos(a) * r1}
            y2={y + Math.sin(a) * r1}
            stroke={color}
            strokeWidth={width}
            strokeLinecap="round"
            opacity={t > 0.01 ? fade : 0}
          />
        );
      })}
    </svg>
  );
};

export const Headline: React.FC<{ children: React.ReactNode; size?: number; style?: React.CSSProperties }> = ({
  children,
  size = 120,
  style,
}) => (
  <div
    style={{
      fontFamily: FONT.display,
      fontWeight: 900,
      fontSize: size,
      lineHeight: 1.02,
      letterSpacing: '-0.03em',
      wordSpacing: '0.1em',
      color: C.ink,
      ...style,
    }}
  >
    {children}
  </div>
);
