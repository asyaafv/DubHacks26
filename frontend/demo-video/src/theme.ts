import { loadFont as loadArchivo } from '@remotion/google-fonts/Archivo';
import { loadFont as loadSpaceGrotesk } from '@remotion/google-fonts/SpaceGrotesk';

const archivo = loadArchivo('normal', {
  weights: ['600', '700', '800', '900'],
  subsets: ['latin'],
});
const spaceGrotesk = loadSpaceGrotesk('normal', {
  weights: ['400', '500', '700'],
  subsets: ['latin'],
});

// Mirrors the "Clip & Save" palette in frontend/web/tailwind.config.js
export const C = {
  paper: '#FFF6E9',
  ink: '#141414',
  muted: '#5a5a5a',
  tangerine: '#FF5C1C',
  lime: '#BCE740',
  sky: '#74C0FF',
  lilac: '#CBA6FF',
  amber: '#F5A800',
  dust: '#D9D2C5',
};

export const FONT = {
  display: archivo.fontFamily,
  body: spaceGrotesk.fontFamily,
};

export const STROKE = 6;

export const hardShadow = (n = 8) => `${n}px ${n}px 0 ${C.ink}`;
