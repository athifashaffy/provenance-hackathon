/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        aegis: {
          blue: '#2f4fb0',
          deep: '#1f3a8a',
          ink: '#16213e',
          red: '#d83434',
          muted: '#5b6b8c',
          line: '#c7d0e6',
          bg: '#f1f3f7',
          green: '#1f6b4f',
          amber: '#b9842b',
        },
      },
      fontFamily: {
        display: ['Rajdhani', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};
