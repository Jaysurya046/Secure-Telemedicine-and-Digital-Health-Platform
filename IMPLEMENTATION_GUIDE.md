# Secure Telemedicine Platform - Implementation Guide

Last updated: 2026-06-14

## What Is Built

The platform currently includes the core service skeletons and main domain workflows across backend, realtime, and frontend layers.

### Infrastructure

- `docker-compose.yml` starts PostgreSQL, Redis, Django backend, Celery worker, Celery beat, realtime service, patient portal, and doctor dashboard.
- Backend, realtime service, patient portal, and doctor dashboard each have Dockerfiles.
- `.env.example` provides the shared local configuration template.

### Django Backend

The backend is under `backend/` and includes:

- Django 5 and Django REST Framework.
- JWT authentication through `djangorestframework-simplejwt`.
- API docs through `drf-spectacular`.
- Redis cache/session configuration.
- Celery configuration.
- PostgreSQL through `dj-database-url`.
- Custom exception handling.
- Audit middleware.

Implemented apps:

- `apps.users`: custom user model, profiles, doctor profile, patient medical info, 2FA model, auth/profile/directory endpoints, custom permissions, health URLs, and user email tasks.
- `apps.appointments`: appointment and availability models, serializers, viewsets, filters, confirm/cancel/complete actions, and reminder task module.
- `apps.consultations`: consultation and message models, serializers, viewset, start/end actions, message creation action, and stale-consultation cleanup task module.
- `apps.medical_records`: records, prescriptions, prescription items, documents, encryption/hash helpers, serializers, viewsets, prescription cancellation, and expiry task module.
- `apps.audit`: audit log model, middleware, serializer, read-only admin viewset, admin registration, and summary task module.

### Realtime Service

The realtime service is under `realtime-service/` and includes:

- Express HTTP server.
- `/health` and `/ready` endpoints.
- Socket.io server on `/socket.io`.
- JWT socket authentication middleware.
- Redis publisher/subscriber client setup.
- Consultation room join/leave events.
- Presence update events.
- WebRTC offer, answer, and ICE candidate signaling.
- Chat message events and recent history.

### Patient Portal

The patient portal is under `patient-portal/` and includes:

- Next.js 14 app router.
- TypeScript and TailwindCSS.
- Landing workspace.
- Login and registration pages.
- Dashboard page.
- Appointment booking/listing page.
- Consultation room page.
- `AppNav`, `VideoCall`, and `Chat` components.
- API and websocket helpers.

### Doctor Dashboard

The doctor dashboard is under `doctor-dashboard/` and includes:

- Vite React TypeScript app.
- Operational dashboard layout.
- Login strip.
- Dashboard, patients, and consultation views.
- Patient history and prescription form components.
- Video call component.
- API and websocket service modules.

## Backend API Map

Base URL: `http://localhost:8000/api/`

Authentication and users:

- `POST /auth/register/`
- `POST /auth/login/`
- `POST /auth/logout/`
- `POST /auth/token/refresh/`
- `GET/PATCH /auth/profile/`
- `POST /auth/change-password/`
- `GET /auth/doctors/`
- `GET /auth/doctors/{id}/`
- `GET /auth/doctors/{id}/availability/`
- `GET /auth/patients/`
- `GET /auth/patients/{id}/`
- `GET /auth/statistics/`

Appointments:

- `GET/POST /appointments/`
- `GET/PATCH/PUT/DELETE /appointments/{id}/`
- `POST /appointments/{id}/confirm/`
- `POST /appointments/{id}/cancel/`
- `POST /appointments/{id}/complete/`
- `GET/POST /appointments/availability/`
- `GET/PATCH/PUT/DELETE /appointments/availability/{id}/`

Consultations:

- `GET/POST /consultations/`
- `GET/PATCH/PUT/DELETE /consultations/{id}/`
- `POST /consultations/{id}/start/`
- `POST /consultations/{id}/end/`
- `POST /consultations/{id}/messages/`

Medical records:

- `GET/POST /medical-records/`
- `GET/PATCH/PUT/DELETE /medical-records/{id}/`
- `GET/POST /medical-records/prescriptions/`
- `GET/PATCH/PUT/DELETE /medical-records/prescriptions/{id}/`
- `POST /medical-records/prescriptions/{id}/cancel/`
- `GET/POST /medical-records/documents/`
- `GET/PATCH/PUT/DELETE /medical-records/documents/{id}/`

Audit:

- `GET /audit/logs/`
- `GET /audit/logs/{id}/`

Health and docs:

- `GET /health/`
- `GET /health/db/`
- `GET /health/redis/`
- `GET /api/docs/`
- `GET /api/redoc/`

## Recommended Local Validation

Use this sequence when dependencies and Docker are available:

```bash
cp .env.example .env
docker-compose up -d --build
docker-compose exec backend python manage.py check
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser
```

Then visit:

- Backend docs: http://localhost:8000/api/docs/
- Patient portal: http://localhost:3000
- Doctor dashboard: http://localhost:3001
- Realtime health: http://localhost:3002/health

## Implementation Priorities

### Priority 1: Runtime Verification

- Install Python and Node dependencies in a clean environment.
- Run migrations against PostgreSQL.
- Validate all service containers start and stay healthy.
- Exercise the login, booking, consultation, prescription, and audit flows manually.

### Priority 2: Backend Tests

Add tests for:

- User registration/login/profile updates.
- Patient, doctor, and admin authorization boundaries.
- Appointment creation, filtering, cancellation, confirmation, and completion.
- Availability validation and appointment conflict handling.
- Consultation start/end and message creation.
- Medical record, prescription, and document access control.
- Audit middleware behavior.

### Priority 3: Frontend and Realtime Tests

Add tests for:

- Patient auth and booking flows.
- Doctor login, patient selection, prescription submission, and consultation navigation.
- Socket authentication failures.
- Consultation room join/leave behavior.
- WebRTC signaling event forwarding.
- Chat send/receive behavior.

### Priority 4: Production Hardening

- Replace development secrets.
- Configure HTTPS/WSS.
- Lock down CORS and CSRF origins.
- Configure production object storage and medical document encryption/key management.
- Add backups, monitoring, alerting, log retention, and incident response.
- Run dependency audits and security tests.
- Complete healthcare compliance review.

## Definition of Done for Production

- [ ] Full stack starts cleanly from documented setup steps.
- [ ] All migrations apply from an empty database.
- [ ] Meaningful backend, frontend, and realtime tests pass.
- [ ] API permissions are covered by automated tests.
- [ ] Medical document storage is encrypted and recoverable with managed keys.
- [ ] Production secrets and environment variables are configured outside source control.
- [ ] HTTPS/WSS, CORS, CSRF, HSTS, logging, monitoring, and backups are configured.
- [ ] Compliance and legal requirements are reviewed for the target region.

## Notes for Future Development

- Prefer extending existing app patterns rather than adding new service boundaries.
- Keep clinical data access explicit and covered by tests.
- Treat the generated Swagger docs as the source of truth for request/response details once the backend is running.
- Update this guide whenever an endpoint, service, or milestone changes.
