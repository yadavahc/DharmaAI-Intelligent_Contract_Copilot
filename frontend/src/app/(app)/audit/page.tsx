import type { Metadata } from "next";

import { AuditLogView } from "@/components/audit-log-view";

export const metadata: Metadata = { title: "Audit log" };

export default function AuditPage() {
  return <AuditLogView />;
}
