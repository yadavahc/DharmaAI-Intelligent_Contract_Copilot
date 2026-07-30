import type { Config } from "tailwindcss";

/**
 * Dharma AI design tokens.
 *
 * One restrained accent (jade) against a near-black base with silver/slate
 * neutrals. Risk semantics get their own scale so a risk colour is never chosen
 * ad hoc at the call site — `text-risk-high` always means the same thing.
 *
 * Everything here is referenced through CSS variables declared in globals.css so
 * the palette is defined once and consumed by Tailwind, inline styles and
 * Recharts alike.
 */
const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: "1rem", sm: "1.5rem", lg: "2rem" },
      screens: { "2xl": "1440px" },
    },
    extend: {
      colors: {
        // ── base surfaces ──
        base: {
          950: "hsl(var(--base-950))", // page background
          900: "hsl(var(--base-900))", // raised surface
          850: "hsl(var(--base-850))",
          800: "hsl(var(--base-800))", // card
          700: "hsl(var(--base-700))", // border strong
          600: "hsl(var(--base-600))",
        },
        // ── neutral text ramp ──
        silver: {
          50: "hsl(var(--silver-50))",
          100: "hsl(var(--silver-100))",
          200: "hsl(var(--silver-200))",
          300: "hsl(var(--silver-300))",
          400: "hsl(var(--silver-400))",
          500: "hsl(var(--silver-500))",
          600: "hsl(var(--silver-600))",
        },
        // ── the single accent ──
        accent: {
          DEFAULT: "hsl(var(--accent))",
          soft: "hsl(var(--accent-soft))",
          muted: "hsl(var(--accent-muted))",
          fg: "hsl(var(--accent-fg))",
        },
        // ── risk semantics ──
        risk: {
          low: "hsl(var(--risk-low))",
          medium: "hsl(var(--risk-medium))",
          high: "hsl(var(--risk-high))",
          critical: "hsl(var(--risk-critical))",
        },
        // ── negotiation sides (Agent Theater) ──
        org: "hsl(var(--org))",
        counterparty: "hsl(var(--counterparty))",

        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
      },
      // ── consistent radii ──
      borderRadius: {
        lg: "var(--radius-lg)",
        md: "var(--radius-md)",
        sm: "var(--radius-sm)",
        xl: "var(--radius-xl)",
        "2xl": "var(--radius-2xl)",
      },
      // ── spacing scale extensions (4px base) ──
      spacing: {
        "4.5": "1.125rem",
        "13": "3.25rem",
        "18": "4.5rem",
        "22": "5.5rem",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.04em" }],
        xs: ["0.75rem", { lineHeight: "1.125rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1.0625rem", { lineHeight: "1.625rem" }],
        xl: ["1.25rem", { lineHeight: "1.75rem", letterSpacing: "-0.01em" }],
        "2xl": ["1.5rem", { lineHeight: "2rem", letterSpacing: "-0.015em" }],
        "3xl": ["1.875rem", { lineHeight: "2.25rem", letterSpacing: "-0.02em" }],
        "4xl": ["2.375rem", { lineHeight: "2.75rem", letterSpacing: "-0.025em" }],
        "5xl": ["3.25rem", { lineHeight: "1.08", letterSpacing: "-0.03em" }],
        "6xl": ["4rem", { lineHeight: "1.04", letterSpacing: "-0.035em" }],
      },
      boxShadow: {
        // Layered, low-opacity shadows read as depth rather than as a grey box.
        glass: "0 1px 0 0 hsl(var(--silver-50) / 0.04) inset, 0 8px 32px -8px hsl(0 0% 0% / 0.6)",
        "glass-lg":
          "0 1px 0 0 hsl(var(--silver-50) / 0.05) inset, 0 24px 64px -16px hsl(0 0% 0% / 0.7)",
        glow: "0 0 0 1px hsl(var(--accent) / 0.25), 0 0 24px -4px hsl(var(--accent) / 0.35)",
        "glow-sm": "0 0 16px -4px hsl(var(--accent) / 0.4)",
      },
      backgroundImage: {
        "mesh-accent":
          "radial-gradient(60% 60% at 20% 10%, hsl(var(--accent) / 0.14) 0%, transparent 60%), radial-gradient(50% 50% at 85% 25%, hsl(200 85% 55% / 0.10) 0%, transparent 55%), radial-gradient(45% 45% at 50% 95%, hsl(265 70% 60% / 0.10) 0%, transparent 55%)",
        "grid-faint":
          "linear-gradient(hsl(var(--silver-50) / 0.028) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--silver-50) / 0.028) 1px, transparent 1px)",
        shimmer:
          "linear-gradient(90deg, transparent, hsl(var(--silver-50) / 0.07), transparent)",
      },
      backgroundSize: { "grid-faint": "44px 44px" },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "70%": { transform: "scale(1.5)", opacity: "0" },
          "100%": { transform: "scale(1.5)", opacity: "0" },
        },
        "gradient-drift": {
          "0%, 100%": { transform: "translate3d(0,0,0) scale(1)" },
          "50%": { transform: "translate3d(2%, -2%, 0) scale(1.06)" },
        },
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "caret-blink": {
          "0%, 70%, 100%": { opacity: "1" },
          "20%, 50%": { opacity: "0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.16, 1, 0.3, 1) both",
        shimmer: "shimmer 1.8s infinite",
        "pulse-ring": "pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "gradient-drift": "gradient-drift 22s ease-in-out infinite",
        "accordion-down": "accordion-down 0.22s cubic-bezier(0.16, 1, 0.3, 1)",
        "accordion-up": "accordion-up 0.18s ease-out",
        "caret-blink": "caret-blink 1.2s steps(1) infinite",
      },
      transitionTimingFunction: {
        premium: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
