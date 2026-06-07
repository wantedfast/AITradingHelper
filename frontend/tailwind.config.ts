import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "hsl(var(--bg))",
        surface: "hsl(var(--surface))",
        "text-primary": "hsl(var(--text))",
        muted: "hsl(var(--muted))",
        stroke: "hsl(var(--stroke))",
        accent: "hsl(var(--accent))",
        terminal: {
          bg: "#070A12",
          panel: "#0D1324",
          line: "#1D2842",
          glow: "#5CF2C2",
          blue: "#6BA8FF",
          amber: "#F9C86A",
          red: "#FF6875"
        }
      },
      boxShadow: {
        glow: "0 0 36px rgba(92, 242, 194, 0.18)",
        blue: "0 0 40px rgba(107, 168, 255, 0.16)"
      },
      fontFamily: {
        body: ["Inter", "sans-serif"],
        display: ["Instrument Serif", "serif"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "Microsoft YaHei", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "ui-monospace", "monospace"]
      },
      animation: {
        "scroll-down": "scroll-down 1.5s ease-in-out infinite",
        "role-fade-in": "role-fade-in 0.4s ease-out",
        "gradient-shift": "gradient-shift 6s ease infinite",
        "hero-drift": "hero-drift 24s ease-in-out infinite"
      }
    }
  },
  plugins: []
};

export default config;
