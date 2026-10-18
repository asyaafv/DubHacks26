import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { evolvePath } from '@remotion/paths';
import { makePie } from '@remotion/shapes';
import { noise2D } from '@remotion/noise';
import { Backdrop, Headline, PopWord, clamp, ease, useSpring } from '../components/primitives';
import { BrowserWindow } from '../components/icons';
import { C, FONT, hardShadow } from '../theme';
import { cue } from '../timeline';

const RING_R = 300;
const RING_Y = 465;

const StrikeX: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const a = 'M 40 40 L 520 330';
  const b = 'M 520 40 L 40 330';
  const pa = evolvePath(ease(frame, at, at + 6), a);
  const pb = evolvePath(ease(frame, at + 4, at + 10), b);
  return (
    <svg width={560} height={370} style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible' }}>
      {[a, b].map((d, i) => (
        <path key={`s${i}`} d={d} stroke={C.ink} strokeWidth={58} strokeLinecap="round" fill="none" {...(i ? pb : pa)} transform="translate(7 7)" />
      ))}
      {[a, b].map((d, i) => (
        <path key={d} d={d} stroke={C.tangerine} strokeWidth={40} strokeLinecap="round" fill="none" {...(i ? pb : pa)} />
      ))}
    </svg>
  );
};

const Burst: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const t = ease(frame, at, at + 16);
  const rays = 16;
  return (
    <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
      {new Array(rays).fill(0).map((_, i) => {
        const a = (i / rays) * Math.PI * 2 + 0.2;
        if (Math.sin(a) > 0.45) return null;
        const r0 = RING_R + 40 + t * 60;
        const r1 = r0 + 40 + 120 * t * (i % 2 ? 0.7 : 1);
        return (
          <line
            key={i}
            x1={960 + Math.cos(a) * r0}
            y1={RING_Y + Math.sin(a) * r0}
            x2={960 + Math.cos(a) * r1}
            y2={RING_Y + Math.sin(a) * r1}
            stroke={C.ink}
            strokeWidth={14}
            strokeLinecap="round"
            opacity={t > 0.02 ? interpolate(t, [0, 0.2, 1], [0, 1, 0.9]) : 0}
          />
        );
      })}
    </svg>
  );
};

export const S8NoWebApp: React.FC = () => {
  const frame = useCurrentFrame();
  const web = cue('s8', 'web');
  const fix = cue('s8', 'fix');
  const seventyFive = cue('s8', 'seventy-five');
  const people = cue('s8', 'people');
  const dont = cue('s8', "don't");

  const browser = useSpring(web - 2, { damping: 11, stiffness: 170 });
  const hit = fix + 2;
  const browserShake = frame > hit ? Math.sin((frame - hit) * 2.2) * 14 * Math.max(0, 1 - (frame - hit) / 12) : 0;

  const revealAt = seventyFive - 6;
  const reveal = ease(frame, revealAt, revealAt + 12, [0, 1], (t) => 1 - (1 - t) ** 3);
  const phaseAOut = ease(frame, revealAt, revealAt + 8);

  const slam = useSpring(seventyFive - 2, { damping: 10, stiffness: 180, mass: 0.9 });
  const impact = seventyFive + 4;
  const shakeAmt = frame > impact ? 22 * Math.max(0, 1 - (frame - impact) / 14) : 0;
  const shakeX = noise2D('sx', frame / 2, 0) * shakeAmt;
  const shakeY = noise2D('sy', frame / 2, 5) * shakeAmt;
  const pct = Math.round(interpolate(frame, [seventyFive - 2, seventyFive + 12], [0, 75], { ...clamp, easing: (t) => 1 - (1 - t) ** 3 }));
  const ringProgress = ease(frame, seventyFive, seventyFive + 22) * 0.75;
  const ring = makePie({ radius: RING_R, progress: Math.max(0.0001, ringProgress), closePath: false });
  const throb = frame > seventyFive + 20 ? 1 + Math.sin((frame - seventyFive - 20) / 5) * 0.015 : 1;

  return (
    <Backdrop>
      <AbsoluteFill style={{ opacity: 1 - phaseAOut, transform: `scale(${1 - phaseAOut * 0.15})` }}>
        <div style={{ position: 'absolute', left: 130, top: 250 }}>
          <Headline size={128}>
            <PopWord at={0}>Nobody</PopWord> <PopWord at={cue('s8', 'needs')}>needs</PopWord>
            <br />
            <PopWord at={cue('s8', 'another')}>another</PopWord>
            <br />
            <PopWord at={web} style={{ color: C.lilac, WebkitTextStroke: `4px ${C.ink}`, textShadow: hardShadow(7) }}>
              web app.
            </PopWord>
          </Headline>
        </div>
        <div
          style={{
            position: 'absolute',
            left: 1180,
            top: 330,
            transform: `translateX(${browserShake}px) translateY(${(1 - browser) * 200}px) rotate(${(1 - browser) * 10 + 3}deg) scale(${0.7 + 0.3 * browser})`,
            opacity: browser,
          }}
        >
          <div style={{ filter: `drop-shadow(12px 12px 0 ${C.ink})` }}>
            <BrowserWindow w={560} />
          </div>
          <StrikeX at={fix - 2} />
        </div>
      </AbsoluteFill>

      <AbsoluteFill style={{ clipPath: `circle(${reveal * 1250}px at 50% 46%)`, backgroundColor: C.tangerine }}>
        <Backdrop color={C.tangerine} dot="rgba(20,20,20,0.12)">
          <AbsoluteFill style={{ transform: `translate(${shakeX}px, ${shakeY}px)` }}>
            <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
              <circle cx={960} cy={RING_Y} r={RING_R} fill="none" stroke={C.ink} strokeOpacity={0.25} strokeWidth={34} strokeDasharray="2 30" strokeLinecap="round" />
              <g transform={`translate(${960 - RING_R} ${RING_Y - RING_R})`}>
                <path d={ring.path} fill="none" stroke={C.ink} strokeWidth={46} strokeLinecap="round" transform="translate(6 6)" />
                <path d={ring.path} fill="none" stroke={C.lime} strokeWidth={34} strokeLinecap="round" />
              </g>
            </svg>
            <Burst at={impact - 2} />
            <div
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                top: RING_Y - 170,
                textAlign: 'center',
                fontFamily: FONT.display,
                fontWeight: 900,
                fontSize: 300,
                lineHeight: '340px',
                letterSpacing: '-0.05em',
                color: C.paper,
                WebkitTextStroke: `9px ${C.ink}`,
                textShadow: hardShadow(16),
                fontVariantNumeric: 'tabular-nums',
                opacity: interpolate(frame, [seventyFive - 2, seventyFive + 1], [0, 1], clamp),
                transform: `scale(${interpolate(slam, [0, 1], [2.8, 1]) * throb}) rotate(${(1 - slam) * -14}deg)`,
              }}
            >
              {pct}%
            </div>
            <div style={{ position: 'absolute', left: 0, right: 0, top: 850, textAlign: 'center', wordSpacing: '0.12em' }}>
              <Headline size={80}>
                <PopWord at={people - 3}>of people</PopWord> <PopWord at={cue('s8', 'say')}>say they</PopWord>{' '}
                <PopWord at={dont} rotate={-8} style={{ background: C.ink, color: C.paper, padding: '0 18px', borderRadius: 14 }}>
                  don't
                </PopWord>{' '}
                <PopWord at={cue('s8', 'want')}>want one.</PopWord>
              </Headline>
            </div>
          </AbsoluteFill>
        </Backdrop>
      </AbsoluteFill>
    </Backdrop>
  );
};
