# API Reference - Users App

## Base URL
```
http://localhost:8000/api
```

## Authentication

All authenticated endpoints require a JWT token in the Authorization header:
```
Authorization: Bearer <access_token>
```

---

## Authentication Endpoints

### Register User
Create a new user account (patient or doctor).

**Endpoint:** `POST /auth/register/`

**Permission:** Public (AllowAny)

> **Role Restriction:** Only `patient` or `doctor` roles can be registered through this endpoint. The `admin` role is strictly rejected. Privileged account flags (`is_staff`, `is_superuser`, `is_verified`) cannot be set during registration.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!@#",
  "password_confirm": "SecurePass123!@#",
  "role": "patient",  // or "doctor"
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+1234567890"  // optional
}
```

**Response:** `201 Created`
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "patient",
    "is_active": true,
    "is_verified": false,
    "created_at": "2026-02-03T02:00:00Z",
    "profile": {
      "first_name": "John",
      "last_name": "Doe",
      "full_name": "John Doe",
      "phone": "+1234567890",
      ...
    }
  },
  "tokens": {
    "refresh": "refresh_token_here",
    "access": "access_token_here"
  },
  "message": "Registration successful"
}
```

---

### Login
Authenticate user and receive JWT tokens.

**Endpoint:** `POST /auth/login/`

**Permission:** Public (AllowAny)

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!@#"
}
```

**Response:** `200 OK`
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "role": "patient",
    ...
  },
  "tokens": {
    "refresh": "refresh_token_here",
    "access": "access_token_here"
  },
  "message": "Login successful"
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid credentials
- `403 Forbidden` - Account is inactive

---

### Logout
Logout user and blacklist refresh token.

**Endpoint:** `POST /auth/logout/`

**Permission:** Authenticated

**Request Body:**
```json
{
  "refresh": "refresh_token_here"
}
```

**Response:** `200 OK`
```json
{
  "message": "Logout successful"
}
```

---

### Refresh Token
Get a new access token using refresh token.

**Endpoint:** `POST /auth/token/refresh/`

**Permission:** Public (AllowAny)

**Request Body:**
```json
{
  "refresh": "refresh_token_here"
}
```

**Response:** `200 OK`
```json
{
  "access": "new_access_token_here",
  "refresh": "new_refresh_token_here"  // if rotation enabled
}
```

---

## User Management Endpoints

### Get User Profile
Get authenticated user's profile.

**Endpoint:** `GET /auth/profile/`

**Permission:** Authenticated

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "role": "patient",
  "is_active": true,
  "is_verified": false,
  "created_at": "2026-02-03T02:00:00Z",
  "profile": {
    "first_name": "John",
    "last_name": "Doe",
    "full_name": "John Doe",
    "phone": "+1234567890",
    "date_of_birth": "1990-01-01",
    "gender": "M",
    "address": "123 Main St",
    "city": "New York",
    "state": "NY",
    "country": "USA",
    "postal_code": "10001",
    "avatar": "http://localhost:8000/media/avatars/avatar.jpg"
  },
  "medical_info": {  // if patient
    "blood_group": "A+",
    "height": 175.5,
    "weight": 70.0,
    "allergies": ["Penicillin"],
    "chronic_conditions": ["Diabetes"],
    "current_medications": ["Metformin"],
    "emergency_contact_name": "Jane Doe",
    "emergency_contact_phone": "+1234567891",
    "emergency_contact_relation": "Spouse"
  }
}
```

---

### Update User Profile
Update authenticated user's profile.

**Endpoint:** `PATCH /auth/profile/`

**Permission:** Authenticated

> **Method Restriction:** `PUT /auth/profile/` is unsupported and returns `405 Method Not Allowed`. Profile writes must use `PATCH` for partial updates of nested resources (`profile`, `doctor_profile`, `medical_info`). Account security fields (`role`, `is_active`, `is_staff`, `is_superuser`, `is_verified`, and `email`) are strictly read-only and cannot be altered via profile writes. All nested updates are validated before saving; invalid nested input triggers atomic rollback without partial modification.

