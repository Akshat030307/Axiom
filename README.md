# Research Agent

An autonomous research agent: give it a question, it plans sub-questions,
searches the web, extracts and fact-checks evidence, resolves contradictions,
generates charts from real numeric evidence, and synthesizes a cited report —
streamed live over a WebSocket and exportable as a PDF. Spec: `PRD.md`.
Project rules: `CLAUDE.md`.

## Architecture

```
┌─────────────────┐        ┌──────────────────────────────────────────┐
│  Next.js 16      │  REST  │  FastAPI                                  │
│  (React 19)      │◄──────►│   ├─ auth (JWT access + refresh)          │
│  :3000           │   WS   │   ├─ research CRUD + history              │
│                  │◄──────►│   ├─ reports, sources, evidence, trace    │
└─────────────────┘        │   ├─ figures, eval                        │
                            │   └─ WebSocket live-run stream            │
                            │        :8000                              │
                            └───────────────┬────────────────────────────┘
                                             │ BackgroundTasks (in-process,
                                             │ no Celery worker yet)
                                             ▼
                            ┌──────────────────────────────────────────┐
                            │  LangGraph pipeline (12 nodes, sequential) │
                            │  planner → web_researcher → ... →          │
                            │  citation_validator                        │
                            │  every node wrapped in @traced             │
                            └───────────────┬────────────────────────────┘
                                             │
                    ┌────────────────────────┼───────────────────────┐
                    ▼                        ▼                       ▼
           ┌────────────────┐      ┌──────────────────┐   ┌──────────────────┐
           │ PostgreSQL 16   │      │ OpenAI            │   │ Tavily search API │
           │ + pgvector      │      │ (reasoning + fast  │   │                   │
           │ (evidence, runs,│      │  tiers, embeddings)│   └──────────────────┘
           │  reports, ...)  │      └──────────────────┘
           └────────────────┘
```

- **Backend**: FastAPI + LangGraph 1.x, SQLAlchemy (async) over Postgres/pgvector, Redis present but unused (no Celery worker yet — runs execute as an in-process `BackgroundTask`).
- **Frontend**: Next.js 16 (App Router) + React 19 + Tailwind v4, TanStack Query for data fetching, a hand-rolled `useResearchSocket` hook for the live WebSocket stream.
- **LLM access**: a single `LLMProvider` behind a task→route table (`app/llm/router.py`) that resolves each named task to a model tier (`reasoning` / `fast`), a reasoning-effort level, and a `max_completion_tokens` cap — nodes never hardcode a model name.
- Every graph node is decorated with `@traced`, which opens/commits the node's DB writes, records a `node_traces` row (tokens, latency, cost, input/output snapshot), and enforces `MAX_RUN_COST_USD` before the node runs.

## Running it

```bash
docker compose up
```

Brings up Postgres (pgvector), Redis, the backend (`:8000`), and the frontend
(`:3000`). The backend runs `alembic upgrade head` on every start. Real API
keys (OpenAI, Tavily) live in `.env` at the repo root (gitignored); `.env.example`
documents every variable.

### Known dev-environment quirks

- **Backend hot-reload kills in-flight runs.** `uvicorn --reload` restarts the
  process on any file save; a run mid-execution has its state discarded
  (already-written `raw_findings`/`evidence` rows survive, but the run's
  `status` is stuck at `"running"` forever). Not a bug in the graph — avoid
  editing backend files while a run you care about is executing.
- **Frontend dev server (`next dev`) currently 404s on any route two or more
  path segments deep** — e.g. `/research/{id}/report`, `/sources`,
  `/evidence`, `/trace` — regardless of whether the segment is static or
  dynamic. Reproduced against a brand-new throwaway route in both Turbopack
  and webpack dev modes, surviving a full container recreate, so it's a
  Next.js 16.3.0 dev-server route-discovery issue, not application code.
  `next build && next start` resolves every route correctly. If a nested
  route 404s during development, that's this issue, not a regression.

