import {
  BookOpenCheck,
  Brain,
  Compass,
  FileSearch,
  Gauge,
  GitCompareArrows,
  Globe,
  Image as ImageIcon,
  LineChart,
  ListChecks,
  PenLine,
  ShieldCheck,
  Sparkles,
  Workflow,
  type LucideIcon,
} from "lucide-react";

interface NodeMessage {
  label: string;
  icon: LucideIcon;
}

// Maps the real graph node names streamed over node_started/node_finished
// (backend/app/graph/graph_builder.py's node list, verbatim) to the present-
// tense language and icon shown in the live activity feed. Every node that
// can actually run has an entry — a name that falls through to the default
// below is a real gap, not an intentional omission.
const NODE_MESSAGES: Record<string, NodeMessage> = {
  planner: { label: "Understanding your question", icon: Compass },
  web_researcher: { label: "Searching the web", icon: Globe },
  evidence_extractor: { label: "Extracting relevant information", icon: FileSearch },
  credibility_scorer: { label: "Weighing source credibility", icon: ShieldCheck },
  retriever: { label: "Ranking the most relevant evidence", icon: Gauge },
  fact_checker: { label: "Cross-checking sources", icon: BookOpenCheck },
  contradiction_detector: { label: "Comparing findings for conflicts", icon: GitCompareArrows },
  figure_planner: { label: "Deciding what deserves a chart", icon: LineChart },
  chart_generator: { label: "Building a chart from the data", icon: LineChart },
  diagram_generator: { label: "Drawing a diagram", icon: Workflow },
  illustration_planner: { label: "Considering an illustration", icon: ImageIcon },
  image_generator: { label: "Generating an illustration", icon: ImageIcon },
  web_image_fetcher: { label: "Finding a real photo to match", icon: Globe },
  synthesizer: { label: "Synthesizing the answer", icon: PenLine },
  citation_validator: { label: "Checking every citation", icon: ListChecks },
  force_finalize: { label: "Wrapping up the report", icon: ListChecks },
};

const DEFAULT_MESSAGE: NodeMessage = { label: "Thinking", icon: Brain };

export function messageForNode(node: string | null): NodeMessage {
  if (!node) return DEFAULT_MESSAGE;
  return NODE_MESSAGES[node] ?? { label: node.replace(/_/g, " "), icon: Sparkles };
}

// Purely decorative — rotates on a timer in the UI, never mixed into the
// real activity feed (see ActivityEvent in useResearchSocket.ts). Witty,
// AI/research-flavored, never claims to be status.
export const WITTY_MESSAGES: string[] = [
  "Teaching the AI to touch grass. It's still processing.",
  "Asking the internet nicely for answers…",
  "Cross-checking things so you don't have to.",
  "Finding sources that actually know what they're talking about.",
  "Doing the research. Pretending this was effortless.",
  "The AI is digging through the internet. Please don't disturb it.",
  "Connecting the dots. Some of them are surprisingly far apart.",
  "Reading so you don't have to.",
  "One moment. The robots are having a meeting.",
  "Turning dozens of tabs into one useful answer.",
  "Consulting the collective wisdom of the internet…",
  "Separating signal from internet noise.",
  "Almost there. The AI found another rabbit hole.",
];