**Request Body:**
```json
{
  "profile": {
    "first_name": "John",
    "last_name": "Smith",
    "phone": "+1234567890",
    "date_of_birth": "1990-01-01",
    "gender": "M",
    "address": "456 Oak Ave",
    "city": "Los Angeles",
    "state": "CA",
    "country": "USA",
    "postal_code": "90001"
  },
  "doctor_profile": {  // if doctor
    "specialization": "Cardiology",
    "years_of_experience": 10,
    "consultation_fee": 150.00,
    "bio": "Experienced cardiologist...",
    "is_available": true
  },
  "medical_info": {  // if patient
    "blood_group": "A+",
    "height": 175.5,
    "weight": 70.0,
    "allergies": ["Penicillin", "Peanuts"]
  }
}
```

**Response:** `200 OK`
```json
{
  // Updated user object
}
```

---

### Change Password
Change user password.

**Endpoint:** `POST /auth/change-password/`

**Permission:** Authenticated

**Request Body:**
```json
{
  "old_password": "OldPass123!@#",
  "new_password": "NewPass123!@#",
  "new_password_confirm": "NewPass123!@#"
}
```

**Response:** `200 OK`
```json
{
  "message": "Password changed successfully"
}
```

**Error Response:** `400 Bad Request`
```json
{
  "error": "Old password is incorrect"
}
```

---

## Doctor Endpoints

### List Doctors
Get a list of all active doctors with filtering and search.

**Endpoint:** `GET /auth/doctors/`

**Permission:** Authenticated

**Query Parameters:**
- `specialization` - Filter by specialization
- `is_available` - Filter by availability (true/false)
- `search` - Search by name or specialization
- `ordering` - Order by field (e.g., `-average_rating`, `consultation_fee`)
- `page` - Page number
- `page_size` - Items per page

**Example:**
```
GET /auth/doctors/?specialization=Cardiology&is_available=true&ordering=-average_rating
```

**Response:** `200 OK`
```json
{
  "count": 10,
  "next": "http://localhost:8000/api/auth/doctors/?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "email": "doctor@example.com",
      "is_active": true,
      "profile": {
        "first_name": "Dr. Jane",
        "last_name": "Smith",
        "full_name": "Dr. Jane Smith",
        "phone": "+1234567890",
        "avatar": "..."
      },
      "doctor_profile": {
        "specialization": "Cardiology",
        "license_number": "MD12345",
        "years_of_experience": 15,
        "consultation_fee": 200.00,
        "bio": "Experienced cardiologist...",
        "is_available": true,
        "consultation_duration": 30,
        "average_rating": 4.8,
        "total_ratings": 150
      }
    }
  ]
}
```

---

### Get Doctor Details
Get detailed information about a specific doctor.

**Endpoint:** `GET /auth/doctors/{id}/`