## The graph pipeline

Defined in `backend/app/graph/graph_builder.py`. Twelve nodes, executed
sequentially per run (no `Send()`-based fan-out anywhere in this codebase —
even "parallel" work like fact-checking multiple claims or generating
multiple charts is a `for` loop inside one node). Every node lives in
`backend/app/graph/nodes/`.

| # | Node | What it does |
|---|------|---------------|
| 1 | `planner` | Reasoning-tier call that turns the query into a `ResearchPlan` — an objective plus 3–12 sub-questions (count depends on mode: quick/deep/academic/competitive). |
| 2 | `web_researcher` | For each sub-question, calls Tavily search, fetches/cleans page text, chunks it down to the relevant part, and persists a `Source` row per unique URL. Single sequential node bounded by `MAX_TOOL_CALLS_PER_NODE`; a failed fetch is logged to `errors` and the loop continues. |
| 3 | `evidence_extractor` | Batches the raw fetched content (3 sources at a time) through a fast-tier structured-output call that pulls out discrete claims — each with a supporting excerpt, confidence, and optional `numeric_value`/`numeric_unit`/`time_period` — and persists them as `Evidence` rows. |
| 4 | `credibility_scorer` | Embeds all evidence (`ensure_evidence_embeddings`, idempotent — this is the first node that needs embeddings, so it pays for them), counts how many *other* sources corroborate each source's claims via cosine similarity, and scores every `Source` from domain/type/date/corroboration signals. |
| 5 | `retriever` | Hybrid retrieval (vector + BM25/full-text, reciprocal-rank fusion) per sub-question over this run's whole evidence pool, then reranks with a fast-tier LLM call down to the top-K, deduplicated, into `retrieved_evidence` — the set every downstream node (and the synthesizer's citation markers) actually uses. |
| 6 | `fact_checker` | Clusters `retrieved_evidence` by embedding similarity, prioritizes clusters (numeric > low-credibility > topically-central), and independently verifies only the top `MAX_FACT_CHECKS_{QUICK,DEEP}` representatives via a fresh search + fast-tier verdict (`supported`/`unsupported`/`outdated`), propagating the verdict to every cluster member. Unreached clusters get an explicit `unverified` — never a silent gap. |
| 7 | `contradiction_detector` | Three-tier funnel: (1) free numeric-threshold check within same-unit clusters, (2) one fast-tier batched classification call per group to flag candidate pairs, (3) one reasoning-tier call per flagged pair to confirm/reject and explain. Confirmed pairs become `Contradiction` rows. |
| 8 | `figure_planner` | Reasoning-tier call that looks at `retrieved_evidence` and proposes 0+ chart requests (`FigureRequest`, `kind` hardcoded to `"chart"` — image/diagram generation is out of scope, see below). Every cited `evidence_id` is checked against the real evidence set before being trusted forward; capped by `MAX_FIGURES_PER_REPORT`. |
| 9 | `chart_generator` | One fast-tier call per accepted figure request, emitting a validated `ChartSpec` (chart type, series, categories, labels). Every plotted value is checked against the referenced evidence's real `numeric_value`s before acceptance — the model **never emits plotting code**; matplotlib renders the accepted spec to PNG, stored content-addressed under `FIGURES_DIR`, and persisted as a `Figure` row. |
| 10 | `synthesizer` | Reasoning-tier call, **streamed** token-by-token over the WebSocket (`report_chunk` frames). Writes the report body with `[n]` citation markers and at most one `figure://{id}` reference per generated figure. The Sources and Contradictions-Noted sections are never LLM-authored — built programmatically from the real `Source`/`Contradiction` rows and appended after. |
| 11 | `citation_validator` | Pure Python, no LLM call. Regex-based sentence splitting checks every `[n]` marker resolves to a real evidence index, and flags claim-bearing sentences with neither a marker nor an `(unverified)` tag. Passing persists the `Report` row; failing routes back to `synthesizer` with the exact flagged sentences quoted verbatim (up to `MAX_CITATION_RETRIES` times) so the retry is a targeted fix, not a blind re-roll. |
| 12 | `force_finalize` | Only reached if citation validation still fails after all retries — auto-tags every remaining flagged sentence `(unverified)` and persists, so a run always terminates with a citable report rather than looping forever. |

