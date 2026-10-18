# Lapse demo intro video

A ~31s animated infographic that opens the Lapse demo, built with
[Remotion](https://www.remotion.dev/) (React → MP4) in the web app's
"Clip & Save" palette.

Libraries: `remotion`, `@remotion/transitions` (scene transitions),
`@remotion/paths` (flowchart connectors, strike-through), `@remotion/shapes`
(75% ring, confetti stars), `@remotion/noise` (bill flutter, chip drift, screen
shake), `@remotion/motion-blur` (thrown cash), `@remotion/google-fonts`
(Archivo + Space Grotesk).

## Commands

```bash
npm install
npm run studio            # live preview / scrub
npm run render            # out/lapse-intro.mp4 — silent, for a live presenter
npm run render:narrated   # out/lapse-intro-narrated.mp4 — with the guide voice
npm run render:rehearsal  # out/lapse-intro-rehearsal.mp4 — guide voice + teleprompter strip
```

## Script and cue sheet

Each scene starts on the first word of its line. The presenter should start
speaking the moment the video starts and keep a brisk pace (~200 words/min).

| Start | Scene | Line |
| --- | --- | --- |
| 0:00.0 | Rewards world | We live in a rewards world. |
| 0:01.5 | Flowchart | Every store, every app, and every card is handing you value, |
| 0:04.9 | Cash on the table | and if you're not maximizing it, you're leaving money on the table. |
| 0:07.8 | Visa research | Visa's own research across 22,000+ consumers found that |
| 0:11.3 | 17.4 vs 8.8 | the average American is in 17.4 loyalty programs but actively uses only 8.8. |
| 0:16.7 | Restaurants | For restaurants, it's just 1.14. |
| 0:18.9 | $10 billion | Antavo estimates that Americans miss out on up to $10 billion in loyalty savings every year. |
| 0:24.1 | 75% | Nobody needs another web app to fix this: 75% of people say they don't want one. |
| 0:28.7 | Lapse | So we came up with Lapse. |

Timing lives in `src/timeline.ts`. `BEATS[].window` is the time each line gets;
in-scene animations are keyed to word onsets from the guide narration
(`src/voiceover-words.json`, `public/vo/*.mp3`, generated with Microsoft Edge
TTS `en-US-AndrewNeural` at +20% rate). To retime for a different speaker,
change the windows; word cues inside a scene shift with the scene.

The Lapse icon is `public/lapse-icon.png`.
