"use client";

import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { GuardrailVerdictCard } from "@/components/guardrail-verdict";
import { PageTransition, Reveal } from "@/components/ui/motion";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardTitle,
  Input,
  Label,
  Progress,
  SectionHeading,
} from "@/components/ui/primitives";
import { ApiError, api } from "@/lib/api";
import type { GuardrailVerdict } from "@/lib/types";
import { cn } from "@/lib/utils";

const ACCEPTED = ".pdf,.docx,.txt,.md";
const MAX_MB = 25;

export function UploadView() {
  const router = useRouter();
  const inputRef = React.useRef<HTMLInputElement>(null);

  const [file, setFile] = React.useState<File | null>(null);
  const [title, setTitle] = React.useState("");
  const [counterparty, setCounterparty] = React.useState("");
  const [dragging, setDragging] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [result, setResult] = React.useState<{
    contract_id: string;
    title: string;
    clause_count: number;
    blocked: boolean;
    guardrails: { summary: string; verdicts: GuardrailVerdict[] };
  } | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const pickFile = (candidate: File | undefined | null) => {
    if (!candidate) return;
    const ext = `.${candidate.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!ACCEPTED.split(",").includes(ext)) {
      setError(`Unsupported file type '${ext}'. Accepted: ${ACCEPTED}`);
      return;
    }
    if (candidate.size > MAX_MB * 1024 * 1024) {
      setError(`File is ${(candidate.size / 1024 / 1024).toFixed(1)} MB — the limit is ${MAX_MB} MB.`);
      return;
    }
    setError(null);
    setResult(null);
    setFile(candidate);
    if (!title) setTitle(candidate.name.replace(/\.[^.]+$/, ""));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) return;

    setUploading(true);
    setError(null);
    setProgress(12);

    // Indeterminate-but-honest progress: extraction, guardrail screening,
    // splitting and embedding all happen server-side in one request, so this
    // approximates rather than tracks. It stops short of 100 until the response
    // lands, so it never claims completion that hasn't happened.
    const ticker = setInterval(() => {
      setProgress((p) => (p < 88 ? p + Math.random() * 9 : p));
    }, 320);

    try {
      const form = new FormData();
      form.append("file", file);
      if (title) form.append("title", title);
      if (counterparty) form.append("counterparty", counterparty);

      const response = await api.uploadContract(form);
      clearInterval(ticker);
      setProgress(100);
      setResult(response);

      if (response.blocked) {
        toast.error("Ingest blocked by a guardrail", {
          description: "Critical PII was detected. The document was stored but not reviewed.",
        });
      } else {
        toast.success(`${response.clause_count} clauses extracted`, {
          description: "Open the contract to run the agent review.",
        });
      }
    } catch (err) {
      clearInterval(ticker);
      setProgress(0);
      const message = err instanceof ApiError ? err.message : String(err);
      setError(message);
      toast.error("Upload failed", { description: message });
    } finally {
      setUploading(false);
    }
  };

  const loadSample = async () => {
    setUploading(true);
    setError(null);
    try {
      const response = await api.loadSampleContract();
      toast.success("Sample contract loaded");
      router.push(`/contracts/${response.contract_id}`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : String(err);
      setError(message);
      toast.error("Could not load the sample", { description: message });
    } finally {
      setUploading(false);
    }
  };

  return (
    <PageTransition className="mx-auto max-w-3xl">
      <SectionHeading
        eyebrow="Step 1"
        title="Upload a contract"
        description="PDF, DOCX or plain text. Text is extracted, screened by the input guardrails, split into clauses on the document's own numbering, and embedded into Qdrant."
      />

      <form onSubmit={submit} className="space-y-5">
        {/* ── dropzone ── */}
        <Card
          flush
          className={cn(
            "relative overflow-hidden transition-colors duration-200",
            dragging && "border-accent/50 bg-accent/[0.04]",
          )}
        >
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              pickFile(e.dataTransfer.files?.[0]);
            }}
            className="flex flex-col items-center justify-center px-6 py-12 text-center"
          >
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPTED}
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0])}
              data-testid="file-input"
            />

            {file ? (
              <>
                <span className="mb-4 grid size-12 place-items-center rounded-xl border border-accent/25 bg-accent/[0.08] text-accent">
                  <FileText className="size-5" />
                </span>
                <p className="text-sm font-medium text-silver-100">{file.name}</p>
                <p className="mt-1 text-2xs text-silver-500">
                  {(file.size / 1024).toFixed(0)} KB
                </p>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="mt-4"
                  onClick={() => {
                    setFile(null);
                    setResult(null);
                    if (inputRef.current) inputRef.current.value = "";
                  }}
                >
                  <X className="size-3.5" /> Choose a different file
                </Button>
              </>
            ) : (
              <>
                <span className="mb-4 grid size-12 place-items-center rounded-xl border border-silver-50/[0.08] bg-base-800/60 text-silver-400">
                  <UploadCloud className="size-5" />
                </span>
                <p className="text-sm font-medium text-silver-200">
                  Drop a contract here, or{" "}
                  <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    className="text-accent-soft underline underline-offset-4 hover:text-accent"
                  >
                    browse
                  </button>
                </p>
                <p className="mt-1.5 text-2xs text-silver-500">
                  PDF · DOCX · TXT · up to {MAX_MB} MB
                </p>
                <p className="mt-4 max-w-sm text-2xs leading-relaxed text-silver-600">
                  Scanned documents need OCR first — Dharma AI reads embedded text, it does not
                  perform OCR.
                </p>
              </>
            )}
          </div>
        </Card>

        {/* ── metadata ── */}
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="title">Contract title</Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Acme ⇄ Vendor — Master Services Agreement"
            />
          </div>
          <div>
            <Label htmlFor="counterparty">Counterparty (optional)</Label>
            <Input
              id="counterparty"
              value={counterparty}
              onChange={(e) => setCounterparty(e.target.value)}
              placeholder="Vendor Industries Ltd"
            />
          </div>
        </div>

        {error && (
          <Alert variant="danger" icon={<AlertTriangle className="size-3.5" />}>
            {error}
          </Alert>
        )}

        {uploading && (
          <div>
            <div className="mb-2 flex items-center justify-between text-2xs text-silver-400">
              <span>Extracting, screening and embedding…</span>
              <span className="numeric">{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} />
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          <Button type="submit" variant="primary" disabled={!file} loading={uploading}>
            <UploadCloud className="size-4" /> Upload and extract
          </Button>
          <Button type="button" variant="secondary" onClick={loadSample} disabled={uploading}>
            <Sparkles className="size-4" /> Use the sample contract
          </Button>
        </div>
      </form>

      {/* ── result ── */}
      {result && (
        <Reveal className="mt-8 space-y-4">
          <Card
            className={cn(
              result.blocked ? "border-risk-critical/30" : "border-risk-low/30",
            )}
          >
            <div className="flex items-start gap-3">
              {result.blocked ? (
                <ShieldAlert className="mt-0.5 size-5 shrink-0 text-risk-critical" />
              ) : (
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-risk-low" />
              )}
              <div className="min-w-0 flex-1">
                <CardTitle>
                  {result.blocked ? "Ingest blocked by guardrail" : "Extraction complete"}
                </CardTitle>
                <p className="mt-1.5 text-xs leading-relaxed text-silver-400">
                  <strong className="text-silver-200">{result.title}</strong> —{" "}
                  {result.clause_count} clauses identified.{" "}
                  {result.blocked
                    ? "Critical personal data was found, so the agents did not review it. Remediate the document and re-upload."
                    : "Ready for the agent review pipeline."}
                </p>
                {!result.blocked && (
                  <Button
                    variant="primary"
                    size="sm"
                    className="mt-4"
                    onClick={() => router.push(`/contracts/${result.contract_id}`)}
                  >
                    Open and review <ShieldCheck className="size-3.5" />
                  </Button>
                )}
              </div>
            </div>
          </Card>

          {/* Guardrail verdicts always shown — a clean scan is information too. */}
          <div>
            <p className="eyebrow mb-3">Input guardrail screening</p>
            <div className="space-y-3">
              {result.guardrails.verdicts.map((verdict) => (
                <GuardrailVerdictCard key={verdict.guardrail} verdict={verdict} compact />
              ))}
            </div>
          </div>
        </Reveal>
      )}
    </PageTransition>
  );
}
