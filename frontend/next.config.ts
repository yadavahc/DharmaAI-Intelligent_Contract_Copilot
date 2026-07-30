import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // `standalone` produces a minimal server bundle for the Docker image, which
  // copies `.next/standalone` and runs `node server.js`.
  //
  // Locally, `npm run start` (`next start`) prints a warning that it "does not
  // work with output: standalone" — it does serve correctly, and the Playwright
  // suite runs against it. The warning is about the standalone bundle not being
  // the thing served, which only matters in the container.
  output: "standalone",
  eslint: {
    // Lint is a separate `npm run lint` step; a lint warning should not break a
    // demo build.
    ignoreDuringBuilds: true,
  },
  experimental: {
    // three.js and Monaco ship huge ESM barrels; this keeps imports tree-shaken.
    optimizePackageImports: ["lucide-react", "recharts", "framer-motion"],
  },
  async headers() {
    return [
      {
        // SSE must not be buffered or cached anywhere in the chain, or the
        // Agent Theater arrives all at once at the end.
        source: "/api/proxy/:path*",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-transform" },
          { key: "X-Accel-Buffering", value: "no" },
        ],
      },
    ];
  },
};

export default nextConfig;