**Conditional edge**: `citation_validator` → `route_after_validation` → one of `done` (END) / `retry` (back to `synthesizer`) / `finalize` (`force_finalize` → END).

**Explicitly out of scope**: `image_harvester` (fetching real photos from web sources) and `diagram_generator` (flowchart/mermaid-style diagrams) do not exist — `chart_generator` is the only figure-producing node, and `FigureRequest.kind` is typed `Literal["chart"]` so structured-output strict mode makes requesting anything else architecturally impossible right now.

## REST API

All routes under `/api/v1` except `/health`. Auth via `Authorization: Bearer <access_token>` (15 min lifetime) unless noted; `/auth/refresh` rotates both tokens.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check, no auth. |
| POST | `/auth/register` | Create a user, returns token pair. |
| POST | `/auth/login` | Returns token pair. |
| POST | `/auth/refresh` | Exchanges a refresh token for a new access token (rotates the refresh token too). |
| GET | `/auth/me` | Current user. |
| POST | `/auth/logout` | Revokes a refresh token. |
| POST | `/research` | Starts a run (`{query, mode}`, mode ∈ `quick`/`deep`/`academic`/`competitive`). Fires the graph as a `BackgroundTask`; returns immediately with `run_id`. |
| GET | `/research` | Paginated run history for the current user (`limit`, `offset`). |
| GET | `/research/{run_id}` | Run status/metadata (tokens, cost, latency). |
| GET | `/research/{run_id}/report` | Final report markdown + citations. |
| POST | `/research/{run_id}/report/pdf` | Renders and stores a PDF export, returns a download URL. |
| GET | `/research/{run_id}/report/pdf/file` | Downloads the exported PDF file. |
| GET | `/research/{run_id}/sources` | All sources found, with credibility scores. |
| GET | `/research/{run_id}/evidence` | All evidence, joined with source + fact-check status. |
| GET | `/research/{run_id}/contradictions` | Confirmed contradictions for the run. |
| GET | `/research/{run_id}/figures` | Figures generated for the run (metadata only). |
| GET | `/figures/{figure_id}/file` | Downloads a figure's PNG bytes (auth-checked, not a static file mount). |
| GET | `/research/{run_id}/trace` | Per-node trace: status, latency, cost, input/output snapshots. |
| GET | `/eval/config` | Real dataset size + enforced cost ceiling — backs the "Run evaluation" confirmation dialog. |
| GET | `/eval` | Recent eval runs (shared benchmark, not per-user). |
| GET | `/eval/{eval_id}` | Metrics for one eval run. |
| POST | `/eval/run` | Kicks off a real, billed evaluation pass over the benchmark dataset (fire-and-forget background task); can resume a prior run or reuse `existing_run_ids` instead of re-running a question. |
| WS | `/ws/research/{run_id}?token=` | Live run stream — see below. |

## WebSocket protocol

`ws(s)://.../api/v1/ws/research/{run_id}?token={access_token}`. On connect,
the server sends a `snapshot` frame (full current state — makes a page
refresh mid-run resync correctly), then streams live frames until a terminal
one. Close codes `4401` (bad/expired token) and `4403` (run belongs to
another user) are sent only after `accept()`, so the browser's `onclose` can
actually see them.

Frame types (`app/observability/events.py`): `snapshot`, `node_started`, `node_finished`, `progress`, `stat`, `source_found`, `contradiction_found`, `report_chunk`, `done`, `error`.

