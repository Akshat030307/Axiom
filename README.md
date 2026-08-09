# Research Agent — Phase 1 (Core MVP)

Autonomous research agent. Phase 1 scope: auth, a 5-node LangGraph loop
(planner → web researcher → evidence extractor → synthesizer → citation
validator), and a minimal Next.js UI. See `PRD.md` for the full spec and
`CLAUDE.md` for project rules. Everything past Phase 1 (hybrid retrieval,
reranking, fact-checking, contradictions, figures, PDF export, WebSockets,
eval) is intentionally not implemented yet.

## Running it

```bash
docker compose up
```

Brings up Postgres (pgvector), Redis, the FastAPI backend (`:8000`), and the
Next.js frontend (`:3000`). The backend container runs `alembic upgrade head`
on every start before launching uvicorn — fine for a single dev instance;
production (`deploy/docker-compose.prod.yml`, not built yet) will move
migrations to a one-shot container so replicas don't race each other.

Real API keys (OpenAI, Tavily) already live in `.env` at the repo root — it's
gitignored and read by both `docker-compose.yml` and Alembic. `.env.example`
documents every variable with placeholders; copy it if you need a fresh
`.env`.

## Known development quirk

The backend runs `uvicorn --reload`. Editing a backend file while a research
run is in flight kills that run mid-execution (`raw_findings`/`evidence`
already written to Postgres survive; the run's `research_runs.status` is left
at `"running"` rather than transitioning to `"completed"` or `"error"`). If a
run seems to vanish while you're actively editing backend code, that's why —
not a bug in the graph itself. Avoid saving backend files while a run you
care about is executing, or just re-submit the query once you're done
editing.

## Architecture notes

- **No Celery worker in Phase 1.** Research runs execute via a FastAPI
  `BackgroundTask` in the backend process itself — the compose scope is
  intentionally just postgres/redis/backend/frontend. Redis is up but unused
  until Phase 2/3 wire in Celery + the Pub/Sub bridge for WebSocket streaming.
- **Every node is `@traced`** (`app/observability/tracer.py`), writing to
  `node_traces` with tokens/latency/cost, and enforcing `MAX_RUN_COST_USD`
  once per node before it runs.
- **Fetched web content never enters a system prompt.** It's wrapped in
  `<fetched_content source_id="...">...</fetched_content>` and placed in a
  user turn, per PRD §12.
- **The citation validator's retry gate is intentionally not armed yet** —
  see the `TODO(phase-2)` in `app/graph/nodes/citation_validator.py`. It
  computes and logs real violations, but always reports
  `citation_validation_passed = True` in Phase 1 so a heuristic false
  positive doesn't burn a reasoning-tier synthesizer retry. The retry /
  `force_finalize` wiring is fully implemented and correct for when the gate
  is armed for real.
