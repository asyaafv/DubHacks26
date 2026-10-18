/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Direction B — "Clip & Save" coupon-clipper palette
        paper: '#FFF6E9',
        ink: '#141414',
        muted: '#5a5a5a',
        line: '#141414',
        cream: '#FFF6E9',
        tangerine: '#FF5C1C',
        lime: '#BCE740',
        sky: '#74C0FF',
        lilac: '#CBA6FF',
        amber: '#F5A800',
        accent: {
          DEFAULT: '#FF5C1C',
          dark: '#141414',
          soft: '#BCE740',
        },
      },
      fontFamily: {
        sans: ['"Space Grotesk"', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'sans-serif'],
        display: ['Archivo', '"Space Grotesk"', 'ui-sans-serif', 'sans-serif'],
        serif: ['Archivo', '"Space Grotesk"', 'ui-sans-serif', 'sans-serif'],
      },
      boxShadow: {
        card: '4px 4px 0 #141414',
        hard: '5px 5px 0 #141414',
        stamp: '6px 6px 0 #141414',
        pop: '8px 8px 0 #141414',
      },
    },
  },
  plugins: [],
}
