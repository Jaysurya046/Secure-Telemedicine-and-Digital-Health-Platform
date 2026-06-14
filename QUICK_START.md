# Quick Start Guide

Last updated: 2026-06-14

## What This Project Contains

- Django REST backend on port `8000`.
- PostgreSQL database on port `5432`.
- Redis cache/pub-sub broker on port `6379`.
- Celery worker and Celery beat scheduler.
- Node.js realtime service on port `3002`.
- Next.js patient portal on port `3000`.
- Vite React doctor dashboard on port `3001`.

## Docker Start

From the project root:

```bash
cp .env.example .env
docker-compose up -d --build
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser
```

Useful URLs:

- Patient portal: http://localhost:3000
- Doctor dashboard: http://localhost:3001
- Backend API docs: http://localhost:8000/api/docs/
- Django admin: http://localhost:8000/admin/
- Backend health: http://localhost:8000/health/
- Realtime health: http://localhost:3002/health

## Manual Development Start

Start PostgreSQL and Redis first, then run each service in its own terminal.

Backend:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Realtime service:

```bash
cd realtime-service
npm install
npm run dev
```

Patient portal:

```bash
cd patient-portal
npm install
npm run dev
```

Doctor dashboard:

```bash
cd doctor-dashboard
npm install
npm run dev
```

Celery worker:

```bash
cd backend
venv\Scripts\activate
celery -A config worker -l info
```

Celery beat:

```bash
cd backend
venv\Scripts\activate
celery -A config beat -l info
```

## First API Smoke Test

1. Open http://localhost:8000/api/docs/.
2. Register a user with `POST /api/auth/register/`.
3. Log in with `POST /api/auth/login/`.
4. Click Authorize in Swagger UI and enter `Bearer <access_token>`.
5. Try `GET /api/auth/profile/`.
6. Create a doctor user or admin user, then test appointment and consultation endpoints.

## Main API Groups

- Auth/users: `/api/auth/`
- Appointments: `/api/appointments/`
- Consultations: `/api/consultations/`
- Medical records: `/api/medical-records/`
- Prescriptions: `/api/medical-records/prescriptions/`
- Documents: `/api/medical-records/documents/`
- Audit logs: `/api/audit/logs/`
- Health: `/health/`, `/health/db/`, `/health/redis/`

## Current Verification Status

Previously completed:

```bash
python -m compileall backend
node --check realtime-service\src\server.js
node --check realtime-service\src\chat\service.js
node --check realtime-service\src\websocket\handler.js
```

Still needed after dependency installation:

```bash
cd backend
python manage.py check
python manage.py test

cd ..\patient-portal
npm run build

cd ..\doctor-dashboard
npm run build

cd ..\realtime-service
npm test
```

The frontend package `test` scripts are currently placeholders, so add real test tooling before relying on them.

## Troubleshooting

Check container status:

```bash
docker-compose ps
```

View logs:

```bash
docker-compose logs -f backend
docker-compose logs -f realtime
docker-compose logs -f patient_portal
docker-compose logs -f doctor_dashboard
```

Common fixes:

- If the backend cannot connect to Postgres or Redis, confirm `.env` matches the Docker service names `db` and `redis`.
- If frontend calls fail, confirm `NEXT_PUBLIC_API_URL` and `VITE_API_URL` point to `http://localhost:8000`.
- If sockets fail, confirm `NEXT_PUBLIC_WS_URL` and `VITE_WS_URL` point to `ws://localhost:3002`.
- If migrations fail after model changes, inspect the app migration files before resetting anything.

## Next Best Steps

1. Run the full Docker stack.
2. Create patient, doctor, and admin accounts.
3. Exercise booking, consultation, prescription, and audit workflows.
4. Add automated tests around permission and workflow boundaries.
5. Harden secrets, TLS, storage, monitoring, backups, and compliance before production.
