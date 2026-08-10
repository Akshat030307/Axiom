# Parallelization, Tool Caching & Multi-Provider Plan

Status: **planning only — nothing in this document is implemented.** Written
in response to a request to reduce pipeline latency via concurrent tool
calls, cache tool-call results, and diversify the APIs different nodes use.
The image-generation node mentioned alongside this request is intentionally
**not** designed here — see "Deferred" at the end.

This plan is grounded in the current code (`backend/app/graph/`,
`backend/app/tools/`, `backend/app/observability/`), not a clean-slate
redesign. Each phase below names the exact files it touches and the exact
constraint in the current code that makes it safe or unsafe.

## Why this isn't a single change

Three real constraints in the current implementation make "just parallelize
it" unsafe to do in one step:

1. **One `AsyncSession` per run, by design.** `RunContext.db`
   (`app/graph/run_context.py`) is a single SQLAlchemy `AsyncSession` "owned
   for the entire run" on the explicit documented assumption that "the graph
   is strictly sequential, so one session has no concurrent-access hazard."
   SQLAlchemy's `AsyncSession` is not safe for concurrent use from multiple
   coroutines. Any change that runs two nodes' bodies concurrently must
   solve this first, or it will corrupt writes silently under load.

2. **Cost-ceiling enforcement is check-then-act, not atomic.** `@traced`
   (`app/observability/tracer.py`) checks `SUM(node_traces.cost_usd) >=
   MAX_RUN_COST_USD` *before* a node runs, then commits that node's own cost
   *after* it finishes. Two nodes racing through this check concurrently can
   both pass it before either has committed, overshooting the ceiling — the
   one enforcement mechanism this whole cost-safety story rests on.

3. **The live-progress UI assumes strict stage order.** The WebSocket's
   7-stage timeline (`STAGE_BY_NODE` in `app/observability/events.py`, and
   the frontend's `ProgressTimeline`) buckets the 12 graph nodes into 7
   stages and renders them as a linear checklist. Two nodes from different
   stages finishing out of order (or simultaneously) isn't a case the
   current frame stream or the frontend component was built to represent.

None of these are reasons *not* to do this — they're the reasons to sequence
it as phases that each de-risk the next, rather than one large change.

## Phase A — Intra-node concurrency (no graph topology change)

**The highest-value, lowest-risk win, and the one to do first.** Several
nodes already loop over independent items sequentially, calling `await`
inside a `for` loop when nothing about the iterations depends on each other:

| Node | Current sequential loop | What's independent |
|---|---|---|
| `web_researcher` | One `search()` call per sub-question, then one `fetch_clean_text()` per result | Every sub-question's search is independent; every fetch within a sub-question's results is independent |
| `fact_checker` | One search + one LLM verification call per cluster representative (up to `MAX_FACT_CHECKS_{QUICK,DEEP}`) | Every cluster's verification is independent |
| `contradiction_detector` | One classification call per group (stage 2), then one resolution call per flagged pair (stage 3) | Every group/pair is independent within its own stage |
| `chart_generator` | One `chart_spec` call + render per figure request | Every figure request is independent |

This does **not** require LangGraph `Send()` fan-out or touching
`graph_builder.py` at all — it's `asyncio.gather(...)` (bounded by an
`asyncio.Semaphore`, since `MAX_TOOL_CALLS_PER_NODE` and the fact/contradiction
caps exist specifically to bound spend, and unbounded concurrency would blow
past a token-per-minute or requests-per-minute limit on the OpenAI/Tavily
side before it blew past our own cost ceiling) *inside* a single node body.
The node's own `NodeResult` bookkeeping (summed tokens/cost via
`cost_override`, already the pattern `retriever` and `contradiction_detector`
use for mixed-model cost) stays correct as long as each concurrent branch
returns its own usage numbers to be summed after `gather` — no different
from summing them in a loop today.

**Constraint this phase must respect:** none of these loops currently touch
`ctx.db` from more than one coroutine at once. They must stay that way — do
the concurrent I/O (search/fetch/LLM calls) inside `gather`, then do all
`ctx.db.add(...)` calls sequentially afterward, on the main coroutine, once
the gathered results are back. That keeps constraint #1 above satisfied
without solving it — no session-per-branch machinery needed for this phase.

**Expected effect:** `web_researcher` and `fact_checker` are almost
certainly the two largest contributors to end-to-end run latency today
(each doing several sequential network round-trips) — this phase should cut
their wall-clock time roughly by the fan-out factor, with no cost increase
(same number of calls, just concurrent instead of sequential) and no change
to `graph_builder.py`, `ResearchState`, or the WebSocket contract.

## Phase B — Exact-match tool-call caching (Redis)

Redis is already provisioned in `docker-compose.yml` and currently unused
(`REDIS_URL` exists in `config.py`, nothing reads or writes it yet) — this
phase adds its first real consumer.

