# Secure Telemedicine and Digital Health Platform

A full-stack telemedicine platform scaffold for patient booking, doctor workflows, secure clinical records, realtime consultation rooms, and administrative audit visibility.

Last updated: 2026-06-14

## Current State

The repository now contains a functional multi-service implementation scaffold, not just a backend starter. The Django domain apps, migrations, Docker orchestration, realtime Socket.io service, patient portal, and doctor dashboard are present. The remaining work is mainly dependency installation, full runtime verification, automated tests, production security hardening, and deployment configuration.

## Architecture

```text
Patient Portal (Next.js, port 3000)
        |
        | REST API
        v
Django Backend (DRF, port 8000) ---- PostgreSQL
        |                              Redis
        | Celery worker/beat
        |
Doctor Dashboard (Vite React, port 3001)

Patient Portal / Doctor Dashboard
        |
        | Socket.io / WebRTC signaling
        v
Realtime Service (Node.js, port 3002) ---- Redis
```

## Services

- `backend/`: Django 5, Django REST Framework, Simple JWT, Celery, Redis cache/session support, PostgreSQL models, and Swagger/ReDoc API docs.
- `realtime-service/`: Express and Socket.io service with JWT-aware socket authentication, consultation rooms, presence, chat, and WebRTC signaling.
- `patient-portal/`: Next.js 14 patient workspace with login, registration, dashboard, appointment booking, consultation room, video, and chat components.
- `doctor-dashboard/`: Vite React doctor workspace with login strip, appointment queue, patient list, patient history, prescription form, consultation room, and realtime service clients.
- `docker-compose.yml`: Local orchestration for PostgreSQL, Redis, backend, Celery worker, Celery beat, realtime service, patient portal, and doctor dashboard.

## Implemented Backend Domains

- Users and profiles: email login, patient/doctor/admin roles, profile data, doctor profiles, patient medical info, two-factor settings model.
- Appointments: appointment scheduling, doctor availability windows, role-filtered access, confirm/cancel/complete actions.
- Consultations: consultation sessions, room IDs, lifecycle actions, persisted messages.
- Medical records: records, prescriptions, prescription line items, medical document metadata, file hashing, encryption helper utilities.
- Audit: audit log model, middleware, admin registration, read-only admin API.
- Background jobs: task modules for user email flows, appointment reminders, consultation cleanup, prescription expiry, and audit summaries.

## Main Local URLs

- Patient portal: http://localhost:3000
- Doctor dashboard: http://localhost:3001
- Backend API: http://localhost:8000/api/
- API docs: http://localhost:8000/api/docs/
- ReDoc: http://localhost:8000/api/redoc/
- Django admin: http://localhost:8000/admin/
- Backend health: http://localhost:8000/health/
- Realtime health: http://localhost:3002/health

## Quick Start

```bash
cp .env.example .env
docker-compose up -d --build
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser
```

Docker Compose starts the backend with migrations and static collection in its command, but running `migrate` explicitly is still useful after model changes.

For manual setup, see [docs/SETUP.md](docs/SETUP.md).

## API Areas

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/logout/`
- `POST /api/auth/token/refresh/`
- `GET/PATCH /api/auth/profile/`
- `GET /api/auth/doctors/`
- `GET /api/auth/patients/`
- `GET/POST /api/appointments/`
- `POST /api/appointments/{id}/confirm/`
- `POST /api/appointments/{id}/cancel/`
- `POST /api/appointments/{id}/complete/`
- `GET/POST /api/appointments/availability/`
- `GET/POST /api/consultations/`
- `POST /api/consultations/{id}/start/`
- `POST /api/consultations/{id}/end/`
- `POST /api/consultations/{id}/messages/`
- `GET/POST /api/medical-records/`
- `GET/POST /api/medical-records/prescriptions/`
- `POST /api/medical-records/prescriptions/{id}/cancel/`
- `GET/POST /api/medical-records/documents/`
- `GET /api/audit/logs/`

Interactive OpenAPI documentation is available at `/api/docs/` when the backend is running.

## Security Status

Implemented:

- JWT authentication with refresh token rotation/blacklisting.
- Argon2-first password hashing.
- Role-based permissions and role-filtered querysets.
- DRF throttling defaults.
- CORS and secure cookie settings.
- Audit middleware and read-only audit log API for admins.
- Medical document hash calculation and encryption helper functions.
- Production-only Django security flags for SSL redirect, HSTS, secure cookies, and content-type protection.

Still required before real clinical use:

- Replace all development secrets.
- Run full security testing and dependency audits.
- Configure HTTPS/WSS, production CORS/CSRF origins, object storage, backups, monitoring, and incident response.
- Validate medical document encryption and key-management workflow end to end.
- Complete HIPAA/GDPR/legal review for the intended deployment region.

## Verification Snapshot

Previously performed:

```bash
python -m compileall backend
node --check realtime-service\src\server.js
node --check realtime-service\src\chat\service.js
node --check realtime-service\src\websocket\handler.js
```

Still pending:

- Install Python and Node dependencies in a clean environment.
- Run Django system checks, migrations, and tests.
- Run `npm run build` for both frontends.
- Add meaningful automated test suites beyond placeholder package scripts.

## Documentation

- [Project status](PROJECT_STATUS.md)
- [Project summary](PROJECT_SUMMARY.md)
- [Implementation guide](IMPLEMENTATION_GUIDE.md)
- [Quick start](QUICK_START.md)
- [Directory structure](DIRECTORY_STRUCTURE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API reference](docs/API.md)
- [Database schema](docs/DATABASE.md)
- [Security](docs/SECURITY.md)
- [Setup](docs/SETUP.md)

This platform handles sensitive healthcare data. Treat the current repository as a functional development scaffold until the production-hardening checklist has been completed.
