# Repository review and development guide

Reviewed: 24 October 2026. Baseline commit: `8229e8a`.

This review separates source implementation, executable checks, and full integration verification. A model, route, or screen existing does not establish that its workflow works. The README's approximate completion percentage is not a verified readiness measure.

## Purpose and architecture

CareBridge is intended to support patients booking doctors, joining remote consultations, exchanging messages, accessing records and prescriptions, and uploading medical documents. Doctors have a separate workspace for their queue, patients, clinical history, consultations, and prescriptions. Administrators use Django admin and audit APIs.

| Layer | Implementation |
| --- | --- |
| Patient website | Next.js 14, React, TypeScript, Tailwind; port 3000 |
| Doctor website | React, Vite, TypeScript; port 3001 |
| REST backend | Django 5.0, DRF, Simple JWT; port 8000 |
| Realtime transport | Express, Socket.io, JWT verification, signaling handlers; port 3002 |
| Persistence | PostgreSQL; Redis for caching/broker and optional chat publication |
| Background work | Celery worker and beat |
| Local orchestration | Docker Compose with eight services |

## Feature inventory

| Feature | Exists in source | Remaining work / defects |
| --- | --- | --- |
| Registration/login | Backend endpoints and patient forms; doctor login strip; local patient API helper | Patient helpers are ignored/untracked by Git; safe profile writes, role enforcement, refresh/logout behavior and meaningful tests need attention |
| Profiles | User, doctor, patient medical information models; profile GET/PATCH | PUT follows a different update path and exposes account fields; nested PATCH saves are not atomic |
| Doctor onboarding | Doctor registration accepts specialization and license number | Verification/approval is not enforced before doctor privileges or directory visibility |
| Patient directory | Doctor/admin list and detail APIs; doctor patient list | Doctor filtering is explicitly unfinished, exposing unrelated patients and medical information |
| Appointments | CRUD, status actions, overlap query, weekly availability model, patient booking form | Required patient field disagrees with patient form; slots, past times, availability/duration rules, timezone conversion, concurrency and state/ownership protections are incomplete |
| Doctor queue | Basic appointment list | Confirm/cancel/complete controls and actual date filtering for "Today's queue" are absent; only first result page is displayed |
| Consultations | Models, CRUD, room IDs, start/end, message API; consultation screens | Appointment ownership checks and field/lifecycle restrictions incomplete; creation/join workflow disconnected; both websites fall back to `demo` |
| Video | Decorative components and server signaling forwards | No media capture, peer connection, offer/answer handling, media rendering, working controls, or TURN configuration in either frontend |
| Chat | Socket handlers, frontend components, last 100 messages per room in a process-local Map; separate Django message API | No room authorization; socket chat never calls Django persistence; history lost at restart; no Redis adapter/subscription bridges nodes; reconnect and failure handling incomplete |
| Clinical records | Backend models/CRUD; doctor history titles | Patient can update/delete their own clinical records through inherited routes; relationship validation and author protections missing; patient record browser absent |
| Prescriptions | Backend nested medication items; minimal doctor form | Form omits required doctor field; patients can update/delete their own prescriptions; editable dosage/frequency/duration, patient prescription views, and atomic writes needed |
| Documents | FileField upload API, metadata/hash, encryption helper functions | Encryption helpers are unused by upload/download; no authenticated download endpoint; DEBUG media serves files directly; file validation and record/patient consistency missing; document UI absent |
| Audit | Middleware, log model, admin-only read API, Django admin registration | Failures silently discarded; patient directory reads omitted; actor/action/resource detail and tamper/retention behavior need validation |
| Notifications/jobs | Reminder/email/cleanup/expiry task functions | Verification/reset endpoints and screens absent; welcome/verification tasks unwired; missing scheduled audit task; stale consultation/expiry jobs unscheduled; reminders lack deduplication |
| Two-factor authentication | Settings model only | No setup, verification, recovery, or login challenge flow |
| Operations/testing | Dockerfiles, Compose, health routes, initial migrations | No committed automated test cases or CI; frontend test scripts only echo messages; no dependency lockfiles; deployment and end-to-end verification outstanding |

## Findings to address first

### 1. Account role escalation through profile PUT — critical, reproduced through the API

