import { dirname } from "path";
import { fileURLToPath } from "url";

import { FlatCompat } from "@eslint/eslintrc";

/**
 * ESLint flat config.
 *
 * `next lint` is deprecated in Next.js 15.5 and removed in 16 — and with no
 * config present it drops into an interactive prompt, which hangs CI forever.
 * This is the migration Next recommends: the ESLint CLI driving the same
 * `eslint-config-next` rules through FlatCompat.
 */
const compat = new FlatCompat({
  baseDirectory: dirname(fileURLToPath(import.meta.url)),
});

const config = [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "out/**",
      "playwright-report/**",
      "test-results/**",
      "next-env.d.ts",
    ],
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Unused function args are often part of a signature we must satisfy
      // (React event handlers, Playwright fixtures); an underscore prefix marks
      // them as deliberate.
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
];

export default config;
