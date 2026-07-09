# Role Inference Service

Maps messy SSO profiles (Okta/Entra/Google-shaped) to the most likely role in an
organization's canonical Work Architecture catalog — with a confidence score,
a structured explanation, and an admin override workflow that never destroys
the underlying inference history.

Built for a take-home assignment scoped to ~1 focused day. The design draws on
a production-scale architecture reference (staged pipeline, layered matching,
calibrated confidence, non-destructive overrides), scaled down deliberately
for 8 sample users and a 10-role catalog. Every place that's a simplification
rather than an oversight is called out explicitly below.

---

## Business problem

Enterprises authenticate users via SSO, and the profile data that comes back
is inconsistent, incomplete, and noisy — job titles are free text a manager
typed, departments are named differently across orgs, and skills/groups are
often absent. Almost every downstream capability (access provisioning,
license allocation, workforce analytics, AI assistants) keys off "what role
does this person actually have" — expressed in the organization's own
canonical taxonomy, not whatever string their SSO happened to store.

This service is the bridge: it turns a raw SSO payload into a role assignment
that's explainable, auditable, and correctable by a human — and it's honest
when the data isn't good enough to guess.

---

## Setup (should take well under 10 minutes)

```bash
git clone <this-repo>
cd role-inference-service

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # optional: add OPENAI_API_KEY to enable live LLM disambiguation

python scripts/seed.py             # loads the 10-role catalog + 8 sample users, runs inference for each
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000/** for the admin page, or
**http://127.0.0.1:8000/docs** for interactive Swagger API docs.

No `OPENAI_API_KEY` is required — the LLM disambiguation stage falls back to a
deterministic stub when no key is configured, so the whole system runs with
zero external dependencies out of the box. Add a key to `.env` to see the real
LLM path (only exercised on the small fraction of profiles that are
genuinely ambiguous — see below).

### Or run with Docker

```bash
cp .env.example .env               # optional: add OPENAI_API_KEY
docker compose up --build
```

Same **http://127.0.0.1:8000/**. The container runs `scripts/seed.py` on
every start (schema migration + sample-data seeding — both idempotent, so a
restart is a no-op past the first run) before starting `uvicorn`. The SQLite
file lives in a named volume (`db-data`) so it survives `docker compose down`
/ `up` cycles; `docker compose down -v` wipes it for a clean-slate rerun.
Compose reads `.env` automatically for `OPENAI_API_KEY` substitution — same
optional-key behavior as the bare-metal path above.

> The Docker setup was written and reasoned through carefully but not
> build-tested in the environment this was developed in (no Docker daemon
> available there) — run `docker compose up --build` once yourself to confirm
> before depending on it for a demo.

Run the test suite (69 tests, all offline/hermetic):

```bash
pytest
```

Quick API smoke test:

```bash
curl -s http://127.0.0.1:8000/api/users/usr_001/inference | python3 -m json.tool
```

---

## Architecture overview

```
SSO payload (Okta/Entra/Google-shaped)
        │
        ▼
 POST /profiles ──► Profile (versioned, raw+normalized) ──► inference triggered
        │                                                        │
        ▼                                                        ▼
 ┌──────────────────────────── Inference Pipeline ────────────────────────────┐
 │ 1. normalize   2. extract signals   3. generate candidates   4. score/rank │
 │ 5. LLM disambiguation (only if top1/top2 margin is tight)                  │
 │ 6. compute confidence   7. build explanation   8. persist + audit          │
 └───────────────────────────────────┬────────────────────────────────────────┘
                                      ▼
                     InferenceRun (immutable) ──► Mapping (effective role)
                                      ▲
                                      │ respects pin
                          Override (admin, non-destructive) ◄── PATCH/DELETE
                                      │
                                      ▼
                        Static admin page (list users, view explanation,
                        override/reset) ── talks only to the REST API
