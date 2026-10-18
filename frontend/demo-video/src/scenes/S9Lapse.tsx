import React from 'react';
import { AbsoluteFill, Img, interpolate, random, staticFile, useCurrentFrame } from 'remotion';
import { makeStar } from '@remotion/shapes';
import { Backdrop, PopWord, Sparks, clamp, ease, useSpring } from '../components/primitives';
import { C, FONT, hardShadow } from '../theme';
import { cue } from '../timeline';

const CX = 960;
const CY = 560;
const TILE = 340;
const PALETTE = [C.tangerine, C.lime, C.sky, C.amber, C.lilac];
const star = makeStar({ points: 5, innerRadius: 9, outerRadius: 20, cornerRadius: 3 });

const Confetti: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const t = frame - at;
  if (t < 0) return null;
  const drag = 0.86;
  const decay = (1 - drag ** t) / (1 - drag);
  return (
    <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
      {new Array(44).fill(0).map((_, i) => {
        const r = (k: string) => random(`confetti-${i}-${k}`);
        const a = r('a') * Math.PI * 2;
        const speed = 34 + r('s') * 40;
        const x = CX + Math.cos(a) * speed * decay;
        const y = CY + Math.sin(a) * speed * decay * 0.75 + 0.35 * t * t * 0.5;
        const rot = (r('r') - 0.5) * 40 * t;
        const fill = PALETTE[i % PALETTE.length];
        const o = interpolate(t, [0, 2, 40, 55], [0, 1, 1, 0], clamp);
        const kind = i % 3;
        return (
          <g key={i} transform={`translate(${x} ${y}) rotate(${rot})`} opacity={o}>
            {kind === 0 && <path d={star.path} transform="translate(-20 -20)" fill={fill} stroke={C.ink} strokeWidth={4} strokeLinejoin="round" />}
            {kind === 1 && <rect x={-16} y={-9} width={32} height={18} rx={4} fill={fill} stroke={C.ink} strokeWidth={4} />}
            {kind === 2 && <circle r={11} fill={fill} stroke={C.ink} strokeWidth={4} />}
          </g>
        );
      })}
    </svg>
  );
};

export const S9Lapse: React.FC = () => {
  const frame = useCurrentFrame();
  const lapse = cue('s9', 'lapse');
  const icon = useSpring(lapse - 2, { damping: 9, stiffness: 150, mass: 0.8 });
  const punch = useSpring(lapse + 2, { damping: 8, stiffness: 220, mass: 0.5 });
  const lockupScale = 1 + interpolate(punch, [0, 0.4, 1], [0, 0.08, 0]);
  const float = frame > lapse + 20 ? Math.sin((frame - lapse - 20) / 9) * 6 : 0;
  const intro = ease(frame, lapse - 2, lapse + 10);
  const tagline = lapse + 18;
  return (
    <Backdrop>
      <AbsoluteFill>
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: interpolate(intro, [0, 1], [430, 150]),
            textAlign: 'center',
            fontFamily: FONT.display,
            fontWeight: 800,
            wordSpacing: '0.1em',
            fontSize: interpolate(intro, [0, 1], [120, 72]),
            color: interpolate(intro, [0, 1], [0, 1]) > 0.5 ? C.muted : C.ink,
          }}
        >
          <PopWord at={0}>So</PopWord> <PopWord at={cue('s9', 'we')}>we</PopWord> <PopWord at={cue('s9', 'came')}>came</PopWord>{' '}
          <PopWord at={cue('s9', 'up')}>up</PopWord> <PopWord at={cue('s9', 'with')}>with</PopWord>
        </div>

        <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
          {[0, 5].map((d) => {
            const t = ease(frame, lapse + d, lapse + d + 18);
            return t > 0 && t < 1 ? (
              <circle key={d} cx={CX} cy={CY} r={60 + t * 1000} fill="none" stroke={d ? C.lime : C.tangerine} strokeWidth={70 * (1 - t)} />
            ) : null;
          })}
        </svg>
        <Confetti at={lapse + 2} />

        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: CY - TILE / 2,
            height: TILE,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            gap: 60,
            transform: `scale(${lockupScale})`,
          }}
        >
          <div
            style={{
              width: TILE,
              height: TILE,
              borderRadius: 82,
              overflow: 'hidden',
              border: `9px solid ${C.ink}`,
              boxShadow: hardShadow(16),
              background: C.paper,
              opacity: interpolate(frame, [lapse - 2, lapse + 1], [0, 1], clamp),
              transform: `translateY(${(1 - icon) * -380 + float}px) rotate(${(1 - icon) * -24}deg) scale(${0.4 + 0.6 * icon})`,
              flexShrink: 0,
            }}
          >
            <Img src={staticFile('lapse-icon.png')} style={{ width: '100%', height: '100%', display: 'block' }} />
          </div>
          <div
            style={{
              fontFamily: FONT.display,
              fontWeight: 900,
              fontSize: 290,
              lineHeight: 1,
              letterSpacing: '-0.045em',
              color: C.tangerine,
              WebkitTextStroke: `9px ${C.ink}`,
              textShadow: hardShadow(16),
              paddingBottom: 30,
            }}
          >
            {'Lapse'.split('').map((ch, i) => (
              <PopWord key={i} at={lapse + i * 1.6} from={140} rotate={i % 2 ? 10 : -10}>
                {ch}
              </PopWord>
            ))}
          </div>
        </div>
        <Sparks at={lapse + 6} x={CX + 500} y={CY - 230} size={90} angle={-50} spread={38} width={14} />
        <Sparks at={lapse + 8} x={CX - 520} y={CY + 230} size={80} angle={130} spread={34} width={14} color={C.tangerine} />

        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: CY + TILE / 2 + 70,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            gap: 26,
            fontFamily: FONT.body,
            fontWeight: 700,
            fontSize: 50,
            color: C.ink,
          }}
        >
          <PopWord at={tagline} from={30}>
            Find &amp; stack your rewards at checkout.
          </PopWord>
          <PopWord at={tagline + 5} from={30}>
            <span
              style={{
                display: 'inline-block',
                background: C.lime,
                border: `4px solid ${C.ink}`,
                borderRadius: 999,
                boxShadow: hardShadow(5),
                padding: '6px 24px',
                fontFamily: FONT.display,
                fontWeight: 800,
                fontSize: 36,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              Chrome extension
            </span>
          </PopWord>
        </div>
      </AbsoluteFill>
    </Backdrop>
  );
};
