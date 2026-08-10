"use client";

import { useParams } from "next/navigation";

import { LiveRunCard } from "@/components/home/LiveRunCard";
import { RunSubNav } from "@/components/run/RunSubNav";

// Direct-URL live workspace — reuses LiveRunCard full-width rather than a
// second implementation, since the backend's `snapshot` frame already fully
// describes a completed run too (same reasoning Home's LiveRunCard usage
// documents). A refresh here just remounts useResearchSocket against the
// same runId and resyncs from that snapshot.
export default function ResearchWorkspacePage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";

  return (
    <main className="mx-auto max-w-3xl px-10 py-10">
      <RunSubNav runId={runId} className="mb-6" />
      <LiveRunCard runId={runId} />
    </main>
  );
}