```

**Stack:** Python + FastAPI + SQLite (SQLAlchemy for tables, Pydantic for
API/DTO schemas — kept deliberately separate, see [Data model](#data-model)).
No frontend framework or build step for the admin page.

**Layers:**
- `app/pipeline/` — the inference engine. Pure functions, no DB or HTTP
  imports. Fully unit-testable without a database.
- `app/services/` — persistence and read-model glue: ingestion, running +
  storing inference, the override lifecycle, audit logging, view assembly.
- `app/api/` — thin FastAPI routers. No business logic; they call services
  and shape responses.
- `app/models/` — `tables.py` (SQLAlchemy ORM) and `schemas.py` (Pydantic
  DTOs), intentionally not the same objects — the wire contract can evolve
  without a migration, and vice versa.
- `app/static/` — the admin page (vanilla HTML/CSS/JS).

This is a **single-tenant** build (no `organizations` table, no per-tenant
config). Multi-tenancy is a real production requirement but adds isolation
and RBAC concerns that would drown out the actual assignment focus — see
[What I'd build next](#what-id-build-next).

### What's scaled down from a production design, and why

| Production concern | This build | Why it's fine at this scale |
|---|---|---|
| Event bus / message queue for `ProfileUpdated`, `RoleCatalogUpdated` | Direct synchronous function calls | 8 users, 10 roles — a queue adds ops complexity with no throughput benefit yet |
| Vector DB / embedding search for semantic title matching | Fuzzy string matching (`rapidfuzz`) + a curated keyword/synonym table | Only 10 roles to search; brute-forcing all of them per profile is sub-millisecond |
| Background workers for bulk reprocessing | `POST /reprocess` runs synchronously in a request | Reprocessing 8 users is instant; the seam (`run_and_persist_inference`) is the same function a queue consumer would call |
| Per-tenant configuration | Global `app/config.py` constants | Single tenant; the settings object is already the seam for making these per-tenant later |
| RBAC / auth on the API | None | Explicitly out of scope per the assignment ("we do not care about... production deployment") |
| Calibrated confidence (Platt scaling against labeled outcomes) | Hand-set weights and thresholds, documented and tunable | No labeled dataset to calibrate against yet; see the bonus eval harness in `eval/` for the seam |

---

## How the inference pipeline works

The core design principle, straight from the brief: **avoid one giant prompt
that dumps all the data and asks an LLM to guess.** A monolithic prompt is
slow, non-deterministic, expensive, hard to test, and impossible to audit.
Instead, an 8-stage pipeline where each stage is independently testable and
the LLM is used *only* where deterministic methods genuinely can't
disambiguate.

| Stage | File | What it does |
|---|---|---|
| 1. Normalize | `pipeline/normalize.py` | Unicode-folds, strips punctuation, expands a curated abbreviation table (`Sr`→`Senior`, `BI`→`Business Intelligence`, `VP`→`Vice President`...), strips trailing level suffixes (`Platform Engineer II`→`Platform Engineer`), flags empty/generic/vanity titles. Pure and deterministic; raw values are preserved alongside normalized ones for audit/display. |
| 2. Extract signals | `pipeline/signals.py` | Turns normalized text into structured features: a seniority level from a title ladder (intern→...→executive), function hints from manager title / groups / free-text notes via a curated keyword table, a keyword bag for catalog-keyword overlap. Tracks which signal *categories* are actually present, independent of the catalog. |
| 3. Generate candidates | `pipeline/candidates.py` | Scores every catalog role (only 10 — brute force is fine at this scale) against present signals: title fuzzy match, department fuzzy match, skills overlap, group/manager function-hint alignment, keyword overlap, seniority match. Each sub-score carries a human-readable `detail` string used later for explanation. |
| 4. Score & rank | `pipeline/scoring.py` | Fuses per-signal sub-scores into one weighted score per role, **renormalized over whichever signals are actually present** — a profile with only a title isn't punished to zero, it's scored on less evidence (and that shows up later as lower *coverage*, not a lower raw score). Computes the top1/top2 margin. |
| 5. LLM disambiguation | `pipeline/llm_disambiguate.py` | **Only runs when the margin is below threshold** (`0.08`, configurable) and there are ≥2 viable candidates. Calls OpenAI with structured output; `chosen_id` is **enum-constrained to the shortlist's role_ids plus `"none"`** — the model cannot invent a role. Validated post-hoc (JSON parses, schema matches, id is actually in the shortlist); falls back to a deterministic stub (top candidate, `llm_degraded=true`) on a missing API key, invalid response, or exhausted retries. |
| 6. Compute confidence | `pipeline/confidence.py` | A calibrated, decomposed number — not a raw score or an LLM's self-reported certainty. See [Confidence model](#confidence-model). |
| 7. Generate explanation | `pipeline/explain.py` | Assembled entirely from stage 3/4 evidence and the stage 6 breakdown: signals used, positive/negative evidence, alternatives with a contrastive `why_lost`, missing-information callouts. Never free-form LLM prose standing alone — it can't contradict the numbers behind it. |
| 8. Persist + audit | `services/inference_service.py` | Writes an immutable `InferenceRun` (pinning `profile_version`, `catalog_version`, `engine_version`, `prompt_version` for reproducibility), updates the `Mapping` read model, writes an audit log entry. |

Stages 1–7 live in `pipeline/orchestrator.py::run_inference()`, a **pure
function** of `(profile, catalog) -> PipelineResult` with no database access
— fully testable without spinning up SQLite. Stage 8 (persistence) is
deliberately kept in the service layer, not the pipeline, so the pipeline
stays storage-agnostic.

### Why this beats "one prompt"

- **Testability** — every stage has deterministic unit tests; matching logic
  is regression-tested without ever calling an LLM.
- **Cost/latency** — with the default weights, only genuinely ambiguous
  profiles reach the LLM (1 of the 8 sample users, deterministically).
- **Explainability** — the explanation is assembled from real sub-scores, not
  a model's post-hoc story about itself.
- **Anti-hallucination by construction** — the LLM only ever *chooses from a
  shortlist the deterministic layers already vouched for*; it cannot return a
  role that isn't in the catalog.

### Real output on the 8 sample users

Observed running `python scripts/seed.py` with no `OPENAI_API_KEY` set (so
stage 5's stub always runs when triggered):

| User | Title | Inferred role | Confidence | Band | Notes |
|---|---|---|---|---|---|
| usr_001 | Sr BI Analyst | Senior Data Analyst | 0.64 | medium | Seniority signal correctly breaks the tie against the (otherwise lexically similar) mid-level Data Analyst |
| usr_002 | Platform Engineer II | Platform Engineer | 0.54 | low | Level-suffix stripping + skills overlap (Kubernetes, Terraform) |
| usr_003 | Customer Outcomes Lead | Customer Success Manager | 0.59 | low | Title doesn't literally match — department/manager/group function-hints carry it |
| usr_004 | Product Strategy Manager | Senior Product Manager | 0.61 | medium | Margin vs. Product Manager was genuinely tight (0.80 vs 0.77) — **escalated to stage 5**, stub fell back to the deterministic leader |
| usr_005 | Revenue Operations Specialist | Revenue Operations Manager | 0.64 | medium | |
| usr_006 | Analyst (generic, dept "Operations", notes mention a Sales transfer) | **none** | 0.25 | very_low | Correctly refuses to guess — see below |
| usr_007 | Lead (generic, Engineering, ML/SQL skills) | Engineering Manager | 0.41 | low | Explanation explicitly flags "the title alone was too generic to rely on" |
| usr_008 | *(empty profile)* | **none** | 0.00 | very_low | Correctly refuses to guess |

`usr_006` and `usr_008` are the assignment's explicit hard cases, and the
system does the thing the brief asks for: it's **honest about uncertainty**
instead of forcing a confident-sounding wrong answer. `usr_006`'s explanation
also surfaces the notes-vs-department conflict ("Transferred from Sales team"
vs. an Operations department) as negative evidence rather than silently
ignoring it or letting it dominate.

These are also the assertions in `tests/test_pipeline_golden.py` — banded,
not pinned to exact floats, so tuning a weight doesn't break the suite unless
it actually changes the decision.

---

## Signal engineering

| Signal | Weight (default) | Notes |
|---|---|---|
| Title | 0.32 | Highest-value, noisiest. Fuzzy-matched against role name + job family; generic titles (`"Lead"`, `"Analyst"` alone) are down-weighted 50%; vanity words (`"Ninja"`, `"Rockstar"`) are dropped to zero. |
| Department | 0.20 | Fuzzy-matched against the role's department. |
| Skills | 0.16 | Overlap coefficient against the role's declared skills. |
| Groups | 0.13 | Mapped through a curated group→function table (`tableau-users`→analytics, `aws-admins`→infra, `salesforce-admins`→revops/sales...) and compared to the role's classified function. |
| Manager title | 0.10 | Same function-classification approach, applied to the manager's title (not the manager's seniority — that would conflate the person with their boss). |
| Keywords | 0.05 | Free-text overlap (title + department + notes + manager title) against the role's declared `keywords`, including catalog abbreviations like `"bi"` that title-expansion would otherwise erase — see the bug note below. |
| Seniority | 0.02 | Extracted from a title ladder (intern→junior→mid→senior→staff→manager→director→vp→executive); this is what disambiguates "Data Analyst" from "Senior Data Analyst" when title/department/keywords are otherwise near-identical. |
| Location | 0.02 (defined, unused) | Collected but the catalog carries no location dimension to compare against — using it would just be noise. Kept as a config field for when location-aware roles exist. |

Weights are applied to **present, trusted signals only, and renormalized**
over whatever's actually available — a profile with just a title isn't
scored to zero on the missing signals, it's scored on what exists, with the
gap showing up as lower coverage (and therefore lower confidence) rather than
a punitive raw score.

**A real bug found and fixed during development:** the keyword-overlap signal
initially matched against an alphabetically-*sorted set* of words, so
multi-word catalog keywords (`"engineering manager"`, `"team lead"`,
`"people management"` on the Engineering Manager role) could never match —
sorting destroys phrase adjacency. Fixed by keeping a second, natural-order
text field specifically for phrase containment checks. Covered by
`test_keywords_overlap_matches_multi_word_catalog_keywords`.

---

## Confidence model

Confidence is a calibrated, decomposed number in `[0, 1]` — not the LLM's
self-reported certainty and not a raw match score.

```
raw = 0.35·S_top + 0.30·S_margin + 0.20·C_coverage + 0.15·A_agreement

