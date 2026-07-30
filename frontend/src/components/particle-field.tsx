"use client";

/**
 * Low-density R3F particle field. Loaded only on capable clients — see
 * `ambient-background.tsx` for the gating logic.
 *
 * Kept deliberately cheap:
 *   * one `Points` object → one draw call, ~900 vertices
 *   * positions generated once into a `Float32Array` and never reallocated
 *   * per-frame work is two rotation assignments, not a per-vertex CPU loop
 *   * `dpr` capped at 1.5 so 4K displays don't render 4× the pixels
 *   * `frameloop="demand"`… not used here (we need continuous drift), but the
 *     renderer pauses automatically when the canvas scrolls out of view via
 *     `Canvas`'s default visibility handling.
 */

import { Canvas, useFrame } from "@react-three/fiber";
import * as React from "react";
import * as THREE from "three";

const PARTICLE_COUNT = 900;
const FIELD_RADIUS = 9;

function Particles({ intensity }: { intensity: number }) {
  const pointsRef = React.useRef<THREE.Points>(null);

  // Generated once. Points are distributed in a spherical shell so the field
  // reads as depth rather than as a flat sheet of dots.
  const { positions, sizes } = React.useMemo(() => {
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    const sizes = new Float32Array(PARTICLE_COUNT);
    for (let i = 0; i < PARTICLE_COUNT; i += 1) {
      const radius = FIELD_RADIUS * (0.45 + Math.random() * 0.55);
      const theta = Math.random() * Math.PI * 2;
      // acos gives an even distribution over the sphere; plain uniform phi clumps
      // points at the poles.
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta) * 0.6;
      positions[i * 3 + 2] = radius * Math.cos(phi);
      sizes[i] = 0.012 + Math.random() * 0.03;
    }
    return { positions, sizes };
  }, []);

  useFrame((state) => {
    if (!pointsRef.current) return;
    const t = state.clock.elapsedTime;
    // Rotate the whole object: constant cost regardless of particle count.
    pointsRef.current.rotation.y = t * 0.028;
    pointsRef.current.rotation.x = Math.sin(t * 0.09) * 0.12;
  });

  const geometry = React.useMemo(() => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("size", new THREE.BufferAttribute(sizes, 1));
    return geo;
  }, [positions, sizes]);

  // Dispose GPU resources on unmount; R3F does not free manually-created
  // geometries/materials for us.
  React.useEffect(() => () => geometry.dispose(), [geometry]);

  return (
    <points ref={pointsRef} geometry={geometry}>
      <pointsMaterial
        size={0.038}
        sizeAttenuation
        transparent
        opacity={0.5 * intensity}
        color="#5eead4"
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

export default function ParticleField({ intensity = 1 }: { intensity?: number }) {
  return (
    <Canvas
      className="absolute inset-0"
      camera={{ position: [0, 0, 12], fov: 55 }}
      dpr={[1, 1.5]}
      gl={{ antialias: false, alpha: true, powerPreference: "low-power" }}
      style={{ pointerEvents: "none" }}
    >
      <Particles intensity={intensity} />
    </Canvas>
  );
}
