"use client";

/**
 * Base UI primitives (shadcn/ui conventions: Radix + CVA + Tailwind tokens).
 *
 * Collected in one module rather than one file per component: it keeps the design
 * system reviewable at a glance and every variant honours the shared tokens, so
 * nothing drifts into looking templated.
 */

import { Slot } from "@radix-ui/react-slot";
import { type VariantProps, cva } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

/* ── Button ─────────────────────────────────────────────────────────────── */

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium " +
    "transition-all duration-200 ease-premium focus-visible:outline-none focus-visible:ring-2 " +
    "focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-base-950 " +
    "disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-4 [&_svg]:shrink-0 active:scale-[0.985]",
  {
    variants: {
      variant: {
        primary:
          "bg-accent text-accent-fg font-semibold shadow-glow-sm hover:bg-accent-soft hover:shadow-glow",
        secondary:
          "border border-silver-50/[0.09] bg-base-800/70 text-silver-100 backdrop-blur hover:border-silver-50/20 hover:bg-base-700/70",
        ghost: "text-silver-300 hover:bg-base-800/70 hover:text-silver-50",
        outline:
          "border border-accent/35 bg-accent/[0.06] text-accent-soft hover:border-accent/60 hover:bg-accent/12",
        danger:
          "border border-risk-critical/35 bg-risk-critical/10 text-risk-critical hover:border-risk-critical/60 hover:bg-risk-critical/20",
        link: "text-accent-soft underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4",
        lg: "h-12 px-6 text-base",
        icon: "size-10",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <>
            <Spinner className="size-4" />
            {children}
          </>
        ) : (
          children
        )}
      </Comp>
    );
  },
);
Button.displayName = "Button";

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn("animate-spin", className)}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path
        d="M22 12a10 10 0 0 0-10-10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

/* ── Card ───────────────────────────────────────────────────────────────── */

export const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { hover?: boolean; flush?: boolean }
>(({ className, hover = false, flush = false, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("glass", hover && "glass-hover", !flush && "p-5", className)}
    {...props}
  />
));
Card.displayName = "Card";

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mb-4 flex items-start justify-between gap-4", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn("text-sm font-semibold tracking-tight text-silver-100", className)}
      {...props}
    />
  );
}

export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("mt-1 text-xs leading-relaxed text-silver-400", className)} {...props} />;
}

/* ── Badge ──────────────────────────────────────────────────────────────── */

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-2xs font-semibold uppercase tracking-wider transition-colors",
  {
    variants: {
      variant: {
        neutral: "border-silver-50/12 bg-base-700/50 text-silver-300",
        accent: "border-accent/30 bg-accent/12 text-accent-soft",
        low: "border-risk-low/30 bg-risk-low/12 text-risk-low",
        medium: "border-risk-medium/30 bg-risk-medium/12 text-risk-medium",
        high: "border-risk-high/30 bg-risk-high/12 text-risk-high",
        critical: "border-risk-critical/30 bg-risk-critical/12 text-risk-critical",
        org: "border-org/30 bg-org/12 text-org",
        counterparty: "border-counterparty/30 bg-counterparty/12 text-counterparty",
      },
      size: {
        sm: "px-2 py-0 text-[0.625rem]",
        md: "px-2.5 py-0.5",
      },
    },
    defaultVariants: { variant: "neutral", size: "md" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, size, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, size }), className)} {...props} />;
}

/** Risk badge: maps a level to its variant so callers never pick colours. */
export function RiskBadge({
  level,
  score,
  className,
  size,
}: {
  level: string | undefined;
  score?: number;
  className?: string;
  size?: "sm" | "md";
}) {
  const variant = (level?.toLowerCase() ?? "low") as "low" | "medium" | "high" | "critical";
  return (
    <Badge variant={variant} size={size} className={className}>
      <span className="size-1.5 rounded-full bg-current" />
      {level ?? "Unknown"}
      {score !== undefined && <span className="numeric ml-0.5 opacity-80">{Math.round(score)}</span>}
    </Badge>
  );
}

