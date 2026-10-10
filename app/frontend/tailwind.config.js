/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        // The colours live in src/style.css as CSS variables: one place for the brand and the dark theme
        fb: {
          blue: 'rgb(var(--c-brand) / <alpha-value>)',
          'blue-dark': 'rgb(var(--c-brand-dark) / <alpha-value>)',
          'blue-classic': 'rgb(var(--c-brand-dark) / <alpha-value>)',
          canvas: 'rgb(var(--c-canvas) / <alpha-value>)',
          card: 'rgb(var(--c-card) / <alpha-value>)',
          line: 'rgb(var(--c-line) / <alpha-value>)',
          'line-strong': 'rgb(var(--c-line-strong) / <alpha-value>)',
          icon: 'rgb(var(--c-icon) / <alpha-value>)',
          text: 'rgb(var(--c-text) / <alpha-value>)',
          secondary: 'rgb(var(--c-secondary) / <alpha-value>)',
          hover: 'rgb(var(--c-hover) / <alpha-value>)',
          danger: 'rgb(var(--c-danger) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: [
          'Segoe UI',
          'Helvetica Neue',
          'Helvetica',
          'Arial',
          'system-ui',
          '-apple-system',
          'sans-serif',
        ],
      },
      boxShadow: {
        fb: '0 1px 2px rgba(0, 0, 0, 0.1)',
        'fb-card': '0 1px 2px rgba(0, 0, 0, 0.08)',
      },
    },
  },
  plugins: [],
};
