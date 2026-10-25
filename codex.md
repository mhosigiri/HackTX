# Tell Me More — backend implementation task

You are working in the local `Hacktx` working folder. Claude owns the frontend. Another teammate owns the main heirloom/object-story AI feature. Your assignment is to finish the supporting backend required by the documented workflows, continuing from the verified current state. Work carefully, in small validated slices. Do not rebuild completed features.

## 1. Read and establish the actual state before editing

1. Locate the correct Hacktx project root. Read applicable AGENTS.md instructions, README.md (case-insensitive filename discovery), `docs/DESIGN.md`, every Markdown file recursively under `goals/`, and the workflow document named `family object stories.md` (discover spelling/case variants). Read linked specifications needed to understand the backend. If a required document cannot be found, report the exact missing item; do not invent its contents.
2. Inspect git status/diffs, backend routes, Pydantic models, services, authentication, jobs, tests, all migrations, and generated API contracts. Read frontend consumers only to understand contracts; do not implement frontend changes.
3. Reconcile documentation against actual code and applied migrations. Treat the baseline below as the last reported status, not proof that this checkout or database is identical. Preserve newer completed work you discover.
4. Produce a compact requirement matrix: workflow, existing backend support, missing support, owner, relevant files, and acceptance checks. Explicitly identify the teammate-owned main-feature boundary before editing. If ownership is ambiguous, leave those paths untouched and ask a targeted question while continuing independent supporting work.
5. Write down a short implementation sequence, then execute the first independently safe supporting slice. Do not stop at a plan when implementation is possible. Track verified completion and blockers as work proceeds.

## 2. Architecture to preserve

- Project/product: **Tell Me More**, interface brand `tell me more`.
- `frontend/`: Vite + React + TypeScript + Tailwind, owned by Claude.
- `backend/`: FastAPI, Python 3.12, uv. Existing single process serves API and runs job worker.
- `supabase/migrations/`: Postgres schema, RLS, Realtime publication, storage buckets.
- `frontend/src/api-types.ts` is generated. Never edit it manually; run `make types` after contract changes. This generated file is the only routine frontend write permitted for this assignment.
- Model calls belong exclusively in `app/providers`; prompts in `backend/app/prompts/*.md`. Preserve `LLM_PROVIDER` / `VISION_PROVIDER` behavior.
- Follow existing route, dependency injection, database access, error, logging, and testing conventions. Do not introduce a second architecture.

## 3. Protected work and collaboration

The main feature is photographing an heirloom, analyzing/identifying it, asking a relative questions, recording/transcribing their story, and generating the cited story result. The teammate owns its pipeline and associated orchestration/contracts.

- Treat `backend/app/jobs/stages/`, AI providers, prompts, interview/transcription/question generation, object analysis/Lens integration, story synthesis/citations, and their worker orchestration as protected by default. Read them for integration context, but do not implement, replace, or refactor them.
- Earlier README status said stages 1–4 (`analyze_object`, `lens_lookup`, `transcribe_turn`, `next_question`) were implemented/tested and stages 5–8 were stubs. Verify present status; do not fill stubs simply because they exist.
- Supporting memories/media routes may overlap with the main story feature. Define ownership from the documents and actual code; do not create a competing story pipeline or duplicate tables.
- Preserve unrelated/uncommitted edits. Recheck affected files before editing in a shared working tree. Do not revert others' work, perform broad formatting, or change shared contracts silently.
- No frontend UI implementation. Supply precise API integration notes for Claude instead.

## 4. Verified baseline supplied by the owner

### Authentication and initial screens

Screens 01–04 plus sign-in are complete: welcome, create account, onboarding, Home. Account preferences support light/dark and logout. Supabase Auth manages sessions. `PATCH /api/profile` saves name/age; backend chooses display mode from age. Incomplete onboarding redirects appropriately; protected pages require authentication.

Profile currently exposes `display_name`, `age`, `ui_mode`. Spoken language was device-local under `tmm-language`; interviews already accepted a language. Do not add a language column unless current documented supporting requirements justify it.

### Screens 21–23: family setup/tree/invitations — complete

Reported applied migration: **`20261025061842`** on the **TellmeMore** project. Do not replay or edit an applied migration. Verify migration history before adding anything.

