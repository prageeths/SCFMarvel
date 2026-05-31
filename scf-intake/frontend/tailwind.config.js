/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Wells Fargo inspired palette (stagecoach red + gold)
        wf: {
          red: "#D71E2B",
          redDark: "#B31B26",
          redDarker: "#8F1620",
          gold: "#FFCD41",
          goldDark: "#E6B200",
          cream: "#FBF7EF",
          sand: "#F3EDE1",
          ink: "#2A2522",
          charcoal: "#3A3430",
          slate: "#6B635C",
          line: "#E7DFD2",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgba(42,37,34,0.06), 0 8px 24px rgba(42,37,34,0.08)",
        pop: "0 12px 40px rgba(42,37,34,0.18)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "0.3" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.25s ease-out",
        "pulse-dot": "pulse-dot 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
