/** @type {import('tailwindcss').Config} */
// Tailwind is available for utility classes; the bespoke design system (tokens,
// sidebar, cards, drawer, chat) lives in src/index.css as CSS custom properties,
// mirroring the design mockup. Both read the same variables so they stay in sync.
export default {
  darkMode: ['selector', '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        accent: "var(--accent)",
        text: "var(--text)",
      },
      fontFamily: {
        ui: "var(--font-ui)",
        display: "var(--font-display)",
        data: "var(--font-data)",
      },
    },
  },
  plugins: [],
  corePlugins: { preflight: false },
};
