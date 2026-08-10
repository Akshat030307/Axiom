# Implementation Plan: Academic Researcher Mode & Image Generator Node

Concrete build plans for the two features scoped in the prior feasibility
discussion. Each section lists exact files, exact schema/field changes, graph
wiring, and a staged (cost-conscious) verification plan.

## Status: both implemented and verified (2026-08-10)

Both features are built, tested against real APIs, and committed. Real
implementation surfaced a few things this plan didn't anticipate:

- **Academic mode uses OpenAlex, not Semantic Scholar** — Semantic
  Scholar's key request landed in an approval backlog; OpenAlex issues keys
  instantly with no queue and covers the same ground, so the build target
  switched. `academic_search.py`'s shape is unchanged from what's described
  below either way.
- **OpenAlex's `search` param treats `?`/`*` as wildcard operators, not
  punctuation** — a real sub-question like "What causes coral bleaching?"
  400s with "Invalid query parameters error" otherwise, since it always
  ends in a literal `?`. Found by actually running a sub-question through
  it, not by reading the docs; `academic_search.py` strips both characters
  before searching.
- **`generate_image` lives on `LLMProvider`**, not a standalone
  `tools/image_generation.py` — `provider.py` already wraps the one
  `AsyncOpenAI` client for every OpenAI call this codebase makes
  (`generate`, `generate_structured`, `embed`); adding a second client
  instance in `tools/` for the images endpoint would've broken that
  "one client, one interface" pattern for no reason.
- **The `figures` table has a DB-level `CHECK` constraint on `kind`**
  (`figures_kind_check`), declared as raw SQL in the initial migration, not
  in the SQLAlchemy model — widening `Figure.kind`'s Python `Literal` alone
  wasn't enough. A real `INSERT` failed against it before this was caught;
  fixed with a new migration (`0002_figure_kind_illustration.py`) rather
  than editing the already-applied `0001`.
