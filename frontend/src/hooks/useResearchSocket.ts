"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import {
  ServerFrameSchema,
  type ContradictionFrameData,
  type ServerFrame,
  type SourceFrameData,
  type StatFrameData,
} from "@/lib/ws-schema";
import type { Citation } from "@/types/api";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
const PING_INTERVAL_MS = 20_000;
const BACKOFF_MIN_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

// A single chronological log entry for the live activity feed — real events
// only (node transitions, source discoveries), never the rotating witty
// copy, which stays purely client-side and is never mixed into this array.
export interface ActivityEvent {
  id: string;
  kind: "node_started" | "node_finished" | "source_found";
  node: string | null;
  source: SourceFrameData | null;
  ts: number;
}

const ACTIVITY_HISTORY_LIMIT = 60;

export interface ResearchSocketState {
  status: string | null;
  mode: string | null;
  query: string | null;
  plan: unknown;
  stage: string | null;
  stageOrder: string[];
  stat: StatFrameData | null;
  sources: SourceFrameData[];
  contradictions: ContradictionFrameData[];
  reportMarkdown: string;
  citations: Citation[];
  connected: boolean;
  terminalError: { message: string; recoverable: boolean } | null;
  // Name of the node currently in flight (has a node_started with no
  // matching node_finished yet), or null between runs / once complete.
  currentNode: string | null;
  activity: ActivityEvent[];
}

function createInitialState(): ResearchSocketState {
  return {
    status: null,
    mode: null,
    query: null,
    plan: null,
    stage: null,
    stageOrder: [],
    stat: null,
    sources: [],
    contradictions: [],
    reportMarkdown: "",
    citations: [],
    connected: false,
    terminalError: null,
    currentNode: null,
    activity: [],
  };
}

type Action =
  | { type: "connected" }
  | { type: "disconnected" }
  | { type: "reset" }
  | { type: "frame"; frame: ServerFrame }
  | { type: "report_ready"; markdown: string; citations: Citation[] };

function reduce(state: ResearchSocketState, action: Action): ResearchSocketState {
  switch (action.type) {
    case "connected":
      return { ...state, connected: true };
    case "disconnected":
      return { ...state, connected: false };
    case "reset":
      return createInitialState();
    case "report_ready":
      return { ...state, reportMarkdown: action.markdown, citations: action.citations };
    case "frame": {
      const { frame } = action;
      switch (frame.type) {
        case "snapshot": {
          // node_traces only exist for nodes that already finished (@traced
          // writes the row on completion, not on start), so this backfills
          // the feed's history on a mid-run reconnect/refresh but can't know
          // which node is *currently* in flight — that arrives naturally
          // with the next real node_started frame a moment later.
          const backfilled: ActivityEvent[] = [...frame.data.node_traces]
            .sort((a, b) => a.seq - b.seq)
            .map((t) => ({
              id: `snapshot-${t.node}-${t.seq}`,
              kind: "node_finished" as const,
              node: t.node,
              source: null,
              ts: 0,
            }));
          return {
            ...state,
            status: frame.data.status,
            mode: frame.data.mode,
            query: frame.data.query,
            plan: frame.data.plan,
            stage: frame.data.stage,
            stageOrder: frame.data.stage_order,
            stat: frame.data.stat,
            sources: frame.data.sources,
            contradictions: frame.data.contradictions,
            reportMarkdown: frame.data.report_markdown,
            activity: backfilled.slice(-ACTIVITY_HISTORY_LIMIT),
          };
        }
        case "progress":
          return { ...state, stage: frame.data.stage };
        case "stat":
          return { ...state, stat: frame.data };
        case "source_found":
          return {
            ...state,
            sources: [...state.sources, frame.data],
            activity: [
              ...state.activity,
              { id: `source-${frame.data.source_id}`, kind: "source_found" as const, node: null, source: frame.data, ts: Date.now() },
            ].slice(-ACTIVITY_HISTORY_LIMIT),
          };
        case "contradiction_found":
          return { ...state, contradictions: [...state.contradictions, frame.data] };
        case "report_chunk":
          return { ...state, reportMarkdown: state.reportMarkdown + frame.data.delta };
        case "done":
          return { ...state, status: "completed", currentNode: null };
        case "error":
          return { ...state, status: "error", terminalError: frame.data, currentNode: null };
        case "node_started":
          return {
            ...state,
            currentNode: frame.data.node,
            activity: [
              ...state.activity,
              { id: `${frame.data.node}-start-${Date.now()}`, kind: "node_started" as const, node: frame.data.node, source: null, ts: Date.now() },
            ].slice(-ACTIVITY_HISTORY_LIMIT),
          };
        case "node_finished":
          return {
            ...state,
            currentNode: state.currentNode === frame.data.node ? null : state.currentNode,
            activity: [
              ...state.activity,
              { id: `${frame.data.node}-finish-${Date.now()}`, kind: "node_finished" as const, node: frame.data.node, source: null, ts: Date.now() },
            ].slice(-ACTIVITY_HISTORY_LIMIT),
          };
        default:
          return state;
      }
    }
    default:
      return state;
  }
}

