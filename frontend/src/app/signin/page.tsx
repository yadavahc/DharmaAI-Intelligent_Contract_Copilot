import type { Metadata } from "next";
import { Suspense } from "react";

import { SignInForm } from "@/components/signin-form";
import { Spinner } from "@/components/ui/primitives";
import { DEMO_CREDENTIALS } from "@/lib/auth";

export const metadata: Metadata = { title: "Sign in" };

export default function SignInPage() {
  return (
    // `SignInForm` reads `useSearchParams()` for the callbackUrl and error, which
    // opts it out of static prerendering. The Suspense boundary lets the rest of
    // the page prerender and the form stream in, instead of failing the build.
    <Suspense
      fallback={
        <div className="flex min-h-dvh items-center justify-center">
          <Spinner className="size-5 text-accent" />
        </div>
      }
    >
      {/* Passed from the server so the demo logins stay in sync with what
          auth.ts actually seeds. */}
      <SignInForm demoAccounts={DEMO_CREDENTIALS} />
    </Suspense>
  );
}
