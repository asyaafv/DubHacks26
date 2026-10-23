import React from 'react';
import { AbsoluteFill, Easing, Html5Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { TransitionSeries, linearTiming, type TransitionPresentation } from '@remotion/transitions';
import { slide } from '@remotion/transitions/slide';
import { wipe } from '@remotion/transitions/wipe';
import { clockWipe } from '@remotion/transitions/clock-wipe';
import { iris } from '@remotion/transitions/iris';
import { S1RewardsWorld } from './scenes/S1RewardsWorld';
import { S2Flowchart } from './scenes/S2Flowchart';
import { S3MoneyOnTable } from './scenes/S3MoneyOnTable';
import { S4VisaResearch } from './scenes/S4VisaResearch';
import { S5Programs } from './scenes/S5Programs';
import { S6Restaurants } from './scenes/S6Restaurants';
import { S7TenBillion } from './scenes/S7TenBillion';
import { S8NoWebApp } from './scenes/S8NoWebApp';
import { S9Lapse } from './scenes/S9Lapse';
import { BEATS, FPS, HEIGHT, TRANSITION, VO_LEAD, WIDTH, WORDS, sceneDuration, sceneStart, type SceneId } from './timeline';
import { C, FONT } from './theme';

export type LapseIntroProps = {
  voiceover: boolean;
  captions: boolean;
};

const SCENES: Record<SceneId, React.FC> = {
  s1: S1RewardsWorld,
  s2: S2Flowchart,
  s3: S3MoneyOnTable,
  s4: S4VisaResearch,
  s5: S5Programs,
  s6: S6Restaurants,
  s7: S7TenBillion,
  s8: S8NoWebApp,
  s9: S9Lapse,
};

// Transition into each scene after the first.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const INTO: Partial<Record<SceneId, TransitionPresentation<any>>> = {
  s2: slide({ direction: 'from-right' }),
  s3: wipe({ direction: 'from-bottom' }),
  s4: slide({ direction: 'from-bottom' }),
  s5: slide({ direction: 'from-right' }),
  s6: slide({ direction: 'from-right' }),
  s7: clockWipe({ width: WIDTH, height: HEIGHT }),
  s8: wipe({ direction: 'from-left' }),
  s9: iris({ width: WIDTH, height: HEIGHT }),
};

const timing = linearTiming({ durationInFrames: TRANSITION, easing: Easing.bezier(0.65, 0, 0.35, 1) });

const Prompter: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const idx = Math.max(0, BEATS.findIndex((b, i) => frame < (BEATS[i + 1] ? sceneStart(BEATS[i + 1].id) : Infinity)));
  const beat = BEATS[idx];
  const next = BEATS[idx + 1];
  const t = (frame - sceneStart(beat.id)) / fps + VO_LEAD;
  const spoken = WORDS[beat.id].filter(([, at]) => at <= t).length;
  const words = beat.line.split(' ');
  const ratio = words.length / WORDS[beat.id].length;
  const lit = Math.round(spoken * ratio);
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end' }}>
      <div
        style={{
          margin: '0 60px 40px',
          padding: '22px 34px',
          borderRadius: 22,
          background: 'rgba(20,20,20,0.88)',
          color: C.paper,
          fontFamily: FONT.body,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 24, opacity: 0.7, marginBottom: 6 }}>
          <span>
            REHEARSAL · scene {idx + 1}/{BEATS.length}
          </span>
          <span style={{ fontVariantNumeric: 'tabular-nums' }}>{(frame / fps).toFixed(1)}s</span>
        </div>
        <div style={{ fontSize: 46, fontWeight: 700, lineHeight: 1.25 }}>
          {words.map((w, i) => (
            <span key={i} style={{ color: i < lit ? C.lime : 'rgba(255,246,233,0.55)' }}>
              {w}{' '}
            </span>
          ))}
        </div>
        {next && <div style={{ fontSize: 28, opacity: 0.5, marginTop: 6 }}>next: {next.line}</div>}
      </div>
    </AbsoluteFill>
  );
};

export const LapseIntro: React.FC<LapseIntroProps> = ({ voiceover, captions }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: C.paper }}>
      <TransitionSeries>
        {BEATS.flatMap((b) => {
          const Scene = SCENES[b.id];
          const into = INTO[b.id];
          return [
            ...(into ? [<TransitionSeries.Transition key={`t-${b.id}`} presentation={into} timing={timing} />] : []),
            <TransitionSeries.Sequence key={b.id} durationInFrames={sceneDuration(b.id)}>
              <Scene />
            </TransitionSeries.Sequence>,
          ];
        })}
      </TransitionSeries>
      {voiceover &&
        BEATS.map((b) => (
          <Sequence key={`vo-${b.id}`} from={sceneStart(b.id)} layout="none">
            <Html5Audio src={staticFile(`vo/${b.id}.mp3`)} trimBefore={Math.round(VO_LEAD * FPS)} />
          </Sequence>
        ))}
      {captions && <Prompter />}
    </AbsoluteFill>
  );
};
