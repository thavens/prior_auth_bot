/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        pi: {
          bg: '#0e0e0e',
          surface: 'rgba(255,255,255,0.02)',
          'surface-hover': 'rgba(255,255,255,0.05)',
          border: 'rgba(255,255,255,0.05)',
          'border-card': 'rgba(255,255,255,0.1)',
          'border-hover': 'rgba(255,255,255,0.2)',
          text: '#ffffff',
          body: 'rgba(255,255,255,0.92)',
          muted: 'rgba(255,255,255,0.50)',
          subtle: 'rgba(255,255,255,0.44)',
          green: '#55cc58',
          red: '#c52626',
          blue: '#3e77f1',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      maxWidth: {
        pi: '1400px',
      },
      transitionTimingFunction: {
        pi: 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      backdropBlur: {
        nav: '12px',
      },
    },
  },
  plugins: [],
}
