import { z } from "zod";

// Mirrors backend/app/observability/events.py exactly (frame envelope +
// per-type `data` shapes) and the extra fields ws.py's snapshot builder adds
// on top of the plain progress/stat frames. Every inbound WS message is
// parsed against this before it touches app state — a malformed frame is
// logged and dropped, never allowed to throw (PRD §15.3).

const FrameEnvelope = {
  run_id: z.string(),
  ts: z.string(),
};

export const SourceSchema = z.object({
  source_id: z.string(),
  title: z.string().nullable(),
  domain: z.string().nullable(),
  source_type: z.string().nullable(),
  credibility_score: z.number().nullable(),
});
export type SourceFrameData = z.infer<typeof SourceSchema>;

export const ContradictionSchema = z.object({
  topic: z.string().nullable(),
  evidence_a_id: z.string(),
  evidence_b_id: z.string(),
});
export type ContradictionFrameData = z.infer<typeof ContradictionSchema>;

export const NodeTraceSummarySchema = z.object({
  node: z.string(),
  seq: z.number(),
  status: z.string().nullable(),
  latency_ms: z.number().nullable(),
  cost_usd: z.number().nullable(),
});

export const StatSchema = z.object({
  sources: z.number(),
  evidence_items: z.number(),
  claims_verified: z.number(),
  conflicts: z.number(),
  eta_seconds: z.number().nullable(),
});
export type StatFrameData = z.infer<typeof StatSchema>;

// Mirrors ResearchPlan (backend/app/models/schemas.py) exactly — this is
// `response.parsed.model_dump()`, sent verbatim both via plan_ready and as
// part of `snapshot` (ws.py reads the same run.plan column either way).
export const PlanSchema = z.object({
  title: z.string(),
  objective: z.string(),
  sub_questions: z.array(z.string()),
  required_sources: z.array(z.string()),
  estimated_depth: z.string(),
  primary_source_required_for: z.array(z.string()),
  expected_figures: z.array(z.string()),
});
export type PlanFrameData = z.infer<typeof PlanSchema>;

const SnapshotDataSchema = z.object({
  status: z.string(),
  mode: z.string(),
  query: z.string(),
  plan: PlanSchema.nullable(),
  stage: z.string().nullable(),
  stage_order: z.array(z.string()),
  stat: StatSchema.nullable(),
  sources: z.array(SourceSchema),
  contradictions: z.array(ContradictionSchema),
  node_traces: z.array(NodeTraceSummarySchema),
  report_markdown: z.string(),
});

const NodeStartedDataSchema = z.object({ node: z.string() });
const NodeFinishedDataSchema = z.object({
  node: z.string(),
  latency_ms: z.number(),
  cost_usd: z.number(),
});
const ProgressDataSchema = z.object({
  stage: z.string(),
  label: z.string(),
  current: z.number(),
  total: z.number(),
});
const ReportChunkDataSchema = z.object({ delta: z.string() });
const DoneDataSchema = z.object({ report_url: z.string() });
const ErrorDataSchema = z.object({ message: z.string(), recoverable: z.boolean() });

export const ServerFrameSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("snapshot"), ...FrameEnvelope, data: SnapshotDataSchema }),
  z.object({ type: z.literal("node_started"), ...FrameEnvelope, data: NodeStartedDataSchema }),
  z.object({ type: z.literal("node_finished"), ...FrameEnvelope, data: NodeFinishedDataSchema }),
  z.object({ type: z.literal("progress"), ...FrameEnvelope, data: ProgressDataSchema }),
  z.object({ type: z.literal("stat"), ...FrameEnvelope, data: StatSchema }),
  z.object({ type: z.literal("source_found"), ...FrameEnvelope, data: SourceSchema }),
  z.object({ type: z.literal("contradiction_found"), ...FrameEnvelope, data: ContradictionSchema }),
  z.object({ type: z.literal("plan_ready"), ...FrameEnvelope, data: PlanSchema }),
  z.object({ type: z.literal("report_chunk"), ...FrameEnvelope, data: ReportChunkDataSchema }),
  z.object({ type: z.literal("done"), ...FrameEnvelope, data: DoneDataSchema }),
  z.object({ type: z.literal("error"), ...FrameEnvelope, data: ErrorDataSchema }),
]);

export type ServerFrame = z.infer<typeof ServerFrameSchema>;