- The disclaimer text ("AI-generated illustration, not derived from
  evidence") ended up applied at the **rendering layer** (`ReportFigure.tsx`
  and `html_renderer.py`'s PDF inlining) rather than baked into the stored
  `caption`, so it can't end up embedded in data that outlives its original
  display context.

Everything below is the original plan, kept as the design record; treat the
status notes above as the corrections reality made to it.

---

## 1. Academic researcher mode

### What already exists (confirmed by reading the current code)

- `ResearchMode` already includes `"academic"`; `planner.py`'s
  `SUBQUESTION_TARGET` already gives it a distinct sub-question count (6–10).
- `config.py` already declares `SEMANTIC_SCHOLAR_API_KEY: str = ""` — unused.
- `credibility/scorer.py`'s `_SOURCE_TYPE_WEIGHT` already has
  `"academic": 0.15` wired into `score_source()`, with a docstring stating
  it's inert "until academic/data researchers exist."
- `_parse_date()` in the same file already accepts a bare `"%Y"` format —
  a paper's publication year needs no reformatting to feed the existing
  recency scoring.

So this is an *activation* of half-built plumbing, not new plumbing.

### New files

- **`backend/app/tools/academic_search.py`** — mirrors `web_search.py`'s
  shape exactly so `web_researcher_node`'s loop doesn't need restructuring:

  ```python
  async def search(query: str, max_results: int = 5) -> list[dict]:
      """Returns the same shape as tools.web_search.search(): a list of
      {url, title, content, published_date}. `content` is the paper's
      abstract — used directly as fetched_content, no separate fetch step
      needed (unlike web results, there's no full page to retrieve)."""
  ```

  Implementation: `GET https://api.semanticscholar.org/graph/v1/paper/search`
  with `query`, `limit=max_results`, `fields=title,abstract,url,year,
  externalIds,citationCount,venue`. Send `x-api-key` header only if
  `settings.SEMANTIC_SCHOLAR_API_KEY` is non-empty (the API works keyless,
  just at a lower rate limit — see Rate limits below). Map each result to
  `{"url": paper.get("url") or f"https://doi.org/{doi}" if doi else
  semantic_scholar_page_url, "title": ..., "content": abstract, "content"
  doubling as "raw_content" for parity, "published_date": str(year) if year
  else None}`. A paper with no abstract is dropped (nothing to extract
  evidence from), same as `web_researcher` already drops a page with no
  extractable content.

  No `httpx`/`aiohttp` client currently exists in `app/tools/` — `httpx` is
  already a pinned dependency (`requirements.txt`), reuse it rather than
  adding a new HTTP library.

### Modified files

- **`backend/app/graph/nodes/web_researcher.py`**:
  - Replace the single `from app.tools.web_search import search` with both
    tools imported, and branch once at the top of the node:
    `search_fn = academic_search.search if state["mode"] == "academic" else
    web_search.search`, then use `search_fn(...)` in the existing loop —
    the rest of the loop body (dedup by URL, chunk selection, `Source`
    row, `ctx.events.source_found`) is untouched.
  - `source_type="web"` in the `Source(...)` construction becomes
    `source_type="academic" if state["mode"] == "academic" else "web"`.
  - Academic-mode results skip the `fetch_clean_text()` fallback entirely
    (abstract *is* the content) — the existing `if not text and
    tool_calls_used < MAX...` branch only fires when `text` is falsy, so
    for academic mode this is naturally a no-op as long as `content` is
    populated from the abstract.

- **`backend/app/config.py`**: no new fields required — `SEMANTIC_SCHOLAR_
  API_KEY` already exists. Optional: `SEMANTIC_SCHOLAR_BASE_URL: str =
  "https://api.semanticscholar.org/graph/v1"` if you'd rather not hardcode
  it in the tool file.

### Rate limits (verified, not assumed)

Keyless: shared 1 request/sec-ish across all unauthenticated callers
(reported inconsistently across sources — treat as roughly 100 requests per
5 minutes, safe assumption). `MAX_TOOL_CALLS_PER_NODE` (8) already bounds
`web_researcher` well under this per run regardless, so **no throttling code
is needed at current call volumes.** Flag for later: if Phase A of the
parallelization plan (`asyncio.gather` inside `web_researcher`) ships before
a Semantic Scholar API key is obtained, academic-mode's concurrency limit
must be capped lower than other modes' — 1 concurrent call, not
`MAX_TOOL_CALLS_PER_NODE`-wide — to avoid 429s.

### Optional / stretch (not required for a working academic mode)

- **Migration**: add a `metadata: JSONB` column to `sources` (it has none
  today — only `evidence` does) to store `{doi, authors, citation_count,
  venue}`. Needed only if you want to surface these in the Sources UI.
- **Credibility enhancement**: extend `CredibilitySignals` with
  `citation_count: int | None` and add a citation-based bonus to
  `score_source()`. This changes a function whose docstring specifically
  advertises it as a from-scratch, deterministic, side-effect-free design —
  treat as a separate, reviewed change, not a drive-by addition.

### Verification plan (staged by cost)

1. **$0** — standalone script calling `academic_search.search("coral
   bleaching causes")` directly, confirm result shape (title/url/content/
   published_date populated, abstract present).
2. **$0** — `.__wrapped__` bypass test of `web_researcher_node` with
   `mode="academic"`, reusing an *existing* persisted `ResearchPlan` from a
   completed run (no new planner call) — confirm `Source` rows land with
   `source_type="academic"` and evidence extraction succeeds on abstract
   text same as it does on web text.
3. **~$0.30–0.45, requires your go-ahead** — one real end-to-end academic-
   mode run, per the standing rule of confirming before any paid batch
   spend.

### Effort

Small. One new tool file (~40 lines, mirroring an existing one), a
conditional branch in one existing node, zero graph topology changes, zero
new prompts, zero new DB migrations for the MVP version.

---

## 2. Image generator node

### The one design decision that matters more than any file list

`chart_generator` is trustworthy because `_values_are_grounded()` rejects
any value not traceable to real evidence — there is no equivalent check
possible for a generated image, because it's pixels from a prompt, not a
rendered data structure. Two consequences this plan bakes in rather than
leaves implicit:

1. **Keep it structurally separate from the chart pipeline**, not a new
   `kind` value bolted onto `FigureRequest`. Chart requests and illustration
   requests validate completely differently; forcing them through one
   `Literal["chart", "illustration"]` risks a future edit that forgets to
   special-case illustrations wherever grounding is assumed. Use a distinct
   `IllustrationRequest` schema and a distinct node pair, mirroring
   `figure_planner`/`chart_generator`'s shape without sharing their types.
2. **The generation prompt must forbid rendered text, numbers, or specific
   claims inside the image itself**, as a hard system-prompt constraint —
   the one class of hallucination an image model can produce that would
   otherwise be indistinguishable from real data at a glance. Illustrations
   are atmospheric/conceptual only, never data-bearing.

### Schema changes (`backend/app/models/schemas.py`)

- `Figure.kind` is already `Literal["chart", "diagram", "source_image"]` —
  none of those three is quite right for a generative illustration
  (`"diagram"` stays reserved for the still-deferred structural
  `diagram_generator`, which would be schematic/mermaid-style, not
  photorealistic/generative). Add a fourth value: `Literal["chart",
  "diagram", "source_image", "illustration"]`.
- New model, separate from `FigureRequest`:
  ```python
  class IllustrationRequest(BaseModel):
      intent: str
      caption: str
      evidence_ids: list[str]  # for attribution/traceability of *why* it was made, not grounding of its content
  ```
- New model for the prompt-writing step's structured output:
  ```python
  class ImagePrompt(BaseModel):
      prompt: str          # must satisfy the no-text/no-numbers constraint below
      caption: str
  ```

### New files

- **`backend/app/agents/prompts/illustration_planner.md`** — mirrors
  `figure_planner.md`'s structure: propose 0+ illustration requests only
  where a purely conceptual visual genuinely adds value (not "one per
  section"), capped by a new `MAX_ILLUSTRATIONS_PER_REPORT` setting.
- **`backend/app/agents/prompts/image_prompt_writer.md`** — the critical
  prompt. Must explicitly instruct: no rendered text, no numbers, no
  statistics, no charts-within-the-image, no depiction of a specific claim
  as fact — describe mood/subject/style only (e.g. "a bleached coral reef,
  documentary photography style" is fine; "a coral reef with 84% of coral
  bleached, chart overlay" is exactly what must never be produced).
- **`backend/app/graph/nodes/illustration_planner.py`** — same shape as
  `figure_planner.py`: reasoning-tier structured call, validates every
  cited `evidence_id` against the real retrieved-evidence set, caps output
  at `MAX_ILLUSTRATIONS_PER_REPORT`.
- **`backend/app/graph/nodes/image_generator.py`** — for each accepted
  request: one fast/reasoning-tier call (`image_prompt_writer` route) to
  turn the request's `intent` into a vetted `ImagePrompt`, then one call to
  OpenAI's Images API with that prompt, store the PNG via the existing
  `app/figures/storage.py` (already generic, not chart-specific), persist a
  `Figure` row with `kind="illustration"`.
- **`backend/app/tools/image_generation.py`** — thin wrapper around the
  OpenAI images endpoint, analogous to how `llm/provider.py` wraps chat
  completions. Returns raw PNG bytes + the actual billed cost (flat
  per-image, not token-based — see Cost accounting below).

### Modified files

- **`backend/app/config.py`**: add `OPENAI_IMAGE_MODEL: str =
  "gpt-image-1-mini"` (cost-conscious default — see cost analysis below),
  `IMAGE_QUALITY: str = "low"`, `MAX_ILLUSTRATIONS_PER_REPORT: int = 2`
  (deliberately much lower than `MAX_FIGURES_PER_REPORT`'s 6 — illustrations
  cost more per unit and add less verifiable value than a chart).
- **`backend/app/config.py`**'s `build_pricing()` / a new sibling function:
  image cost isn't input/output-token-shaped, so it doesn't fit the existing
  `PRICING` dict shape. Add a small `IMAGE_PRICING: dict[str, float]` keyed
  by `(model, quality)` → flat USD per image, and have `image_generator.py`
  compute its own cost and pass it via `NodeResult.cost_override` — this is
  exactly the mechanism `retriever`/`contradiction_detector`/
  `chart_generator` already use for non-single-model cost, so `@traced`'s
  cost-ceiling enforcement needs zero changes.
- **`backend/app/llm/router.py`**: add an `"illustration_planning"` route
  (reasoning tier, same shape as `"figure_planning"`) and an
  `"image_prompt"` route (fast tier) for the prompt-writing step. The
  actual image generation call is not a chat completion and does not go
  through this router at all — it's a separate provider call.
- **`backend/app/graph/state.py`**: add `illustration_requests:
  list[IllustrationRequest]` as a sequential key (same pattern as
  `figure_requests`). `figures` needs no change — it's already
  `Annotated[list[Figure], operator.add]`, so `image_generator`'s output
  fans into the same list `chart_generator` already populates, regardless
  of node order.
- **`backend/app/graph/graph_builder.py`**: insert
  `chart_generator → illustration_planner → image_generator → synthesizer`
  (was `chart_generator → synthesizer`) — mirrors the existing
  `figure_planner → chart_generator` pairing exactly, just one hop later so
  `synthesizer` sees both chart and illustration figures in one `figures`
  list by the time it prompts.
- **`backend/app/graph/nodes/synthesizer.py`**: no change needed —
  `_format_figures_list()` already iterates `state.get("figures")`
  generically by `fig.id`/`fig.caption`, not by kind.

### Frontend changes

- **`frontend/src/components/report/ReportFigure.tsx`**: the existing
  authenticated blob-fetch rendering works unchanged for any `kind` — no
  change needed to *display* an illustration. Add one thing: a visible,
  permanent badge/caption suffix when `figure.kind === "illustration"` —
  e.g. `"{caption} — AI-generated illustration, not derived from evidence"`
  — so it's never visually confusable with a grounded chart. This is the
  one frontend change this feature actually requires; skipping it is not an
  acceptable shortcut given the grounding concern above.
- **`frontend/src/types/api.ts`**: `FigureResponse.kind` type widens from
  whatever it is today to include `"illustration"`.

### Cost accounting (verified pricing, not memorized)

| Model | Quality | Cost/image |
|---|---|---|
| `gpt-image-1-mini` | low/default | **~$0.005** |
| `gpt-image-1.5` / `gpt-image-2` | high | $0.13–$0.21 |

Note: the original `gpt-image-1` retires Oct 23, 2026 — don't build against
it. With the recommended defaults (`gpt-image-1-mini`, `MAX_ILLUSTRATIONS_
PER_REPORT=2`), worst case is **~$0.01/report** — negligible next to a
typical run's existing ~$0.15–0.45 LLM spend. At flagship high-quality
instead, the same 2-image cap costs $0.26–$0.42/report — still bounded, but
now comparable to the rest of the run's entire cost. **Do not raise the
per-report cap toward `MAX_FIGURES_PER_REPORT` (6) unless staying on the
mini tier** — 6 flagship-quality images alone would cost $0.78–$1.26,
approaching the whole-run $1.50 ceiling on images alone.

### Verification plan (staged by cost)

1. **~$0.005** — standalone script calling the new
   `tools/image_generation.py` wrapper directly with a hand-written test
   prompt, confirm PNG bytes come back and render correctly.
2. **~$0.01** — `.__wrapped__` bypass test of `illustration_planner_node` +
   `image_generator_node` against evidence from an *existing* completed run
   (no new planner/search cost), confirm a `Figure` row is created with
   `kind="illustration"` and `cost_override` is tracked correctly.
3. **$0** — frontend check: manually attach the test illustration's id to a
   copy of a report's markdown (same non-destructive technique used to
   verify chart rendering earlier), screenshot-verify the new "AI-generated"
   badge renders and is visually distinct from a chart figure.
4. **~$0.30–0.45 + ~$0.01 images, requires your go-ahead** — one real
   end-to-end run with illustrations enabled.

### Effort

Moderate — genuinely a new node pair, two new prompts, a non-token pricing
path, and one required (not optional) frontend change. Larger than academic
mode, comparable in scope to how `chart_generator` itself was built.

---

## Suggested build order

The two features are fully independent — no shared files force an
ordering. If sequencing only one at a time: **academic mode first** — it's
smaller, reuses more existing plumbing (the credibility bonus is *already
wired and waiting*), costs less to verify, and improves report quality
(better sources) rather than adding a new hallucination-risk surface. Image
generator's main open cost is the design decision above (separate schema
path, hard no-text/no-numbers prompt constraint) — worth confirming that
approach before writing any code for it, since it's the one part of this
plan that's a judgment call rather than a mechanical extension of existing
patterns.