- Family creation persists after refresh; current user is identified as `me`; relationships and member details work.
- Invitations specify recipient relative to an anchor: recipient parent means recipient is anchor's parent. Pending invitations are separate from accepted relationships.
- No invitation email is sent. Inviter shares a link; copy failure exposes selectable link text.
- Invitation destination survives sign-out/sign-in/onboarding within the same browser.
- Acceptance creates membership/person/relationship atomically and correctly directed. Repeated acceptance returns the same result without duplicates.
- Accepted invitations cannot be declined; declined invitations cannot be accepted.
- Wrong accounts cannot read invitation details or act on someone else's invitation.
- Nonmembers cannot read tree/list or create invitations; Supabase RLS hides invitation and relationship rows.
- Duplicate pending invitations and self-invitations are rejected.
- Browser and live backend checks used three accounts. Reported checks: 53 backend tests including 12 invitation tests passed; ruff clean; frontend typecheck/lint passed except existing fast-refresh warnings in auth/display-mode providers.
- Docker was unavailable; tests ran against embedded Postgres 16 with migrations applied. Preserve a reproducible isolated test setup; do not claim Docker validation.

### Known limitations, not permission for unrelated rewrites

- Users can belong to multiple families, but the frontend showed only the first. Preserve multiple memberships. Ensure backend membership listing/scoping supports all families; leave the selector UI to Claude. Avoid a database `active_family` field when request-level family selection suffices.
- Legacy `POST /api/families/join` adds membership without a tree position. Inspect its authorization and compatibility impact. Do not silently delete it or change behavior; document a minimal safe resolution if needed.
- Invitation context in local storage does not transfer to another device through confirmation email. Supabase Site URL/redirect configuration still needs verification. Do not claim cross-device resume works or redesign auth without an explicit requirement.
- Test fixtures/accounts and a verification family remain in the development project. Do not remove them, expose their credentials, or copy passwords into source/docs/logs. Use isolated test fixtures for new tests.

## 5. Supporting backend scope and order

Determine exact requirements from the workflow/goals documents. The following is sequencing guidance, not an invented endpoint/schema specification:

1. Confirm multi-family membership listing and strict family-scoped access; fix necessary supporting gaps without breaking completed invitations.
2. Important dates (screens 17–20): calendar range retrieval, event details/create/update/delete, supported family-person associations, annual repeats, permissions. Store all-day values as dates; store timed instants with explicit timezone semantics. Define February 29 recurrence. Bound calendar queries; do not materialize unlimited repeated occurrences.
3. Family availability/private schedules (29–32): owners manage private busy periods, timezone, supported repeats, sharing preference, and temporary override with expiry. Accepted authorized relatives see only current free/busy/not-shared status, never titles, notes, schedule rows, or future busy intervals. Enforce this distinction in backend responses AND direct database/RLS access. Derive status at request time unless proven otherwise; do not store status every minute or add a scheduler process for a computable result.
4. Family memories (24–28): only the supporting CRUD/media/metadata/visibility responsibilities confirmed outside the teammate's pipeline. Reuse existing storage and story entities where semantically correct. Do not implement AI narration or synthesis.
5. Timeline (33): prefer a bounded projection of authorized existing events/stories/memories; avoid copying all source content into a second timeline database. Return source references and stable ordering.
6. Notifications (34) and preferences (35): implement only documented MVP requirements; reuse existing notification infrastructure and supported Realtime mechanisms. Do not invent email/push delivery, queues, or third-party integrations.

For each slice, define a concise contract and schema rationale, implement it, test it, regenerate types, and document frontend handoff. Do not create tables for every screen. If a scope item depends on protected work, record the dependency and continue independent items.

## 6. Database restraint and migration discipline

