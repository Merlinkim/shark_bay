import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          950: '#0c0f14',
          900: '#12161d',
          850: '#151a22',
          800: '#1a202a',
          700: '#252d3a',
        },
        text: {
          primary: '#eef2f7',
          secondary: '#a9b2c1',
          muted: '#818b9b',
        },
        accent: {
          blue: '#6f8fdc',
          green: '#4f9b79',
          amber: '#ac9060',
          red: '#b97584',
        },
      },
      boxShadow: {
        card: '0 1px 1px rgba(0,0,0,0.15), 0 6px 20px rgba(0,0,0,0.16)',
      },
      borderRadius: {
        xl: '12px',
      },
    },
  },
  plugins: [],
} satisfies Config;
