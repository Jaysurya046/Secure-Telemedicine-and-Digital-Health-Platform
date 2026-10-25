# Consultations and secure messaging

A confirmed appointment can open its existing consultation or create one. Both portals use the consultation ID for REST and its separate `room_id` for sockets. The doctor starts a scheduled consultation and completes an in-progress consultation with validated clinical fields. Patients see clinical information read-only. Video capture/media remains a separate module.

## API and messaging contract

- `GET /api/consultations/identity/` returns the current authenticated active user's ID, role and email. Unsupported roles are forbidden.
- `GET /api/consultations/?appointment=<id>` and `?room_id=<uuid>` retain participant/admin queryset scoping.
- `GET /api/consultations/<id>/messages/?page=1&page_size=50` returns canonical persisted history, newest first, ordered by timestamp and ID. Maximum page size is 200. Consultation details no longer embed the entire message history.
- `POST` to the same messages URL accepts only `message` (nonblank string, at most 2000 characters) and optional `client_msg_id` (string, at most 64 characters). Sender, IDs and timestamps come from Django.
- A nonblank retry key is unique per consultation and sender, protected by a database constraint and consultation transaction lock. Same key/content returns the original message; different content returns 409. Blank keys intentionally do not deduplicate.
- Scheduled and in-progress consultations allow messages. Completed/cancelled consultations allow reads and retries of an already persisted identical message, but reject new messages with 409.

## Realtime contract

The service requires `DJANGO_API_URL` (Compose configures `http://backend:8000`) and the shared JWT signing configuration. Only unexpired access tokens with identity and expiration are accepted. Django verifies current user identity and supported roles; identity in JWT role/email claims is not trusted. Established sockets disconnect at token expiration.

Every join, history request, message and signaling event checks Django membership without an authorization cache. Presence is restricted to joined rooms. Recipients are rechecked before delivery, so removed or inactive participants cannot retain access through a previous join. Django outages fail closed.

Clients join with `consultation:join {roomId}` and wait for `consultation:joined`. `chat:message {roomId, message, clientMsgId}` is persisted through the sender's own Django token before broadcast. `chat:ack {clientMsgId, messageId, sentAt}` acknowledges persistence. Retry the same key after lost acknowledgements. `chat:error` includes an error code/message and the retry key when supplied. REST history and socket delivery identify the same database rows.

History initially loads one page; earlier pages load on demand. Reconnect recovery fetches all pages and merges by canonical ID. Pending messages retain their retry keys. Sign-out unmounts consultation state and disconnects sockets. Existing WebRTC signaling is checked for membership, joined-room access and in-progress status; this module does not implement media transport.

Realtime broadcasts currently run on a single Socket.IO process. Connecting Redis does not provide a distributed Socket.IO adapter. Multi-instance fanout and load testing are not verified here.

## Migration and verification

Apply the new consultation migration with the backend's normal `python manage.py migrate` deployment step. No developer/production database was migrated during implementation verification.

Run the four backend suites with `--settings=config.test_settings`, then `makemigrations --check --dry-run` and `check`. Run `npm test` and `npm run build` in each portal. Run `npm test` in `realtime-service` with repository Python dependencies installed in `venv` and local loopback networking permitted.

Realtime integration tests start a disposable Django HTTP server and temporary SQLite database and use the production Socket.IO handlers. They exercise actual JWT authorization, scoped history, persistence, retries, cross-user denials, malformed events, membership/account revocation, reconnect recovery, outage handling and session expiry. Rendered-component tests cover doctor clinical actions, patient read-only access, appointment entry, pagination, retries and socket cleanup. PostgreSQL row-lock contention and live Redis integration remain separate infrastructure checks.
