import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        atlasly: {
          bg: '#f5f1e8',
          paper: '#fffdf8',
          ink: '#121412',
          muted: '#5f6359',
          line: '#dad3c2',
          teal: '#0f7f6f',
          rust: '#bc5629',
          slate: '#1c2a31',
          ok: '#1e8c5a',
          warn: '#c97a15',
          bad: '#b34b35',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        lg: '0.5rem',
        md: '0.375rem',
        sm: '0.25rem',
      },
    },
  },
  plugins: [],
}

export default config
