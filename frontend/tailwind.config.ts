import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          950: '#0b0d12',
          900: '#11141a',
          800: '#171b23',
          700: '#222836',
        },
        text: {
          primary: '#f2f4f8',
          secondary: '#a8b0bf',
          muted: '#7e8797',
        },
        accent: {
          blue: '#5b8cff',
          green: '#33b07a',
          amber: '#c99a46',
          red: '#d05f73',
        },
      },
      boxShadow: {
        card: '0 1px 1px rgba(0,0,0,0.2), 0 10px 30px rgba(0,0,0,0.25)',
      },
      borderRadius: {
        xl: '14px',
      },
    },
  },
  plugins: [],
} satisfies Config;