`backend/apps/users/views.py:172` inherits `RetrieveUpdateAPIView`. Only PATCH is customized. PUT uses `UserSerializer`, whose writable fields include `role` and `is_active` (`backend/apps/users/serializers.py:53`). An authenticated patient can submit their email and `role: admin` to the inherited PUT path. Authorization throughout the backend trusts `user.role`, so application administrator access does not require Django's `is_staff` flag.

An isolated APIClient probe returned HTTP 200 and the stored patient role became `admin`. Fix the write contract, explicitly protect account-controlled fields on every supported method, and add an API regression proving stored role/flags cannot change. Do not merely hide role selection in a form. Decide and document whether PUT is supported or returns 405.

### 2. Realtime room access is unauthenticated and unscoped — confirmed by executable handler probes

`realtime-service/src/auth/middleware.js` accepts missing tokens as guests and accepts signed refresh tokens because token type is unchecked. `src/websocket/handler.js` joins any supplied room. `src/chat/service.js` exposes history and broadcasts messages without membership checks. `src/webrtc/signaling.js` similarly forwards arbitrary room events.

Synthetic executable probes returned true for all five conditions: anonymous connection accepted; refresh token accepted; guest joined arbitrary room; nonmember broadcast a message; nonmember read room history. These probes called the actual handlers with test socket objects; they are not a full browser/network test.

Require valid access tokens, resolve the current active user and consultation membership against the backend, and enforce authorization on every event. Validate event payloads and rate limits. A room UUID is not authorization.

### 3. Clinical write permissions and cross-patient references — high, reproduced through the API

`backend/apps/medical_records/views.py` restricts only record/prescription creation and the custom prescription cancellation action. Inherited PUT/PATCH/DELETE still permit patients who can read an object to modify/delete it. Serializers expose author, patient, consultation and status fields. A patient can also change appointment status through generic updates, bypassing the doctor-only confirmation/completion actions.

`PatientViewSet.get_queryset()` contains an explicit `pass` where doctor-to-patient scoping should be. Consultation creation accepts an appointment object without verifying the caller participates in that appointment. API probes returned 200 for patient edits to a clinical record and prescription, 200 for patient self-confirmation through appointment PATCH, and 201 for creating a consultation for another patient's appointment. The directory probe returned 200 for a doctor's access to an unrelated patient. Scope related-object fields as well as list querysets; reject reassignment and invalid state transitions.

### 4. Frontend delivery is not reproducible from Git

The patient portal imports `@/lib/api` from four pages and `@/lib/websocket` from its consultation page. Both modules exist locally, but neither is tracked by Git: `.gitignore:13` contains `lib/`, which excludes `patient-portal/src/lib/`. A clean clone therefore loses both helpers and cannot resolve those imports. The local registration helper correctly adds `role: patient` and password confirmation. Preserve these files and narrow the ignore rule before relying on reproducible frontend builds.

The patient production build passes in this local working copy, including these ignored helpers. The doctor build produced three TypeScript errors: missing `ImportMeta.env` declarations in both service modules, and a useEffect cleanup returning `Socket` rather than void in `src/pages/Consultation.tsx:17`.

### 5. Browser/API request contracts disagree

The appointment serializer requires `patient`, but the patient form sends only doctor, dates, reason and symptoms. Injecting the patient in `perform_create()` happens after serializer validation, so it does not resolve this mismatch. The prescription serializer similarly requires `doctor`, while the doctor's form omits it and the view injects it too late. Both frontend-shaped request probes returned HTTP 400 with the corresponding missing-field error. Make ownership fields request-aware and server-controlled, then test the exact frontend payloads.

### 6. Compose environment forwarding is incomplete

Compose reads the root `.env` for interpolation; it does not automatically pass every variable into containers. Backend and Celery only receive the listed database/cache settings, while realtime receives the interpolated `JWT_SECRET_KEY`. Copying `.env.example` therefore gives realtime a different JWT secret from the backend's default signing key. Django secret/debug/security/email/CORS overrides are also not forwarded. Docker is unavailable in this review environment, so this is a configuration finding rather than a container-run result.

### 7. Background scheduling and storage claims exceed implementation

`backend/config/celery.py:31` schedules `apps.audit.tasks.generate_daily_reports`, which does not exist; the module defines `summarize_recent_audit_activity`. Expiry and stale-consultation tasks exist but have no beat schedule. Socket Redis publication has no matching subscription or adapter. Uploaded medical files are hashed, not encrypted by the actual workflow.

