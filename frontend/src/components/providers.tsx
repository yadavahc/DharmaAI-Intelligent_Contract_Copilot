"use client";

import { SessionProvider } from "next-auth/react";
import * as React from "react";
import { Toaster } from "sonner";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider
      // The review/negotiation pages are long-lived; refetch the session
      // periodically so a role change or expiry is picked up without a reload.
      refetchInterval={5 * 60}
      refetchOnWindowFocus
    >
      {children}
      <Toaster
        position="bottom-right"
        theme="dark"
        closeButton
        richColors
        toastOptions={{
          // Match the glass surface used everywhere else rather than sonner's default.
          classNames: {
            toast:
              "!bg-base-850/95 !border-silver-50/10 !text-silver-100 !backdrop-blur-xl !shadow-glass-lg !rounded-lg",
            title: "!text-sm !font-semibold",
            description: "!text-xs !text-silver-400",
            actionButton: "!bg-accent !text-accent-fg !text-xs !font-semibold",
            cancelButton: "!bg-base-700 !text-silver-300 !text-xs",
          },
        }}
      />
    </SessionProvider>
  );
}
