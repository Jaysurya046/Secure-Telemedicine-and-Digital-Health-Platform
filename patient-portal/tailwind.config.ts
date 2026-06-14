import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#172033',
        mint: '#2f9e8f',
        coral: '#e46d5f',
        gold: '#d5a11e'
      }
    }
  },
  plugins: []
};

export default config;
