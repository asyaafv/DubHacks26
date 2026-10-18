/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#F6F4EF',
        ink: '#17261E',
        muted: '#5E7368',
        line: '#E3DED2',
        accent: {
          DEFAULT: '#1B6B45',
          dark: '#145536',
          soft: '#E5F2EB',
        },
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', 'Segoe UI', 'Helvetica Neue', 'Arial', 'sans-serif'],
        serif: ['Iowan Old Style', 'Palatino Linotype', 'Palatino', 'Georgia', 'serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(23, 38, 30, 0.04), 0 10px 28px rgba(23, 38, 30, 0.05)',
      },
    },
  },
  plugins: [],
}