`docs/SECURITY.md` contains illustrative designs and checked compliance claims that are not established by the source. Treat these as intended requirements until independently verified, and replace completion claims with evidence as work proceeds.

### 8. Default cache configuration fails with installed dependencies — reproduced

The manifests resolved `redis==8.1.0` and `django-redis==6.0.0`. `backend/config/settings.py:205` configures `redis.connection.HiredisParser`, which is absent. A direct call to `cache.set()` raised `ImportError: Module "redis.connection" does not define a "HiredisParser" attribute/class` before any Redis connection attempt. This also affects normal DRF throttling and cached sessions. Fix the supported parser configuration and pin/test compatible dependencies; Django's system check does not catch this.

### 9. Models and committed migrations have drifted — reproduced

On the isolated SQLite database, all committed migrations applied, but `makemigrations --check --dry-run` exited 1. It proposes index renames in all five local apps and alterations to the custom user's inherited auth fields. Reconcile these deliberately rather than treating a successful initial migration as a clean schema baseline. No migration files were generated during review.

## Verification and limitations

- All 62 Python source files parsed successfully; backend compileall passed.
- Syntax checks passed for all six realtime JavaScript source files.
- Realtime `node --test` reported **zero tests**.
- Doctor dependencies installed; `npm run build` failed with the three TypeScript errors above.
- Realtime dependency installation succeeded; handler probes confirmed the five access-control failures listed above.
- Python requirements installed into the ignored local `venv/`; Django 5.0.14 and DRF 3.17.2 were resolved. The available host is Python 3.13; Docker specifies Python 3.11, which was not available for verification.
- Django `manage.py check` exited 0 with one warning: the configured `backend/static` directory does not exist. `manage.py test` found and ran **zero tests**.
- All committed migrations applied to an in-memory SQLite database. Model/migration drift check failed as described above.
- Backend APIClient probes used synthetic fixtures, an in-memory SQLite database, a local-memory cache, and `force_authenticate` to isolate role/serializer behavior. They reproduced the permission failures and request-contract errors above; they do not establish JWT, PostgreSQL, Redis, or deployment integration correctness.
- The default Redis cache probe failed with the parser ImportError above. The API probes intentionally used a working isolated cache so this startup/configuration defect could not mask authorization defects.
- Patient `tsc --noEmit --incremental false` and `npm run build` passed. An interrupted initial dependency installation left the bundled `lucide-react` declaration missing; it was restored from the identical installed 0.468.0 package in the doctor workspace before rerunning. This repair changed generated `node_modules` only. The first failed patient build is therefore not attributed to application source.
- The two patient helper files exist locally; their exclusion from Git is confirmed by both `git ls-files` and `git check-ignore -v`.
- Docker is not installed/available on PATH. PostgreSQL, Redis, Celery, browser workflows, two-party media, encryption recovery, concurrency and production deployment have not been verified end to end.
- Dependency installs used the existing manifests. No dependency vulnerability audit or compliance assessment was performed.
- No application source was modified. This review adds only this document; dependency directories, build outputs and synthetic runtime logs are ignored by Git.

## Development sequence and review rule

Work in small changes and issue only one implementation prompt at a time. Suggested sequence:

1. Safe account/profile access: stop role escalation and protect account fields; establish backend regression tests.
2. Runtime/build baseline: fix the Redis parser, reconcile migration drift, track the existing ignored patient clients, repair doctor TypeScript errors and verify Compose environment forwarding; then patient/doctor session flows.
3. Patient/clinical data authorization across directories, CRUD and related-object references.
4. Appointment booking and availability: exact payload, slots, timezone, conflicts, states and concurrent requests.
5. Consultation lifecycle and authorized room entry, using real consultation identifiers.
6. Authenticated persistent chat, followed by real WebRTC media and controls.
7. Record and prescription workflows, including complete doctor editors and patient read views.
8. Validated private document storage and encrypted upload/download.
9. Reliable reminders, background schedules, audit visibility, operational checks and accurate documentation.

Doctor approval, email verification, password recovery and 2FA should each get their own bounded prompt once the core access/session flow is stable. Keep external deployment and real patient data gated on the security and integration work.

For each change, review the actual diff, run relevant positive and negative tests, and report PASS / NEEDS CHANGES with evidence. A generated walkthrough or an exit-zero placeholder test script is not acceptance evidence. Preserve existing work, avoid unrelated redesign, and document checks blocked by the environment.
