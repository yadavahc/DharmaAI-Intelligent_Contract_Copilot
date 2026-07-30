"use client";

/**
 * Ambient animated background for the landing page and dashboard.
 *
 * Performance and graceful degradation are the whole design constraint here, so
 * the component picks its own fidelity:
 *
 *   1. `prefers-reduced-motion`, or a small viewport, or ≤4 logical cores, or
 *      `navigator.connection.saveData` → a static CSS gradient mesh. No canvas,
 *      no WebGL context, no rAF loop.
 *   2. Otherwise → a low-density React Three Fiber particle field (a single
 *      `Points` object, one draw call, ~900 vertices) drifting slowly.
 *
 * R3F is loaded via `next/dynamic` with `ssr: false` so three.js never enters the
 * server bundle or the initial page payload — it arrives only for clients that
 * will actually use it. The canvas is `pointer-events-none` and `aria-hidden`:
 * it is decoration and must never intercept a click or reach a screen reader.
 */

import dynamic from "next/dynamic";
import * as React from "react";

const ParticleField = dynamic(() => import("./particle-field"), {
  ssr: false,
  loading: () => null,
});

export type BackgroundVariant = "particles" | "mesh" | "auto";

function useCapability(variant: BackgroundVariant) {
  // Start with the cheap option so the first paint never includes WebGL, then
  // upgrade after mount if the device looks capable.
  const [mode, setMode] = React.useState<"mesh" | "particles">("mesh");

  React.useEffect(() => {
    if (variant === "mesh") {
      setMode("mesh");
      return;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const smallViewport = window.matchMedia("(max-width: 768px)").matches;
    const cores = navigator.hardwareConcurrency ?? 4;
    const saveData =
      (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData ??
      false;

    const capable = !reduceMotion && !smallViewport && cores > 4 && !saveData;
    setMode(variant === "particles" || capable ? "particles" : "mesh");

    // Respond if the user toggles reduced motion or resizes across the breakpoint.
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sizeQuery = window.matchMedia("(max-width: 768px)");
    const onChange = () => {
      const stillCapable =
        !motionQuery.matches && !sizeQuery.matches && cores > 4 && !saveData;
      setMode(stillCapable ? "particles" : "mesh");
    };
    motionQuery.addEventListener("change", onChange);
    sizeQuery.addEventListener("change", onChange);
    return () => {
      motionQuery.removeEventListener("change", onChange);
      sizeQuery.removeEventListener("change", onChange);
    };
  }, [variant]);

  return mode;
}

export function AmbientBackground({
  variant = "auto",
  intensity = 1,
  className = "",
}: {
  variant?: BackgroundVariant;
  intensity?: number;
  className?: string;
}) {
  const mode = useCapability(variant);

  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none fixed inset-0 -z-10 overflow-hidden ${className}`}
    >
      {/* Always present: the gradient mesh is the base layer and the fallback. */}
      <div
        className="absolute inset-0 bg-mesh-accent animate-gradient-drift will-change-transform"
        style={{ opacity: 0.85 * intensity }}
      />
      {/* Faint grid, masked to fade out toward the edges. */}
      <div
        className="absolute inset-0 bg-grid-faint bg-grid-faint"
        style={{
          maskImage: "radial-gradient(ellipse 75% 55% at 50% 40%, #000 40%, transparent 100%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 75% 55% at 50% 40%, #000 40%, transparent 100%)",
        }}
      />
      {mode === "particles" && <ParticleField intensity={intensity} />}
      {/* Vignette: keeps text legible over whatever is behind it. */}
      <div className="absolute inset-0 bg-gradient-to-b from-base-950/20 via-transparent to-base-950/85" />
    </div>
  );
}
