/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        fb: {
          blue: '#1877F2',
          'blue-dark': '#166FE5',
          'blue-classic': '#3B5998',
          canvas: '#F0F2F5',
          card: '#FFFFFF',
          line: '#E4E6EB',
          'line-strong': '#D8DDE4',
          icon: '#898F9C',
          text: '#050505',
          secondary: '#65676B',
          hover: '#E7F3FF',
          danger: '#E41E3F',
        },
        modme: {
          orange: '#1877F2',
          dark: '#050505',
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