- Before adding a table/column/index, identify the requirement, existing alternatives, ownership, read/write patterns, constraints, and deletion behavior. Use the smallest coherent normalized schema.
- Reuse existing user/person/family/member/media entities; avoid parallel identity, membership, story, calendar, or notification systems. Do not conflate account identity with a family-specific person when the existing model distinguishes them.
- Store binary media in existing object storage, not base64 blobs in Postgres. Keep references and necessary metadata in rows; use private access/signed URLs as appropriate.
- Avoid speculative abstractions, generic entity-attribute-value tables, giant unvalidated JSON blobs, excessive audit/event tables, and duplicate derived state. JSONB must have a concrete bounded purpose and validation.
- Enforce integrity in Postgres with appropriate foreign keys, unique/check constraints, and explicit delete behavior; use concurrency-safe transactions for multi-row mutations. Do not rely only on a read-before-write check.
- Index actual authorization/filter/join paths; avoid redundant indexes and indexing every column. Bound lists, date windows, uploads, and request sizes; avoid N+1 queries and unbounded selects.
- Add new forward-only migrations with unique versions. Never rewrite applied migration `20261025061842` or the initialization migration. Test fresh installation AND upgrades from the current baseline.
- Develop and verify migrations on an isolated database. This task authorizes local code/migration preparation, not applying new migrations to the shared/live TellmeMore project. Present the exact reviewed migration and target for explicit authorization before remote application. Never reset/drop/truncate a shared database or use live user data as disposable test data.

## 7. Backend guardrails

- Authenticate using the existing verified Supabase token path. Never trust client-supplied user IDs, email, family membership, or roles as authorization evidence.
- Validate access to every resource and nested foreign ID, including storage objects and linked people. Family ID in a URL is a scope identifier, not permission. Test cross-family attacks.
- Enable appropriate RLS for every new exposed table. Elevated/service-role database access bypasses RLS: enforce authorization explicitly in backend code and test direct authenticated database access separately.
- Private schedules are owner-only. Derived availability is a narrow authorized response; do not grant relatives SELECT on schedule rows to compute it client-side.
- Use parameterized queries, explicit request/response models, allowlisted updates, consistent status codes, and safe errors. Avoid mass assignment and returning raw database rows or internal tracebacks.
- Preserve existing verified-email rules for invitations. Use atomic state transitions/idempotency where retries can duplicate data. Validate relationship direction and family-local anchors.
- Keep secrets server-side and out of git, tests, generated contracts, reports, and logs. Do not print env contents, auth tokens, private transcripts, full schedules, or signed media URLs.
- Use the existing dependency stack. Do not add Redis, Celery, another worker/service, ORM replacement, microservices, or broad architectural rewrites without a demonstrated requirement and owner agreement.
- No blanket exception swallowing, fake success, hardcoded sample users, disabled authorization, permissive RLS/CORS workarounds, or TODO stubs presented as implemented features.
- Keep expensive I/O out of blocking async paths using existing conventions. Apply existing timeout/upload protections where relevant. Do not build speculative infrastructure.

## 8. Validation and completion

For every implemented slice:

1. Add meaningful tests using existing fixtures/fake providers and isolated Postgres. Cover positive flows, unauthorized and cross-family access, invalid inputs, persistence, constraints, relevant retries/concurrency, and transaction rollback.
2. For scheduling/calendar code, test timezones, day/month/year boundaries, recurrence bounds, override expiry, and private-data non-disclosure.
3. Run relevant tests, backend lint/ruff, and `make types`. Run the full backend suite before handoff; investigate regressions rather than weakening tests. Run frontend typecheck to verify generated contract compatibility without changing UI code.
4. Use existing documented commands (`make lint`, `make test`, `make check`) only as appropriate. Inspect live-check behavior before running; real-key/live-write checks require a designated development target and authorized data. If Docker or another dependency is missing, report the actual alternative and limitations.
5. Record exact commands/results, changed files, migrations prepared/applied, new contracts, permissions, and remaining blockers. Distinguish local tests from live verification. Never claim a browser flow was tested without testing it.
6. Provide Claude a concise contract handoff: methods/paths, authentication, request/response shapes, pagination/date semantics, errors, permissions, and small synthetic examples. Clearly mark unavailable/protected functionality.

## 9. Git and delivery restrictions

**Do not push to any repository.** Do not open PRs, merge, publish, deploy, force-push, change remotes, or perform remote writes. Do not commit unless separately asked. No destructive git commands or automatic stashing of others' changes. Leave reviewable local changes with a clear final summary.

Begin by reading the project documents and auditing the current baseline. Continue supporting backend implementation from the first genuinely missing requirement; do not redo authentication or screens 21–23, and do not take over the teammate's main feature.
