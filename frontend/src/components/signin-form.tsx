"use client";

import { AlertCircle, ArrowRight, ShieldCheck, Sparkles, User } from "lucide-react";
import { signIn } from "next-auth/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { AmbientBackground } from "@/components/ambient-background";
import { Reveal } from "@/components/ui/motion";
import { Alert, Badge, Button, Card, Input, Label } from "@/components/ui/primitives";
import { ROLE_LABELS, cn } from "@/lib/utils";

interface DemoAccount {
  email: string;
  password: string;
  name: string;
  role: string;
}

const ROLE_CAPABILITIES: Record<string, string> = {
  ADMIN: "Full access — manage the playbook, delete contracts, approve redlines.",
  REVIEWER: "Review escalated clauses and approve, edit or reject redlines.",
  BUSINESS_USER: "Upload contracts and read reviews. Cannot approve redlines.",
};

export function SignInForm({ demoAccounts }: { demoAccounts: DemoAccount[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") || "/dashboard";
  const urlError = searchParams.get("error");

  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(
    urlError ? "Those credentials were not accepted. Try a demo account below." : null,
  );

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
      callbackUrl,
    });

    if (result?.error) {
      // The most common cause on a fresh clone is Postgres not being up, so say
      // that rather than only "invalid credentials".
      setError(
        "Sign-in failed. Check the email and password — or, if this is a fresh " +
          "setup, confirm Postgres is running and `npx prisma db push` has been run.",
      );
      setLoading(false);
      return;
    }

    toast.success("Signed in");
    router.push(result?.url ?? callbackUrl);
    router.refresh();
  };

  const signInAs = async (account: DemoAccount) => {
    setEmail(account.email);
    setPassword(account.password);
    setLoading(true);
    setError(null);

    const result = await signIn("credentials", {
      email: account.email,
      password: account.password,
      redirect: false,
      callbackUrl,
    });

    if (result?.error) {
      setError(
        "Demo sign-in failed. Is Postgres running and the Prisma schema pushed? " +
          "Run `npx prisma db push` in ./frontend.",
      );
      setLoading(false);
      return;
    }
    toast.success(`Signed in as ${ROLE_LABELS[account.role] ?? account.role}`);
    router.push(result?.url ?? callbackUrl);
    router.refresh();
  };

  return (
    <div className="relative flex min-h-dvh items-center justify-center px-4 py-12">
      <AmbientBackground variant="mesh" intensity={0.8} />

      <Reveal className="w-full max-w-4xl">
        <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
          {/* ── sign in ── */}
          <Card className="p-7">
            <Link href="/" className="mb-7 inline-flex items-center gap-2.5">
              <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-accent to-accent/50 shadow-glow-sm">
                <Sparkles className="size-4 text-accent-fg" strokeWidth={2.5} />
              </span>
              <span className="text-base font-semibold tracking-tight text-silver-50">
                Dharma<span className="text-accent"> AI</span>
              </span>
            </Link>

            <h1 className="text-xl font-semibold tracking-tight text-silver-50">Sign in</h1>
            <p className="mt-1.5 text-xs text-silver-400">
              Your role determines what you can approve.
            </p>

            {error && (
              <Alert variant="danger" className="mt-5" icon={<AlertCircle className="size-3.5" />}>
                {error}
              </Alert>
            )}

            <form onSubmit={submit} className="mt-6 space-y-4">
              <div>
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                />
              </div>
              <div>
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                />
              </div>
              <Button type="submit" variant="primary" className="w-full" loading={loading}>
                {loading ? "Signing in…" : "Sign in"}
                {!loading && <ArrowRight className="size-3.5" />}
              </Button>
            </form>
          </Card>

          {/* ── demo accounts ── */}
          <Card className="p-7">
            <div className="mb-5 flex items-center gap-2">
              <ShieldCheck className="size-4 text-accent" />
              <h2 className="text-sm font-semibold text-silver-100">Demo accounts</h2>
            </div>
            <p className="mb-5 text-xs leading-relaxed text-silver-400">
              One click to sign in. Each role sees a different app — and the backend enforces the
              difference, so a Business User genuinely cannot approve a redline.
            </p>

            <ul className="space-y-2.5">
              {demoAccounts.map((account) => (
                <li key={account.email}>
                  <button
                    type="button"
                    onClick={() => signInAs(account)}
                    disabled={loading}
                    className={cn(
                      "group w-full rounded-lg border border-silver-50/[0.07] bg-base-900/50 p-3.5 text-left",
                      "transition-all duration-200 ease-premium hover:border-accent/35 hover:bg-accent/[0.05]",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
                      "disabled:pointer-events-none disabled:opacity-50",
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent/12 text-accent-soft">
                          <User className="size-3.5" />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-xs font-semibold text-silver-100">
                            {account.name}
                          </p>
                          <p className="truncate font-mono text-2xs text-silver-500">
                            {account.email}
                          </p>
                        </div>
                      </div>
                      <Badge variant={account.role === "ADMIN" ? "accent" : "neutral"} size="sm">
                        {ROLE_LABELS[account.role] ?? account.role}
                      </Badge>
                    </div>
                    <p className="mt-2.5 text-2xs leading-relaxed text-silver-500">
                      {ROLE_CAPABILITIES[account.role]}
                    </p>
                    <p className="mt-1.5 font-mono text-[0.625rem] text-silver-600">
                      password: {account.password}
                    </p>
                  </button>
                </li>
              ))}
            </ul>

            <p className="mt-5 text-2xs leading-relaxed text-silver-600">
              Demo accounts are seeded on first sign-in. Credentials come from the environment
              (see <code className="font-mono">.env.example</code>) — change them for anything
              beyond a local demo.
            </p>
          </Card>
        </div>
      </Reveal>
    </div>
  );
}
