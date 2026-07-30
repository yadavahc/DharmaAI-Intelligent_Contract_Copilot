"use client";

/**
 * Motion primitives.
 *
 * All animation goes through these so timing and easing stay consistent — one
 * spring, one easing curve, one stagger interval across the whole app. Every
 * component honours `prefers-reduced-motion` by collapsing to a static render
 * rather than merely shortening the duration.
 */

import {
  AnimatePresence,
  type Variants,
  motion,
  useInView,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from "framer-motion";
import * as React from "react";

import { cn } from "@/lib/utils";

export const EASE_PREMIUM = [0.16, 1, 0.3, 1] as const;
export const SPRING_SOFT = { type: "spring", stiffness: 220, damping: 28, mass: 0.9 } as const;

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 14 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: EASE_PREMIUM } },
};

export const staggerContainer: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
};

/** Page-level transition wrapper. */
export function PageTransition({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.35, ease: EASE_PREMIUM }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Staggered list/grid container. Children should be `<StaggerItem>`. */
export function Stagger({
  children,
  className,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  as?: "div" | "ul" | "section";
}) {
  const reduce = useReducedMotion();
  const Comp = motion[as];
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <Comp
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
      className={className}
    >
      {children}
    </Comp>
  );
}

export function StaggerItem({
  children,
  className,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  as?: "div" | "li";
}) {
  const reduce = useReducedMotion();
  const Comp = motion[as];
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <Comp variants={fadeUp} className={className}>
      {children}
    </Comp>
  );
}

/** Reveal on scroll — used for landing-page sections. */
export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const reduce = useReducedMotion();

  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 22 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.6, delay, ease: EASE_PREMIUM }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/**
 * Animated number counter for KPIs.
 *
 * Spring-driven rather than linear so the value settles instead of stopping dead,
 * and it re-animates when `value` changes (e.g. live risk score during
 * negotiation), not just on mount.
 */
export function AnimatedNumber({
  value,
  decimals = 0,
  suffix = "",
  prefix = "",
  className,
  duration,
}: {
  value: number;
  decimals?: number;
  suffix?: string;
  prefix?: string;
  className?: string;
  duration?: number;
}) {
  const reduce = useReducedMotion();
  const motionValue = useMotionValue(0);
  const spring = useSpring(motionValue, {
    stiffness: 90,
    damping: 22,
    duration: duration ? duration * 1000 : undefined,
  });
  const display = useTransform(spring, (latest) =>
    `${prefix}${latest.toFixed(decimals)}${suffix}`,
  );

  React.useEffect(() => {
    motionValue.set(Number.isFinite(value) ? value : 0);
  }, [value, motionValue]);

  if (reduce) {
    return (
      <span className={className}>
        {prefix}
        {value.toFixed(decimals)}
        {suffix}
      </span>
    );
  }
  return <motion.span className={className}>{display}</motion.span>;
}

/** Smooth expand/collapse for clause bodies. */
export function Collapse({
  open,
  children,
  className,
}: {
  open: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          key="content"
          initial={reduce ? { height: "auto", opacity: 1 } : { height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={reduce ? { height: "auto", opacity: 0 } : { height: 0, opacity: 0 }}
          transition={{ duration: 0.28, ease: EASE_PREMIUM }}
          className={cn("overflow-hidden", className)}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * "Agent is thinking" indicator — three staggered dots plus a label.
 * Shown while a negotiation turn is being generated.
 */
export function ThinkingIndicator({
  label = "thinking",
  tone = "accent",
  className,
}: {
  label?: string;
  tone?: "accent" | "org" | "counterparty";
  className?: string;
}) {
  const toneClass =
    tone === "org" ? "bg-org" : tone === "counterparty" ? "bg-counterparty" : "bg-accent";
  return (
    <div className={cn("flex items-center gap-2 text-xs text-silver-400", className)}>
      <div className="flex gap-1" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className={cn("size-1.5 rounded-full", toneClass)}
            animate={{ opacity: [0.25, 1, 0.25], y: [0, -3, 0] }}
            transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.16, ease: "easeInOut" }}
          />
        ))}
      </div>
      <span className="italic">{label}</span>
    </div>
  );
}

/** A live pulsing dot, for "streaming" / "online" states. */
export function PulseDot({
  className,
  tone = "accent",
}: {
  className?: string;
  tone?: "accent" | "critical" | "medium";
}) {
  const color =
    tone === "critical" ? "bg-risk-critical" : tone === "medium" ? "bg-risk-medium" : "bg-accent";
  return (
    <span className={cn("relative inline-flex size-2", className)}>
      <span className={cn("absolute inset-0 rounded-full opacity-70 animate-pulse-ring", color)} />
      <span className={cn("relative size-2 rounded-full", color)} />
    </span>
  );
}

/** Typewriter reveal used for streamed agent messages. */
export function StreamingText({
  text,
  className,
  showCaret = false,
}: {
  text: string;
  className?: string;
  showCaret?: boolean;
}) {
  return (
    <span className={className}>
      {text}
      {showCaret && (
        <span className="ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 animate-caret-blink bg-accent" />
      )}
    </span>
  );
}

export { motion, AnimatePresence, useReducedMotion };
