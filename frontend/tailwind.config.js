/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: "#0a0a1a", mid: "#12122a", deep: "#1a1a3e" },
        accent: { DEFAULT: "#7c3aed", light: "#a78bfa", soft: "rgba(124,58,237,0.15)" },
        glass: "rgba(255,255,255,0.05)",
        glass2: "rgba(255,255,255,0.08)",
        border: "rgba(124,58,237,0.2)",
        txt: { DEFAULT: "#e2e8f0", dim: "#94a3b8" },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ['"JetBrains Mono"', '"Cascadia Code"', "monospace"],
      },
      backdropBlur: { glass: "24px" },
      height: { dvh: "100dvh" },
      minHeight: { dvh: "100dvh" },
    },
  },
  plugins: [],
};