confidence = raw × (1 − P_conflict) × (1 − P_missing) × (1 − P_stale)
```

- **S_top** — the winning candidate's fused score.
- **S_margin** — the gap between the top and second candidate (a wide margin
  means the deterministic layers already agree).
- **C_coverage** — fraction of the 7 reference signal categories actually
  present on this profile (independent of what they said).
- **A_agreement** — fraction of the winner's present signals that actually
  support it, vs. contradict it.
- **P_conflict** — penalty proportional to the *weight* of signals that
  contradict the winner (a title that agrees but a department that
  disagrees costs more than a low-weight keyword disagreeing).
- **P_missing** — flat penalty (0.4) when there's no title at all.
- **P_stale** — penalty (0.2) when the decision rests only on indirect
  evidence (manager/groups) with no direct title/department support.

### Bands

| Band | Range | Meaning |
|---|---|---|
| high | ≥ 0.85 | Strong, corroborated, no conflict |
| medium | 0.60–0.85 | Plausible, some gaps |
| low | 0.40–0.60 | Weak/conflicting — would go to a review queue in a real deployment |
| very_low | < 0.40 | **No role is assigned.** `inferred_role` is `null` and the explanation says so explicitly. |

Refusing to guess below `very_low` is deliberate, not a missing feature: a
confident-*wrong* answer silently grants the wrong downstream access; an
honest "insufficient data" doesn't. `usr_006` and `usr_008` exercise this
path in the golden tests.

All thresholds and weights live in `app/config.py` as one importable
`Settings` object — easy to find, easy to override in tests, and the natural
seam for making them per-tenant later.

---

## Data model and the override lifecycle

```
roles ──< inference_runs (immutable)
users ──< profiles (versioned, append-only)
      ──< overrides (append-only; reset deactivates, never deletes)
      ──  mapping (1:1, materialized "effective role" read model)
