/** @type {import('tailwindcss').Config} */
export default {
  // darkMode: 'class' → toggle utente via <html class="dark">
  darkMode: "class",
  // Content da scansionare per il purge.
  // Include sia la SPA Vue che i template Jinja del backend (stessa palette).
  content: [
    "./index.html",
    "./src/**/*.{vue,ts,tsx,js,jsx,html}",
    "../backend/app/templates/**/*.html",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        serif: [
          "'Source Serif Pro'",
          "ui-serif",
          "Georgia",
          "serif",
        ],
      },
      // Palette base estesa quando avremo identità visiva definitiva.
      // Per ora ci affidiamo ai default di Tailwind (slate, blue, ecc.).
    },
  },
  plugins: [],
};
