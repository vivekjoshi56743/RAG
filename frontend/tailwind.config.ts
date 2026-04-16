import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
      },
      boxShadow: {
        soft: "0 6px 24px -12px rgba(15, 23, 42, 0.35)",
      },
      borderRadius: {
        "2.5xl": "1.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