Cache at the tool layer, not the LLM layer: `app/tools/web_search.py`'s
`search()` and `app/tools/web_fetch.py`'s `fetch_clean_text()` are the
highest-value targets, since the same query or URL recurring across runs
(dev iteration, re-running the same demo question, `academic`/`competitive`
modes re-deriving similar sub-questions) currently re-pays Tavily/fetch cost
and latency every time.

- **Key**: a normalized hash of `(provider, query)` for search, or the bare
  URL for fetches.
- **TTL, not permanent**: web content changes, and this is a *research*
  agent — a permanently-cached answer to "current coral bleaching
  statistics" would silently go stale. A TTL on the order of hours-to-a-day
  is a reasonable starting point; it should be a config value
  (`TOOL_CACHE_TTL_SECONDS`), not a hardcoded constant, since the right
  answer differs by how time-sensitive a deployment's typical queries are.
- **Only exact-match to start.** This phase deliberately does *not* do the
  "retrieve if similar" part of the request — see Phase D for why that's
  split out as a separate, higher-risk phase.
- **Cache hits should still produce a `Source`/evidence trail** — a cached
  result must remain fully traceable back to the original fetch (store the
  original fetch timestamp alongside the cached body, surface it in
  `node_traces.input` for that node), so citation provenance doesn't quietly
  become "we don't actually know when this was fetched."

