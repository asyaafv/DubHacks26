import React from 'react';
import { AbsoluteFill, interpolate, random, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { CameraMotionBlur } from '@remotion/motion-blur';
import { noise2D } from '@remotion/noise';
import { Backdrop, Headline, Marker, PopWord, clamp } from '../components/primitives';
import { Bill } from '../components/icons';
import { C, STROKE, hardShadow } from '../theme';
import { cue } from '../timeline';

const TABLE_Y = 830;
const BILLS = 18;

type Throw = {
  t0: number;
  dur: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  peak: number;
  spin: number;
  rest: number;
  flyAway: boolean;
  scale: number;
  fill: string;
};

const THROWS: Throw[] = new Array(BILLS).fill(0).map((_, i) => {
  const r = (k: string) => random(`bill-${i}-${k}`);
  const flyAway = i % 5 === 3;
  const fromRight = i % 2 === 1;
  const x0 = fromRight ? 1960 + r('x0') * 120 : -140 - r('x0') * 120;
  const x1 = flyAway ? (fromRight ? -300 : 2250) : 330 + ((i * 0.618 * 1300) % 1300) + r('x1') * 60;
  return {
    t0: 6 + i * 3 + r('t0') * 2,
    dur: flyAway ? 30 : 24 + r('dur') * 8,
    x0,
    y0: 1000 + r('y0') * 200,
    x1,
    y1: flyAway ? 620 + r('y1') * 200 : TABLE_Y - 34 - r('stack') * 40,
    peak: 470 + r('peak') * 110,
    spin: (fromRight ? -1 : 1) * (240 + r('spin') * 360),
    rest: (r('rest') - 0.5) * 60,
    flyAway,
    scale: 0.85 + r('scale') * 0.3,
    fill: i % 6 === 0 ? '#9fd13a' : C.lime,
  };
});

const FlyingBill: React.FC<{ b: Throw; i: number }> = ({ b, i }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (frame < b.t0) return null;
  const t = Math.min(1, (frame - b.t0) / b.dur);
  const yc = 2 * b.peak - (b.y0 + b.y1) / 2;
  const x = b.x0 + (b.x1 - b.x0) * t;
  const y = (1 - t) ** 2 * b.y0 + 2 * (1 - t) * t * yc + t ** 2 * b.y1;
  const flight = (tt: number, f: number) => ({
    rz: b.spin * tt,
    rx: noise2D(`fx${i}`, f / 9, 0) * 70,
    ry: noise2D(`fy${i}`, f / 11, 3) * 55,
  });
  let { rz, rx, ry } = flight(t, frame);
  let dy = 0;
  if (t >= 1 && !b.flyAway) {
    const landed = b.t0 + b.dur;
    const s = spring({ frame: frame - landed, fps, config: { damping: 10, stiffness: 140, mass: 0.6 } });
    const atLand = flight(1, landed);
    rz = interpolate(s, [0, 1], [atLand.rz, Math.round(b.spin / 180) * 180 + b.rest]);
    rx = interpolate(s, [0, 1], [atLand.rx, 64]);
    ry = interpolate(s, [0, 1], [atLand.ry, 0]);
    dy = -Math.sin(Math.min(1, (frame - landed) / 10) * Math.PI) * 18 * (1 - Math.min(1, (frame - landed) / 18));
  }
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y + dy,
        transform: `translate(-50%, -50%) scale(${b.scale}) rotateX(${rx}deg) rotateZ(${rz}deg) rotateY(${ry}deg)`,
        transformStyle: 'preserve-3d',
        filter: 'drop-shadow(5px 5px 0 rgba(20,20,20,0.9))',
      }}
    >
      <Bill w={210} fill={b.fill} />
    </div>
  );
};

const Table: React.FC = () => {
  const frame = useCurrentFrame();
  const rise = interpolate(frame, [0, 12], [260, 0], { ...clamp, easing: (x) => 1 - (1 - x) ** 3 });
  return (
    <div style={{ position: 'absolute', left: 0, top: 0, width: 1920, height: 1080, transform: `translateY(${rise}px)` }}>
      {[330, 1590].map((lx) => (
        <div
          key={lx}
          style={{
            position: 'absolute',
            left: lx - 26,
            top: TABLE_Y + 40,
            width: 52,
            height: 400,
            background: '#C9471A',
            border: `${STROKE}px solid ${C.ink}`,
          }}
        />
      ))}
      <div
        style={{
          position: 'absolute',
          left: 180,
          top: TABLE_Y - 20,
          width: 1560,
          height: 76,
          background: C.tangerine,
          border: `${STROKE}px solid ${C.ink}`,
          borderRadius: 18,
          boxShadow: hardShadow(10),
        }}
      />
    </div>
  );
};

export const S3MoneyOnTable: React.FC = () => {
  const not = cue('s3', 'not');
  const leaving = cue('s3', 'leaving');
  const money = cue('s3', 'money');
  const table = cue('s3', 'table');
  return (
    <Backdrop>
      <AbsoluteFill style={{ perspective: 1400 }}>
        <Table />
        <CameraMotionBlur shutterAngle={200} samples={6}>
          <AbsoluteFill style={{ perspective: 1400 }}>
            {THROWS.map((b, i) => (
              <FlyingBill key={i} b={b} i={i} />
            ))}
          </AbsoluteFill>
        </CameraMotionBlur>
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: 'center', paddingTop: 90, textAlign: 'center' }}>
        <Headline size={78} style={{ color: C.muted, fontWeight: 800 }}>
          <PopWord at={not}>Not</PopWord> <PopWord at={not + 4}>maximizing</PopWord> <PopWord at={not + 10}>it?</PopWord>
        </Headline>
        <Headline size={112} style={{ marginTop: 14 }}>
          <PopWord at={leaving - 4}>You're</PopWord> <PopWord at={leaving}>leaving</PopWord>{' '}
          <PopWord at={money} rotate={-6}>
            <Marker at={money + 2}>money</Marker>
          </PopWord>
          <br />
          <PopWord at={table - 4}>on the</PopWord>{' '}
          <PopWord at={table} rotate={6} style={{ color: C.tangerine, WebkitTextStroke: `4px ${C.ink}`, textShadow: hardShadow(7) }}>
            table.
          </PopWord>
        </Headline>
      </AbsoluteFill>
    </Backdrop>
  );
};
