import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Microsoft YaHei", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
} satisfies Config;