**Permission:** Authenticated

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "email": "doctor@example.com",
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "profile": {
    "first_name": "Dr. Jane",
    "last_name": "Smith",
    "full_name": "Dr. Jane Smith",
    "phone": "+1234567890",
    "date_of_birth": "1980-01-01",
    "gender": "F",
    "address": "789 Medical Center",
    "city": "Boston",
    "state": "MA",
    "country": "USA",
    "postal_code": "02101",
    "avatar": "..."
  },
  "doctor_profile": {
    "specialization": "Cardiology",
    "license_number": "MD12345",
    "years_of_experience": 15,
    "consultation_fee": 200.00,
    "bio": "Board-certified cardiologist with 15 years of experience...",
    "education": [
      {
        "degree": "MD",
        "institution": "Harvard Medical School",
        "year": 2005
      }
    ],
    "certifications": [
      "Board Certified in Cardiology",
      "Advanced Cardiac Life Support (ACLS)"
    ],
    "languages": ["English", "Spanish"],
    "is_available": true,
    "consultation_duration": 30,
    "average_rating": 4.8,
    "total_ratings": 150
  }
}
```

---

### Get Doctor Availability
Get doctor's availability schedule.

**Endpoint:** `GET /auth/doctors/{id}/availability/`

**Permission:** Authenticated

**Response:** `200 OK`
```json
{
  "doctor_id": "uuid",
  "is_available": true,
  "consultation_duration": 30,
  "message": "Availability endpoint - to be fully implemented with appointments app"
}
```

---

## Patient Endpoints

### List Patients
Get a list of patients (doctors see their patients, admins see all).

**Endpoint:** `GET /auth/patients/`

**Permission:** Doctor or Admin

**Query Parameters:**
- `search` - Search by name or email
- `page` - Page number
- `page_size` - Items per page

**Response:** `200 OK`
```json
{
  "count": 50,
  "next": "http://localhost:8000/api/auth/patients/?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "email": "patient@example.com",
      "is_active": true,
      "created_at": "2026-01-15T00:00:00Z",
      "profile": {
        "first_name": "John",
        "last_name": "Doe",
        "full_name": "John Doe",
        "phone": "+1234567890",
        "avatar": "..."
      }
    }
  ]
}
```

---

### Get Patient Details
Get detailed information about a specific patient.

**Endpoint:** `GET /auth/patients/{id}/`

**Permission:** Doctor or Admin

**Response:** `200 OK`
```json
{
  "id": "uuid",
  "email": "patient@example.com",
  "is_active": true,
  "created_at": "2026-01-15T00:00:00Z",
  "profile": {
    "first_name": "John",
    "last_name": "Doe",
    "full_name": "John Doe",
    "phone": "+1234567890",
    "date_of_birth": "1990-01-01",
    "gender": "M",
    "address": "123 Main St",
    "city": "New York",
    "state": "NY",
    "country": "USA",
    "postal_code": "10001",
    "avatar": "..."
  },
  "medical_info": {
    "blood_group": "A+",
    "height": 175.5,
    "weight": 70.0,
    "allergies": ["Penicillin"],
    "chronic_conditions": ["Diabetes"],
    "current_medications": ["Metformin"],
    "emergency_contact_name": "Jane Doe",
    "emergency_contact_phone": "+1234567891",
    "emergency_contact_relation": "Spouse"
  }
}
```

---

## Statistics Endpoint

### Get Platform Statistics
Get public platform statistics.

**Endpoint:** `GET /auth/statistics/`

**Permission:** Public (AllowAny)

**Response:** `200 OK`
```json
{
  "total_doctors": 150,
  "total_patients": 5000,
  "specializations": 25
}
```

---

## Health Check Endpoints

### Basic Health Check
Check if service is running.

**Endpoint:** `GET /health/`

**Permission:** Public (AllowAny)

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "service": "telemedicine-backend"
}
```

---

### Database Health Check
Check database connectivity.

**Endpoint:** `GET /health/db/`

**Permission:** Public (AllowAny)

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "database": "connected"
}
```

**Error Response:** `503 Service Unavailable`
```json
{
  "status": "unhealthy",
  "database": "disconnected",
  "error": "connection error message"
}
```

---

### Redis Health Check
Check Redis connectivity.

**Endpoint:** `GET /health/redis/`

**Permission:** Public (AllowAny)

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "redis": "connected"
}
```

**Error Response:** `503 Service Unavailable`
```json
{
  "status": "unhealthy",
  "redis": "disconnected",
  "error": "connection error message"
}
```

---

## Error Responses

All endpoints return consistent error responses:

### Validation Error
**Status:** `400 Bad Request`
```json
{
  "error": true,
  "message": "Validation error",
  "details": {
    "email": ["This field is required."],
    "password": ["This field is required."]
  }
}
```

### Authentication Error
**Status:** `401 Unauthorized`
```json
{
  "error": true,
  "message": "Authentication credentials were not provided.",
  "details": {
    "detail": "Authentication credentials were not provided."
  }
}
```

### Permission Error
**Status:** `403 Forbidden`
```json
{
  "error": true,
  "message": "You do not have permission to perform this action.",
  "details": {
    "detail": "You do not have permission to perform this action."
  }
}
```

### Not Found Error
**Status:** `404 Not Found`
```json
{
  "error": true,
  "message": "Not found",
  "details": {
    "detail": "Not found."
  }
}
```

### Server Error
**Status:** `500 Internal Server Error`
```json
{
  "error": true,
  "message": "Internal server error",
  "details": {
    "detail": "An error occurred."
  }
}
```

---

## Rate Limiting

- **Anonymous users**: 100 requests per hour
- **Authenticated users**: 1000 requests per hour
- **Authentication endpoints**: 5 requests per minute

When rate limit is exceeded:
**Status:** `429 Too Many Requests`
```json
{
  "detail": "Request was throttled. Expected available in 60 seconds."
}
```

---

## Interactive API Documentation

