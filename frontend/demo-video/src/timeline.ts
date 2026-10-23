import words from './voiceover-words.json';

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

// Overlap between consecutive scenes, in frames.
export const TRANSITION = 12;

export type SceneId = 's1' | 's2' | 's3' | 's4' | 's5' | 's6' | 's7' | 's8' | 's9';

export type Beat = {
  id: SceneId;
  // Seconds from this scene's start to the next scene's start. Sized from a
  // brisk (~200 wpm) read of `line`; every visual cue lands inside it.
  window: number;
  line: string;
};

export const BEATS: Beat[] = [
  { id: 's1', window: 1.5, line: 'We live in a rewards world.' },
  { id: 's2', window: 3.4, line: 'Every store, every app, and every card is handing you value,' },
  { id: 's3', window: 2.9, line: "and if you're not maximizing it, you're leaving money on the table." },
  { id: 's4', window: 3.5, line: "Visa's own research across 22,000+ consumers found that" },
  { id: 's5', window: 5.4, line: 'the average American is in 17.4 loyalty programs but actively uses only 8.8.' },
  { id: 's6', window: 2.2, line: "For restaurants, it's just 1.14." },
  { id: 's7', window: 5.2, line: 'Antavo estimates that Americans miss out on up to $10 billion in loyalty savings every year.' },
  { id: 's8', window: 4.6, line: "Nobody needs another web app to fix this: 75% of people say they don't want one." },
  { id: 's9', window: 2.4, line: 'So we came up with Lapse.' },
];

export const sec = (s: number) => Math.round(s * FPS);

export const sceneStart = (id: SceneId) => {
  let t = 0;
  for (const b of BEATS) {
    if (b.id === id) return sec(t);
    t += b.window;
  }
  throw new Error(`Unknown scene ${id}`);
};

// TransitionSeries overlaps each scene with the next by TRANSITION frames, so
// every scene but the last is padded by that amount to keep starts on the beat.
export const sceneDuration = (id: SceneId) => {
  const i = BEATS.findIndex((b) => b.id === id);
  const b = BEATS[i];
  return sec(b.window) + (i < BEATS.length - 1 ? TRANSITION : 0);
};

export const TOTAL_FRAMES = sec(BEATS.reduce((a, b) => a + b.window, 0));

// Word onsets (seconds, relative to the start of each line) from the guide
// narration. `[word, onset, duration]`.
export type WordTiming = [string, number, number];
export const WORDS = words as Record<SceneId, WordTiming[]>;

// Seconds trimmed from the front of each guide clip (TTS lead-in silence).
export const VO_LEAD = 0.07;

// In-scene cue: onset of the nth match of `word` in the guide read, shifted a
// hair early so the visual lands on the word rather than after it.
export const cue = (id: SceneId, word: string, nth = 0) => {
  const matches = WORDS[id].filter(([w]) => w.toLowerCase().replace(/[^a-z0-9-']/g, '') === word.toLowerCase());
  const m = matches[nth];
  if (!m) throw new Error(`No cue "${word}" in ${id}`);
  return Math.max(0, sec(m[1] - VO_LEAD - 0.06));
};