audit_logs (append-only, references everything by entity_type/entity_id)
```

- **Profiles, inference runs, and overrides are append-only.** The only row
  that ever gets *updated in place* is `Mapping` — a materialized projection
  that's always reconstructable from the tables above it.
- **Effective role = the active override's role, if one exists, else the
  latest inference run's chosen role.** An inference run is always computed
  and stored — *even while an override is active* — so the underlying model
  can be compared against the standing human decision over time (drift
  detection: if overrides keep getting set against what the model predicts,
  that's a signal the model or catalog is wrong, and you can only see that if
  inference keeps running underneath the override).
- **`pinned` has one specific behavioral effect:** `POST /reprocess` (bulk
  re-inference, standing in for a catalog/org-wide reprocessing event) skips
  users with an active *pinned* override entirely — their decision is a
  deliberate "don't touch." An active-but-unpinned override still gets a
  fresh `InferenceRun` on reprocess (for comparison), but still wins the
  effective role until explicitly reset.
- **Reset is idempotent** — deactivates the current override (if any) and
  reverts `Mapping` to the latest inference run, re-enabling automatic
  reprocessing.
- **Why overrides don't just overwrite the inferred role:** it would destroy
  the audit trail ("why did this person have this role on this date"),
  prevent drift detection, and make reset impossible to implement cleanly.
  Overrides *layer over* inference; they don't replace it.

Every mutating action (inference completing, an override being set or reset)
writes an `AuditLog` row: actor, action, before/after, reason, timestamp —
`GET /api/audit` and `GET /api/users/{id}/history` expose this.

---

## API reference

All routes are under `/api`. Interactive docs at `/docs`.

| Method & path | Purpose |
|---|---|
| `POST /api/profiles` | Ingest an SSO payload → new versioned `Profile` → synchronous inference |
| `POST /api/infer` | Force re-run inference for a user (`{"user_id": "..."}`) |
| `GET /api/users` | List all users with effective role, source, confidence |
| `GET /api/users/{id}` | Effective role + override status for one user |
| `GET /api/users/{id}/inference` | Full latest inference result (confidence, explanation, signals, alternatives) |
| `PATCH /api/users/{id}/override` | Set/pin an override (`role_id`, `pinned`, `reason`, `created_by`) |
| `DELETE /api/users/{id}/override` | Reset to inferred mode |
| `GET /api/users/{id}/history` | Timeline of inference runs + overrides |
| `GET /api/roles` | The Work Architecture catalog |
| `GET /api/audit` | Org-level audit log (optional `entity_type` filter) |
| `POST /api/reprocess` | Bulk re-infer all users, respecting pinned overrides by default |

Example (matches the assignment's example output shape, extended with
structured evidence fields):

```bash
curl -s http://127.0.0.1:8000/api/users/usr_001/inference | python3 -m json.tool
```
```json
{
  "inferred_role": "Senior Data Analyst",
  "role_id": "role_001",
  "confidence": 0.64,
  "band": "medium",
  "explanation": "Mapped to Senior Data Analyst (medium confidence, 0.64). Title and department jointly point to Senior Data Analyst.",
  "signals": ["Title 'senior business intelligence analyst' vs role name 'Senior Data Analyst' (similarity 0.58)", "..."],
  "alternative_roles": [
    { "role": "Data Analyst", "confidence": 0.67, "why_lost": "Weaker seniority match than Senior Data Analyst (0.20 vs 1.00)." }
  ],
  "signals_used": ["..."],
  "positive_evidence": ["..."],
  "negative_evidence": [],
  "missing_information": []
}
```

---

## Assumptions

- SSO payloads arrive in the canonical shape shown in the assignment (flat
  `title`/`department`/`manager_title`/`groups`/`skills`/`location`/`notes`),
  not raw Okta/Entra/Google API responses. `services/ingestion.py` is the
  named seam for a real per-provider adapter (`jobTitle` vs `profile.title`
  vs nested `organizations[]`) — currently a pass-through plus a `source`
  field, since building three real provider parsers wasn't the point of this
  exercise.
- Single tenant, single Work Architecture catalog, `catalog_version` is a
  flat integer rather than a full bitemporal `role_versions` table.
- Synchronous inference is fine at this dataset size; the service-layer
  function that runs it (`run_and_persist_inference`) is the exact seam a
  background worker would call at real scale.
- No auth/RBAC on the API — explicitly out of scope per the assignment.
- "Groups" and "manager title" function classification uses a small, hand-
  curated keyword table (`pipeline/vocabulary.py`), not embeddings — growing
  it from real override data is a natural active-learning loop, not
  implemented here.

## Known limitations

- Matching is lexical (fuzzy string + curated keyword tables), not semantic —
  a title using entirely different vocabulary than the catalog's keywords
  (with no corroborating department/skills/groups) will under-match. At
  catalog scale beyond a few hundred roles, this is where embeddings +
  vector search would earn their cost.
- Confidence weights and thresholds are hand-set from the reasoning in this
  README, not calibrated against a labeled dataset — there isn't one yet.
  See `eval/` for the seam.
- No authentication on the API or admin page.
- `POST /reprocess` runs synchronously in the request; fine for 8 users, not
  for 50,000.
- The LLM disambiguation stage's *fallback* path has been verified against a
  real OpenAI call (not just mocks): with a configured key, running inference
  for `usr_004` (the sample profile that escalates to stage 5) made 3 real
  network round-trips, each returning `insufficient_quota` (a billing issue on
  the test account, not a code error), and the pipeline correctly retried per
  `llm_max_retries` before falling back to the deterministic stub
  (`llm_degraded=true`) — landing on the same result documented above rather
  than crashing. The *success* path (a real 200 response feeding a genuine
  model disambiguation) still hasn't been exercised end-to-end — that needs
  quota on an OpenAI account, not a code change. The real-call parsing/
  validation logic is covered by mocked unit tests in
  `test_llm_disambiguate.py` either way.

## What I'd build next

1. **Calibration loop** — feed override outcomes back to recalibrate weights
   per tenant (Platt scaling against "did the admin agree with the model").
2. **Embeddings/hybrid search** for candidate generation once the catalog is
   large enough that brute-forcing every role stops being free.
3. **Event-driven reprocessing** — `ProfileUpdated`/`RoleCatalogUpdated`
   events on a queue instead of a synchronous bulk endpoint, so a catalog
   republish doesn't block on request/response.
4. **Multi-tenant config + RBAC** — per-tenant weights/thresholds (the
   `Settings` object is already shaped for this), auth on every route,
   strict tenant isolation at the data layer.
5. **PII minimization before the LLM call** — send normalized features
   instead of raw personal data where possible.
6. **Org-graph signals** — direct-reports count / peer roles for
   people-manager vs. IC disambiguation, and for corroborating genuinely
   sparse profiles (usr_008-style) via structural neighbors instead of
   refusing outright.

---

## Optional bonus: evaluation harness

`eval/labels.json` hand-labels an expected role for each of the 8 sample
users — including an explicit "no correct answer, should abstain" label for
the three hard cases. `eval/eval.py` runs the real pipeline against them and
reports two metrics (not just accuracy, since this system is *expected* to
abstain sometimes):

```bash
python eval/eval.py
```

```
Resolved-case accuracy:   5/5 (100%)
Correct-abstention rate:  2/3 (67%)
```

The one "miss" is worth being honest about rather than papering over:
`usr_007` ("Lead" in Engineering, ML/SQL skills) is labeled "should abstain,"
but the pipeline actually returns a **low-confidence guess** (Engineering
Manager, band `low`) with the explanation explicitly flagging "the title
alone was too generic to rely on." That's arguably *correct* behavior — low
confidence + a clear caveat is a legitimate outcome for a genuinely
borderline case, not the same failure mode as a confident wrong answer — but
this harness's binary abstain/resolve framing is too coarse to give it
partial credit. A real version of this harness would score bands/ranges the
way the golden pipeline tests do, not a single hand-picked "expected" role.

This is real signal on a 3-case ambiguous set, not a rigorous eval — the
production version described in "What I'd build next" (calibration against
actual override outcomes) is what this would need to become trustworthy at
scale.

---

## Optional bonus: schema migrations (Alembic)

The assignment explicitly names "schema migration strategy" as a production
concern for a system whose own data model expects to evolve (`catalog_version`
bumps, new columns as overrides/audit needs grow). Previously, `init_db()`
just called `Base.metadata.create_all(bind=engine)` on every app boot — fine
for a fresh SQLite file, but with no way to evolve an existing database's
schema without a manual, undocumented `ALTER TABLE`.

`app/db.py::init_db()` now runs `alembic upgrade head` programmatically
instead, so both `uvicorn app.main:app` and `python scripts/seed.py` exercise
the same migration path a real deployment would:

```bash
# after changing a model in app/models/tables.py:
alembic revision --autogenerate -m "describe the change"
# inspect the generated file in migrations/versions/ before committing --
# autogenerate is a good first draft, not a guarantee
alembic upgrade head        # applied automatically on next app/seed startup anyway
```

`migrations/env.py` pulls both the target metadata (`Base.metadata`, via
`app/models/tables.py`) and the connection string (`settings.database_url`)
directly from the app's own config — `alembic.ini` intentionally carries no
`sqlalchemy.url`, so there is exactly one source of truth for which database
is in play, not two configs that can drift apart.

**Deliberate exception:** `tests/test_api.py` still calls
`Base.metadata.create_all` directly against a per-test throwaway SQLite file,
bypassing Alembic entirely. Ephemeral test databases have no migration
history worth managing — building the current schema directly is faster and
keeps 69 tests hermetic and independent of migration state. Alembic governs
the one database that actually persists and evolves over time (`role_inference.db`
in dev; whatever's configured via `DATABASE_URL` in a real deployment).

The baseline migration (`migrations/versions/..._initial_schema.py`) was
autogenerated against an empty database and verified to reflect all 7 tables
in `app/models/tables.py` exactly (columns, nullability, foreign keys,
indexes) with no manual edits needed.

---

## AI tooling used

This was built end-to-end with **Claude Code** (Sonnet 5), working
stage-by-stage rather than one large generation pass — deliberately mirroring
the "don't dump everything into one prompt" principle the pipeline itself is
built around.

**Workflow:** plan mode first (explore the assignment + an internal
architecture-notes doc, ask clarifying questions about stack/LLM
provider/admin-UI shape, write a scoped-down implementation plan), then
implement commit-by-commit — data model, pipeline stages 1–4, stages 5–8,
services/API, admin page, seed script, docs — running the real test suite
and a live server after each stage rather than trusting generated code
on faith.

**Where it was genuinely helpful:**
- Scaffolding repetitive-but-precise code (SQLAlchemy tables next to Pydantic
  DTOs, FastAPI routers, the confidence-formula implementation) correctly on
  the first pass once the design was pinned down.
- Writing the golden-case test suite *after* actually running the pipeline
  against all 8 sample users and observing real output, rather than guessing
  expected scores up front — this caught the assumption-vs-reality gap
  early instead of shipping brittle tests.
- Catching its own bug: while writing the keyword-overlap tests, it noticed
  role_010's multi-word catalog keywords (`"engineering manager"`) could
  never match against an alphabetized word set, root-caused it (sorting
  destroys phrase order), and fixed it with a second natural-order text
  field — verified by rerunning the full sample-user diagnostic before and
  after.
- End-to-end verification: rather than asserting the admin page worked from
  reading the HTML, it installed Playwright, drove a real headless browser
  against the live server (list rendering, expanding an explanation,
  setting and resetting an override), and only then called it done.

**Where it required correction / was steered:**
- The first draft of `_stub_result()` in the LLM fallback path would have
  crashed on an empty shortlist (`shortlist[0]` with no guard) — caught by
  writing the edge-case test *before* assuming the happy-path code was
  correct, not caught by the implementation itself.
- Left several architectural judgment calls to explicit human decisions
  rather than silently picking one: LLM provider (OpenAI vs. Anthropic vs.
  none), admin UI shape (static page vs. CLI vs. API-only), and where
  exactly `pinned` should behaviorally matter in the override/reprocess
  interaction — these were resolved via clarifying questions before writing
  code, not guessed.

**Validation strategy:** every pipeline stage has isolated unit tests; the
full pipeline is regression-tested against all 8 real sample users with
band-based (not exact-float) assertions; the API is tested against an
isolated per-test SQLite database through the full
ingest→infer→override→reprocess→reset lifecycle; the admin page was driven
in an actual headless browser, not just read. 69 automated tests, all
offline. Nothing in this repo is "trust me, the AI wrote it" — every claim
above is something that was actually run and observed, not assumed.