For interactive API testing, visit:
- **Swagger UI**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/

---

## Notes

1. All timestamps are in ISO 8601 format (UTC)
2. All IDs are UUIDs
3. Pagination uses page numbers (default page size: 20)
4. File uploads use multipart/form-data
5. All other requests use application/json
6. JWT access tokens expire in 15 minutes
7. JWT refresh tokens expire in 7 days

---

## Appointments & Doctor Availability Endpoints

### List / Create Appointments
- **List**: `GET /api/appointments/` (Supports query parameters: `status`, `page`, `ordering`)
  - Permissions: Authenticated (`patient` sees own, `doctor` sees own assigned, `admin` sees all).
  - Paginated Response: `{ "count": N, "next": "...", "previous": "...", "results": [...] }`.
- **Create**: `POST /api/appointments/`
  - Permissions: Authenticated (`patient`, `doctor`, `admin`).
  - Request body:
    ```json
    {
      "doctor": "uuid",
      "scheduled_start": "2026-11-03T10:00:00Z",
      "scheduled_end": "2026-11-03T11:00:00Z",
      "reason": "Consultation",
      "symptoms": ["headache"]
    }
    ```
  - Derives patient for patient role caller; author spoofing rejected with HTTP 400.
  - Every new appointment starts with status `pending`.

### Retrieve / Update (Reschedule) Appointment
- **Retrieve**: `GET /api/appointments/{id}/`
- **Update / Reschedule**: `PATCH /api/appointments/{id}/`
  - Only pending appointments can change timestamps.
  - Rescheduling must fit an active availability window for the doctor and not overlap existing bookings.
  - Generic PUT/PATCH cannot mutate status directly (use dedicated lifecycle actions).

### Appointment Lifecycle Actions
- **Confirm**: `POST /api/appointments/{id}/confirm/`
  - Transition: `pending` -> `confirmed`.
  - Body: `{}` (empty object required).
  - Permission: Assigned doctor or admin.
- **Cancel**: `POST /api/appointments/{id}/cancel/`
  - Transition: `pending` or `confirmed` -> `cancelled`.
  - Body: `{ "cancellation_reason": "optional reason string" }`.
  - Permission: Assigned patient, assigned doctor, or admin.
- **Complete**: `POST /api/appointments/{id}/complete/`
  - Transition: `confirmed` -> `completed`.
  - Body: `{}` (empty object required).
  - Permission: Assigned doctor or admin.

### Doctor Availability Schedule
- **List Availability**: `GET /api/appointments/availability/`
  - Doctors see all their windows (active and inactive). Patients see active windows.
  - Query parameters: `doctor`, `weekday`, `is_active`, `page`.
- **Create Availability Window**: `POST /api/appointments/availability/`
  - Permissions: Doctor (manages own) or Admin (requires doctor user).
  - Body:
    ```json
    {
      "weekday": 1,
      "start_time": "09:00:00",
      "end_time": "17:00:00",
      "is_active": true
    }
    ```
- **Update Availability Window**: `PATCH /api/appointments/availability/{id}/`
- **Delete Availability Window**: `DELETE /api/appointments/availability/{id}/` (Returns `204 No Content`).

---

## Appointment Scheduling & Timezone Handling

- **Timezone Alignment**: Appointment scheduling matches doctor availability windows using Django's configured default timezone (`settings.TIME_ZONE`, currently UTC). Aware datetimes submitted with different UTC offsets are converted to the configured default timezone before comparing weekday and time boundaries.
- **Active Window Fitting**: On appointment creation and actual datetime changes (rescheduling), the entire appointment must fit inside one active availability window (`is_active=True`) belonging to its doctor. Exact boundaries are permitted (`appointment start >= window start` and `appointment end <= window end`).
- **Midnight Crossing & Separate Windows**: Appointments crossing midnight in the configured timezone are rejected. Separate availability windows cannot be combined to cover an appointment.
- **Unchanged Edits & Historical Bookings**: Unrelated updates (such as notes) and unchanged timestamps (including equivalent timestamps expressed with different UTC offsets) do not revalidate doctor availability on existing appointments.
- **Concurrency & Locking Strategy**: PostgreSQL row-level locks via `select_for_update()` coordinate simultaneous bookings and prevent double-booking or state drift during concurrent requests.
