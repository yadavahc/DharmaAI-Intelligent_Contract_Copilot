import type { Metadata } from "next";

import { UploadView } from "@/components/upload-view";

export const metadata: Metadata = { title: "Upload contract" };

export default function UploadPage() {
  return <UploadView />;
}