/* ── Inputs ─────────────────────────────────────────────────────────────── */

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-md border border-silver-50/[0.09] bg-base-900/70 px-3 py-2 text-sm",
        "text-silver-100 placeholder:text-silver-500 transition-colors",
        "focus-visible:border-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "flex min-h-24 w-full rounded-md border border-silver-50/[0.09] bg-base-900/70 px-3 py-2 text-sm",
      "text-silver-100 placeholder:text-silver-500 transition-colors resize-y",
      "focus-visible:border-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "h-10 w-full appearance-none rounded-md border border-silver-50/[0.09] bg-base-900/70 px-3 pr-9 text-sm",
      "text-silver-100 transition-colors focus-visible:border-accent/50 focus-visible:outline-none",
      "focus-visible:ring-2 focus-visible:ring-accent/25",
      "bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 fill=%22none%22 viewBox=%220 0 24 24%22 stroke=%22%2394a3b8%22 stroke-width=%222%22%3E%3Cpath d=%22m6 9 6 6 6-6%22/%3E%3C/svg%3E')] bg-[length:1rem] bg-[right_0.65rem_center] bg-no-repeat",
      className,
    )}
    {...props}
  />
));
Select.displayName = "Select";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("mb-1.5 block text-xs font-medium text-silver-300", className)}
      {...props}
    />
  );
}

/* ── Progress ───────────────────────────────────────────────────────────── */

export function Progress({
  value,
  className,
  indicatorClassName,
}: {
  value: number;
  className?: string;
  indicatorClassName?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-base-700/70", className)}
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn(
          "h-full rounded-full bg-accent transition-[width] duration-500 ease-premium",
          indicatorClassName,
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

/* ── Skeletons ──────────────────────────────────────────────────────────── */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton h-4 w-full", className)} />;
}

export function SkeletonCard({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <Card className={className}>
      <Skeleton className="mb-4 h-3 w-24" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn("mb-2.5 h-3", i === lines - 1 ? "w-2/5" : i % 2 ? "w-4/5" : "w-full")}
        />
      ))}
    </Card>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={cn("h-9", c === 0 ? "flex-[2]" : "flex-1")} />
          ))}
        </div>
      ))}
    </div>
  );
}

/* ── Empty state ────────────────────────────────────────────────────────── */

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border border-dashed border-silver-50/10 px-6 py-14 text-center",
        className,
      )}
    >
      {icon && (
        <div className="mb-4 grid size-12 place-items-center rounded-xl border border-silver-50/[0.08] bg-base-800/60 text-silver-400">
          {icon}
        </div>
      )}
      <p className="text-sm font-semibold text-silver-200">{title}</p>
      {description && (
        <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-silver-400">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/* ── Alert ──────────────────────────────────────────────────────────────── */

export function Alert({
  variant = "info",
  title,
  children,
  className,
  icon,
}: {
  variant?: "info" | "warning" | "danger" | "success";
  title?: string;
  children?: React.ReactNode;
  className?: string;
  icon?: React.ReactNode;
}) {
  const variants = {
    info: "border-[hsl(200_85%_58%)]/25 bg-[hsl(200_85%_58%)]/[0.07] text-[hsl(200_85%_78%)]",
    warning: "border-risk-medium/25 bg-risk-medium/[0.07] text-risk-medium",
    danger: "border-risk-critical/25 bg-risk-critical/[0.07] text-risk-critical",
    success: "border-risk-low/25 bg-risk-low/[0.07] text-risk-low",
  };
  return (
    <div className={cn("rounded-lg border px-4 py-3 text-xs", variants[variant], className)}>
      <div className="flex gap-2.5">
        {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
        <div className="min-w-0 flex-1">
          {title && <p className="mb-1 font-semibold">{title}</p>}
          <div className="leading-relaxed opacity-90">{children}</div>
        </div>
      </div>
    </div>
  );
}

/* ── Tooltip (lightweight, CSS-only) ────────────────────────────────────── */

export function Tooltip({
  content,
  children,
  side = "top",
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom";
}) {
  return (
    <span className="group/tip relative inline-flex">
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute left-1/2 z-50 w-max max-w-xs -translate-x-1/2 scale-95 rounded-md",
          "border border-silver-50/10 bg-base-850/95 px-2.5 py-1.5 text-2xs font-normal normal-case tracking-normal",
          "text-silver-200 opacity-0 shadow-glass-lg backdrop-blur transition-all duration-150",
          "group-hover/tip:scale-100 group-hover/tip:opacity-100",
          side === "top" ? "bottom-full mb-2" : "top-full mt-2",
        )}
      >
        {content}
      </span>
    </span>
  );
}

/* ── Section heading ────────────────────────────────────────────────────── */

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-6 flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
        <h2 className="text-2xl font-semibold tracking-tight text-silver-50">{title}</h2>
        {description && (
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-silver-400">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}