The 12 graph nodes are bucketed into a fixed **7-stage** progress enum for the UI timeline (`STAGE_BY_NODE`): `understanding_query`, `creating_plan`, `searching_sources`, `extracting_evidence`, `fact_checking`, `resolving_conflicts`, `generating_report` — e.g. `credibility_scorer`+`retriever` both bucket under `extracting_evidence`, and `figure_planner`+`chart_generator` bucket under `generating_report`.

## Data model

Postgres, one row set per run (all FK'd to `research_runs.id`, cascade-deleted with it):

| Table | Holds |
|---|---|
| `users` / `refresh_tokens` | Auth. |
| `research_runs` | One row per query: mode, status, plan (JSONB), token/cost/latency totals. |
| `sources` | Every URL fetched, with domain, type, publication date, credibility score. |
| `evidence` | Every extracted claim: excerpt, confidence, optional numeric value/unit/time period, a 1536-dim pgvector embedding, full-text-search column. |
| `fact_check_results` | One per evidence item: `supported`/`unsupported`/`outdated`/`unverified`, verifying URL, notes. |
| `contradictions` | Confirmed contradictions between two evidence items, with explanation. |
| `figures` | Generated charts: kind, caption, file path, mime type, the full `ChartSpec` (JSONB), and the evidence ids it's attributed to (DB constraint: must be non-empty). |
| `reports` | Final markdown + structured citations (JSONB) + referenced figure ids. |
| `node_traces` | Per-node-execution trace: tokens, latency, cost, status, input/output snapshots — powers the Trace UI. |
| `eval_runs` | Benchmark evaluation runs (shared, not per-user): dataset version, metrics JSONB. |
| `user_preferences` | Preferred mode/source types/report format. |

## Frontend routes

| Route | Shows |
|---|---|
| `/login`, `/register` | Auth. |
| `/` | Home — greeting, research input + mode selector, live run card (timeline + stat strip) for the most recent run, recent-research list. |
| `/history` | Paginated run history. |
| `/research/{id}` | Live workspace — same live-run card, full-width, plus a streaming source panel and in-progress report preview. |
| `/research/{id}/report` | Final report: citations open a modal with the source excerpt, credibility, and fact-check status; `figure://` references render inline via an authenticated blob-fetch (`ReportFigure`); PDF export button. |
| `/research/{id}/sources` | Sources table with a monochrome credibility meter. |
| `/research/{id}/evidence` | Every claim with topic, source, and fact-check status; contradictions section. |
| `/research/{id}/trace` | Per-node latency/cost table. |
| `/evaluation` | Metrics table for the latest eval run, or an empty state; "Run evaluation" requires confirming a real, displayed cost cap before it fires. |
| `/search`, `/saved`, `/settings` | Stubs ("coming soon") — not built out this phase. |

## Cost & safety limits (`app/config.py`)

Enforced per node by `@traced`, not just documented: `MAX_RUN_COST_USD` (1.50), `MAX_EVAL_COST_USD` (1.50), `MAX_TOOL_CALLS_PER_NODE` (8), `MAX_FACT_CHECKS_QUICK/DEEP` (10/40), `MAX_FIGURES_PER_REPORT` (6), `MAX_CITATION_RETRIES` (2), `RUN_TIMEOUT_SECONDS` (900). Model tiers, reasoning-effort levels, and per-task `max_completion_tokens` caps are all in `app/llm/router.py`'s `ROUTES` table, never hardcoded per node.

## Tech stack

| | |
|---|---|
| Backend | Python 3.12, FastAPI, LangGraph 1.2.10, SQLAlchemy 2.x (async), Alembic, pgvector, matplotlib, Playwright (PDF rendering), bleach |
| Frontend | Next.js 16.3, React 19.2, Tailwind CSS v4, TanStack Query v5, react-markdown v9, lucide-react, motion |
| Infra | PostgreSQL 16 + pgvector, Redis (present, unused — no Celery worker yet), Docker Compose |
| External APIs | OpenAI (reasoning + fast model tiers, embeddings), Tavily (web search) |
