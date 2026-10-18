/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        lapse: '#FF5C1C',
        ink: '#141414',
        cream: '#FFF6E9',
        lime: '#BCE740',
        sky: '#74C0FF',
        amber: '#F5A800',
      },
      boxShadow: {
        card: '4px 4px 0 #141414',
        hard: '5px 5px 0 #141414',
      },
      fontFamily: {
        sans: ['"Space Grotesk"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['Archivo', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
