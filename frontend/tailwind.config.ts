import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: '#07090d',
          panel: '#10151d',
          border: '#1c2632',
          muted: '#6f8399',
          text: '#d7e4f0',
        },
        neon: {
          cyan: '#29d3ff',
          green: '#36ff8b',
          amber: '#ffcc4d',
          red: '#ff4d6d',
        },
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(41,211,255,0.2), 0 0 18px rgba(41,211,255,0.15)',
      },
    },
  },
  plugins: [],
} satisfies Config;