**Expected effect:** near-zero latency and cost for a repeated query during
demo/dev iteration (the exact scenario "reuse existing completed runs for
testing" already relies on manually today); no effect on cost/latency for a
genuinely novel query, since there's nothing to hit.

## Phase C — Graph-level fan-out (the real topology change)

Once Phase A proves intra-node concurrency is safe and Phase B's Redis usage
is live, the graph itself has a real fan-out opportunity: `fact_checker`,
`contradiction_detector`, and `figure_planner` all read only
`retrieved_evidence` (output of `retriever`) and don't read each other's
output — they're sequential today (`retriever → fact_checker →
contradiction_detector → figure_planner → chart_generator → synthesizer`)
purely because sequential edges are this codebase's established pattern, not
because of a real data dependency between those three specifically.

`fact_checker` and `contradiction_detector` could become two parallel
branches off `retriever`, both feeding into `figure_planner` (LangGraph
supports fan-out/fan-in via multiple edges into one node, the same way
`figures` is already an `Annotated[list[Figure], operator.add]` reducer key
in `ResearchState` — that pattern generalizes to letting two branches write
different keys and both be present when the fan-in node runs).

**This phase cannot start until constraints #1 and #2 above are actually
solved**, not worked around:

- **DB session**: either give each parallel branch its own `AsyncSession`
  scoped to that branch (opened from the same engine, committed
  independently) with a final merge point, or move `@traced`'s own writes
  (the `NodeTrace` row, the cost-ceiling check) onto a concurrency-safe path
  (e.g. a dedicated lightweight connection per trace write) while leaving
  node business logic to manage its own session. The former is more
  consistent with how `RunContext` already models "the DB is per-run
  state"; the latter is a smaller diff. Worth a real design pass before
  picking, not a default.
- **Cost ceiling**: needs to become check-and-reserve rather than
  check-then-act — e.g. an atomic Redis counter (`INCRBY` the node's
  estimated max cost before it starts, reconcile to actual after) so two
  concurrent branches can't both pass a stale check. This is also the
  natural place to put Phase B's Redis connection to work a second time.
- **WebSocket stage contract**: `STAGE_BY_NODE` and the frontend's
  `ProgressTimeline` need to represent two stages as concurrently
  in-progress, not just complete/active/pending in one linear order. This is
  a frontend contract change, not just a backend one — needs explicit
  scoping (does the timeline show two rows "active" at once? collapse them
  into one "verifying evidence" row while both run? that's a design
  decision, not just an engineering one).

**Expected effect:** the second-largest latency win after Phase A, but it's
also the phase with the most surface area for a subtle bug (a race in cost
accounting or a lost DB write under concurrent access is the kind of thing
that passes testing and fails in production under load) — it should not be
attempted until Phase A has been running in practice long enough to build
confidence in the concurrency patterns being used.

## Phase D — Similarity-based ("semantic") tool-call caching

This is the "retrieve them if they are similar" part of the request, split
out from Phase B deliberately because it trades a small amount of accuracy
risk for additional cache-hit coverage, and that trade needs to be made
consciously, not as a side effect of a latency optimization:

- Embed each cached search query (reusing the existing embedding
  infrastructure in `app/retrieval/embeddings.py` — no new embedding model
  needed) and look up nearest neighbors above a similarity threshold before
  falling through to a real search.
- **The risk this phase must design around**: a "similar but not identical"
  cache hit serving stale or subtly-wrong-context results is a *correctness*
  bug in a system whose entire value proposition is citation traceability —
  not just a latency/cost optimization gone slightly wrong. A wrong cache
  hit here doesn't fail loudly; it silently feeds a plausible-looking but
  mismatched source into evidence extraction, and nothing downstream
  (fact_checker, citation_validator) is positioned to catch "this evidence
  came from a query that wasn't quite the one asked."
- Mitigation direction (not a final design): a conservative similarity
  threshold well above what `CLAIM_SIMILARITY_THRESHOLD`/
  `CONTRADICTION_CLUSTER_THRESHOLD` use for evidence clustering (those
  operate on claims already extracted by an LLM and vetted downstream; a
  cache hit skips extraction and verification entirely, so it needs a much
  higher bar), plus storing which original query a similarity-cache hit
  actually matched so it's auditable from `node_traces` after the fact.
- This phase should not start until Phase B (exact-match) has real
  hit-rate data — if exact-match alone captures most of the realistic
  benefit (repeated dev/demo queries, `academic` mode's overlapping
  sub-questions), the added correctness risk of similarity matching may not
  be worth it at all.

## Phase E — Multi-provider tool routing

Today there is exactly one search provider (`TavilyClient`, hardcoded in
`app/tools/web_search.py`) used for everything: `web_researcher`'s
exploratory search and `fact_checker`'s independent verification search
both call the same `search()` function. `SEMANTIC_SCHOLAR_API_KEY` already
exists as a config field (`app/config.py`) but has no code path using it
anywhere — a hook left in place, never wired up.

The proposed shape mirrors the pattern already proven for LLM calls
(`app/llm/router.py`'s task → tier table): a small `TOOL_ROUTES` table
mapping a named task (`"web_search"`, `"fact_check_search"`,
`"academic_search"`, ...) to a provider, instead of one function every node
calls. Concrete first candidate: route `academic` mode's searches (and
`fact_checker`'s verification searches, which are themselves a form of
"find an authoritative source about X") through Semantic Scholar when the
claim/topic looks academic, falling back to Tavily otherwise — this uses an
already-provisioned key rather than adding a new one.

Called out explicitly per the request: **this does not reduce cost by
default just because a provider has a free tier.** More providers means more
integration code, more failure modes to handle gracefully (today
`web_researcher` already treats a failed search as non-fatal and continues —
any new provider needs the same defensive handling), and likely *more* total
calls in the near term while both providers run for comparison/fallback
before one is trusted alone. This phase is about coverage/quality
(matching the right source type to the right kind of claim) more than a
cost play, and should be scoped that way rather than sold as a pure
cost-saver.

## Suggested sequencing

| Phase | Risk | Latency win | Blocked on |
|---|---|---|---|
| A — intra-node concurrency | Low | High | Nothing — can start immediately |
| B — exact-match tool caching | Low | Medium (situational — big for repeated queries, zero for novel ones) | Nothing — can start immediately, in parallel with A |
| C — graph-level fan-out | High | Medium-high | A proven in practice; DB-session and cost-ceiling redesign done first |
| D — similarity-based caching | Medium-high (correctness, not just engineering risk) | Low-medium | B's real hit-rate data |
| E — multi-provider tool routing | Medium (integration surface) | ~None directly (coverage/quality play) | Nothing structurally, but lowest priority of the five |

A and B can start immediately and independently. C, D, and E are each
genuinely separate design efforts, not follow-on tasks of A/B — none of them
should be scoped as "just extend the caching layer" or "just add another
branch" without the dedicated design pass each section above calls out.

## Deferred: image generator node

Out of scope for this document entirely, per the request that raised it —
noted here only so it isn't lost. The current figures pipeline
(`figure_planner` → `chart_generator`, see `README.md`) deliberately
excludes both `image_harvester` (real photos from web sources) and
`diagram_generator`; `FigureRequest.kind` is typed `Literal["chart"]`,
making that exclusion structural, not just a missing node. Whenever this is
picked up, it's a new node design (licensing/attribution for harvested
images is a real question chart generation never had to answer) — not an
extension of anything in this plan.

## Open questions before any phase becomes an implementation plan

1. **Phase A**: what concurrency limit per node? `MAX_TOOL_CALLS_PER_NODE`
   (8) already exists as a total-calls budget — does a semaphore of the same
   size make sense, or should it be smaller to stay under a provider's
   requests-per-second limit regardless of the total-calls budget?
2. **Phase B**: what TTL, and should it be configurable per tool
   (`web_search` vs `fetch_clean_text` plausibly want different staleness
   tolerances)?
3. **Phase C**: separate-session-per-branch vs. concurrency-safe trace
   writes — this needs a real decision, not a default, before any code gets
   written.
4. **Phase C**: how should the frontend's 7-row timeline represent two
   concurrent stages? This is a design/product question, not just backend.
5. **Phase E**: is Semantic Scholar actually the right first provider to
   wire up, or is there a more valuable one for this system's typical query
   mix?