/**
 * Owns the live-run WebSocket (PRD §7.3 / §15.3): connects with the access
 * token, applies `snapshot` wholesale, reduces subsequent frames, pings to
 * keep the connection alive, and reconnects with backoff. Every inbound
 * frame is Zod-validated — a malformed frame is logged and dropped, never
 * thrown, so a server-side change can't white-screen the workspace.
 *
 * On `done`, the accumulated `report_chunk` text is discarded in favor of a
 * fresh `GET /research/{id}/report` fetch: the backend strips model-authored
 * sections and appends programmatic ones after streaming ends, so the
 * accumulated text can genuinely differ from the canonical report.
 */
export function useResearchSocket(runId: string | null): ResearchSocketState {
  const { accessToken, refreshAccessToken } = useAuth();
  const [state, dispatch] = useReducer(reduce, undefined, createInitialState);

  const tokenRef = useRef(accessToken);
  useEffect(() => {
    tokenRef.current = accessToken;
  }, [accessToken]);

  const fetchCanonicalReport = useCallback(async (id: string) => {
    const token = tokenRef.current;
    if (!token) return;
    try {
      const report = await api.getReport(token, id);
      dispatch({ type: "report_ready", markdown: report.markdown, citations: report.citations });
    } catch (err) {
      console.error("[useResearchSocket] failed to fetch canonical report:", err);
    }
  }, []);

  useEffect(() => {
    if (!runId || !tokenRef.current) return;
    const id = runId; // narrow once to a stable `const` so it stays typed `string` inside the nested closures below

    let cancelled = false;
    const backoffState = { delayMs: BACKOFF_MIN_MS };
    let terminal = false;
    let pingTimer: ReturnType<typeof setInterval> | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let ws: WebSocket | null = null;

    dispatch({ type: "reset" });

    function teardownSocket() {
      if (pingTimer) {
        clearInterval(pingTimer);
        pingTimer = null;
      }
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        ws.close();
        ws = null;
      }
    }

    function scheduleReconnect(token: string) {
      if (cancelled) return;
      const delay = backoffState.delayMs;
      backoffState.delayMs = Math.min(backoffState.delayMs * 2, BACKOFF_MAX_MS);
      reconnectTimer = setTimeout(() => connectSocket(token), delay);
    }

    function connectSocket(token: string) {
      if (cancelled) return;
      teardownSocket();

      const socket = new WebSocket(`${WS_URL}/api/v1/ws/research/${id}?token=${encodeURIComponent(token)}`);
      ws = socket;

      socket.onopen = () => {
        backoffState.delayMs = BACKOFF_MIN_MS;
        dispatch({ type: "connected" });
        pingTimer = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
        }, PING_INTERVAL_MS);
      };

      socket.onmessage = (event) => {
        let parsed: unknown;
        try {
          parsed = JSON.parse(event.data as string);
        } catch {
          console.warn("[useResearchSocket] non-JSON frame dropped:", event.data);
          return;
        }

        const result = ServerFrameSchema.safeParse(parsed);
        if (!result.success) {
          console.warn("[useResearchSocket] malformed frame dropped:", result.error.issues, parsed);
          return;
        }

        const frame = result.data;
        console.info("[useResearchSocket] frame:", frame.type, frame.data);
        dispatch({ type: "frame", frame });

        if (frame.type === "done") {
          terminal = true;
          void fetchCanonicalReport(id);
        } else if (frame.type === "error") {
          terminal = true;
        }
      };

      socket.onclose = (event) => {
        dispatch({ type: "disconnected" });
        if (pingTimer) {
          clearInterval(pingTimer);
          pingTimer = null;
        }
        if (cancelled || terminal) return;
        if (event.code === 4403) return; // run belongs to another user -- not recoverable

        if (event.code === 4401) {
          // Access token expired mid-run (realistic on a deep run brushing
          // the 15-minute lifetime) -- one silent refresh before giving up.
          refreshAccessToken()
            .then((newToken) => {
              if (cancelled) return;
              tokenRef.current = newToken;
              scheduleReconnect(newToken);
            })
            .catch((err) => {
              console.error("[useResearchSocket] refresh after 4401 failed, abandoning:", err);
            });
          return;
        }

        scheduleReconnect(tokenRef.current ?? token);
      };
    }

    connectSocket(tokenRef.current);

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      teardownSocket();
    };
    // Intentionally keyed on runId only -- accessToken changes elsewhere
    // (e.g. useAuth's own boot-time refresh) must not tear down a live
    // connection; the 4401 path above is the one place this hook rotates
    // the token itself, via the tokenRef/refreshAccessToken it already holds.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, fetchCanonicalReport, refreshAccessToken]);

  return state;
}
