import { ArrowLeft, FileQuestion, LayoutDashboard, Search } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { AmbientBackground } from "@/components/ambient-background";
import { Reveal } from "@/components/ui/motion";
import { Button, Card } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <div className="relative flex min-h-dvh items-center justify-center px-4 py-16">
      <AmbientBackground variant="mesh" intensity={0.6} />

      <Reveal className="w-full max-w-lg">
        <Card className="p-8 text-center sm:p-12">
          <div className="mx-auto mb-6 grid size-14 place-items-center rounded-2xl border border-silver-50/[0.08] bg-base-800/60 text-silver-400">
            <FileQuestion className="size-6" />
          </div>

          <p className="numeric text-5xl font-semibold text-accent/70">404</p>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-silver-50">
            This clause isn&apos;t in the contract
          </h1>
          <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-silver-400">
            The page you asked for doesn&apos;t exist. It may have been moved, or the contract or
            clause id may no longer be valid.
          </p>

          <div className="mt-8 flex flex-wrap justify-center gap-2.5">
            <Button variant="primary" asChild>
              <Link href="/dashboard">
                <LayoutDashboard className="size-4" /> Dashboard
              </Link>
            </Button>
            <Button variant="secondary" asChild>
              <Link href="/contracts">
                <ArrowLeft className="size-4" /> Contracts
              </Link>
            </Button>
            <Button variant="ghost" asChild>
              <Link href="/search">
                <Search className="size-4" /> Search
              </Link>
            </Button>
          </div>
        </Card>
      </Reveal>
    </div>
  );
}
