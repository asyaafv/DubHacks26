import React from 'react';
import { Composition } from 'remotion';
import { LapseIntro } from './LapseIntro';
import { FPS, HEIGHT, TOTAL_FRAMES, WIDTH } from './timeline';

const base = { component: LapseIntro, durationInFrames: TOTAL_FRAMES, fps: FPS, width: WIDTH, height: HEIGHT };

export const RemotionRoot: React.FC = () => (
  <>
    {/* Silent cut to play behind a live presenter. */}
    <Composition id="LapseIntro" {...base} defaultProps={{ voiceover: false, captions: false }} />
    {/* Same cut with the guide narration, as a backup if nobody can speak over it. */}
    <Composition id="LapseIntroNarrated" {...base} defaultProps={{ voiceover: true, captions: false }} />
    {/* Guide narration + teleprompter strip for practicing the read against the cues. */}
    <Composition id="LapseIntroRehearsal" {...base} defaultProps={{ voiceover: true, captions: true }} />
  </>
);
