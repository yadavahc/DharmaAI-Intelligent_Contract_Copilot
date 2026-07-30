import type { Metadata } from "next";

import { GuardrailDemoView } from "@/components/guardrail-demo-view";

export const metadata: Metadata = { title: "Guardrail demo" };

export default function GuardrailsPage() {
  return <GuardrailDemoView />;
}
