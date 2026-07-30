"use client";

import { diffWords } from "diff";
import { ArrowRight, Columns2, Rows2 } from "lucide-react";
import * as React from "react";

import { Badge, Button } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/**
 * Word-level diff for redlines: original → suggested → reason.
 *
 * Word-level rather than character-level, because character diffs on legal prose
 * produce unreadable confetti. Two view modes: inline (the classic redline a
 * lawyer expects) and side-by-side (easier when the rewrite is substantial).
 */
export function DiffView({
  original,
  suggested,
  reason,
  changeSummary,
  className,
  defaultMode = "inline",
}: {
  original: string;
  suggested: string;
  reason?: string;
  changeSummary?: string;
  className?: string;
  defaultMode?: "inline" | "split";
}) {
  const [mode, setMode] = React.useState<"inline" | "split">(defaultMode);

  const parts = React.useMemo(
    () => diffWords(original ?? "", suggested ?? ""),
    [original, suggested],
  );

  const stats = React.useMemo(() => {
    let added = 0;
    let removed = 0;
    for (const part of parts) {
      const words = part.value.trim().split(/\s+/).filter(Boolean).length;
      if (part.added) added += words;
      else if (part.removed) removed += words;
    }
    return { added, removed };
  }, [parts]);

  const unchanged = stats.added === 0 && stats.removed === 0;

  return (
    <div className={cn("space-y-3", className)} data-testid="diff-view">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="eyebrow">Proposed redline</p>
          {unchanged ? (
            <Badge variant="neutral" size="sm">
              no change proposed
            </Badge>
          ) : (
            <>
              <Badge variant="low" size="sm">
                +{stats.added} added
              </Badge>
              <Badge variant="critical" size="sm">
                −{stats.removed} removed
              </Badge>
            </>
          )}
        </div>
        <div className="flex gap-1">
          <Button
            variant={mode === "inline" ? "outline" : "ghost"}
            size="icon-sm"
            onClick={() => setMode("inline")}
            aria-label="Inline diff"
            aria-pressed={mode === "inline"}
          >
            <Rows2 />
          </Button>
          <Button
            variant={mode === "split" ? "outline" : "ghost"}
            size="icon-sm"
            onClick={() => setMode("split")}
            aria-label="Side-by-side diff"
            aria-pressed={mode === "split"}
          >
            <Columns2 />
          </Button>
        </div>
      </div>

      {mode === "inline" ? (
        <div className="rounded-lg border border-silver-50/[0.07] bg-base-900/50 p-4">
          <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-silver-300">
            {parts.map((part, i) => (
              <span
                key={i}
                className={cn(
                  part.added && "diff-ins",
                  part.removed && "diff-del",
                )}
              >
                {part.value}
              </span>
            ))}
          </p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-risk-critical/20 bg-risk-critical/[0.03] p-4">
            <p className="mb-2 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-risk-critical">
              Original
            </p>
            <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-silver-400">
              {original || "—"}
            </p>
          </div>
          <div className="rounded-lg border border-risk-low/20 bg-risk-low/[0.03] p-4">
            <p className="mb-2 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-risk-low">
              Suggested
            </p>
            <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-silver-300">
              {suggested || "—"}
            </p>
          </div>
        </div>
      )}

      {(reason || changeSummary) && (
        <div className="rounded-lg border border-accent/20 bg-accent/[0.04] p-3.5">
          <p className="mb-1.5 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-accent-soft">
            <ArrowRight className="size-3" />
            Why this change
          </p>
          {reason && <p className="text-xs leading-relaxed text-silver-300">{reason}</p>}
          {changeSummary && (
            <p className="mt-1.5 text-2xs italic leading-relaxed text-silver-500">
              {changeSummary}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Compact version-to-version diff used by the version history timeline. */
export function VersionDiff({
  fromText,
  toText,
  className,
}: {
  fromText: string;
  toText: string;
  className?: string;
}) {
  const parts = React.useMemo(() => diffWords(fromText ?? "", toText ?? ""), [fromText, toText]);

  return (
    <p
      className={cn(
        "whitespace-pre-wrap rounded-md border border-silver-50/[0.06] bg-base-900/50 p-3 font-mono text-2xs leading-relaxed text-silver-400",
        className,
      )}
    >
      {parts.map((part, i) => (
        <span key={i} className={cn(part.added && "diff-ins", part.removed && "diff-del")}>
          {part.value}
        </span>
      ))}
    </p>
  );
}
