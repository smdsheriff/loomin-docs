/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        dark: {
          bg: '#ffffff',
          sidebar: '#f6f8fa',
          border: '#d1d9e0',
          text: '#1f2328',
          muted: '#656d76',
          accent: '#2563eb',
          'accent-hover': '#1d4ed8',
          card: '#f0f3f6',
          hover: '#eaeef2',
          success: '#1a7f37',
          warning: '#9a6700',
          danger: '#cf222e',
        },
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Noto Sans',
          'Helvetica',
          'Arial',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'SF Mono',
          'Menlo',
          'Consolas',
          'Liberation Mono',
          'monospace',
        ],
      },
    },
  },
  plugins: [],
};
