# Architecture Documentation

## System Architecture

The Secure Telemedicine Platform follows a **microservices architecture** with clear separation of concerns and service boundaries.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Client Layer                                  │
├──────────────────────────────┬──────────────────────────────────────┤
│   Next.js Patient Portal     │   React Doctor Dashboard             │
│   - Appointment Booking      │   - Patient Management               │
│   - Consultation Interface   │   - Consultation Interface           │
│   - Medical Records View     │   - Prescription Management          │
│   - Profile Management       │   - Analytics                        │
└──────────────┬───────────────┴──────────────┬───────────────────────┘
               │                              │
               │         HTTPS/WSS            │
               │                              │
┌──────────────▼──────────────────────────────▼───────────────────────┐
│                     API Gateway / Load Balancer                      │
│                     - Rate Limiting                                  │
│                     - SSL Termination                                │
│                     - Request Routing                                │
└──────────────┬──────────────────────────────┬───────────────────────┘
               │                              │
       ┌───────┴────────┐            ┌────────┴─────────┐
       │                │            │                  │
┌──────▼─────────┐  ┌──▼────────────▼───┐  ┌──────────▼──────────┐
│ Django Backend │  │ Node.js RT Service│  │ Storage Service     │
│                │  │                   │  │                     │
│ - REST APIs    │◄─┤ - WebSocket       │  │ - Medical Documents │
│ - Auth/AuthZ   │  │ - WebRTC Signaling│  │ - Images/Reports    │
│ - Business     │  │ - Chat Service    │  │ - Encrypted Storage │
│   Logic        │  │ - Presence        │  │                     │
│ - Data Models  │  └───────────────────┘  └─────────────────────┘
│                │
│ - Celery Tasks │◄──┐
└────────┬───────┘   │
         │           │
    ┌────▼───────┐   │
    │ PostgreSQL │   │
    │            │   │
    │ - User Data│   │
    │ - Medical  │   │
    │   Records  │   │
    │ - Audit Log│   │
    └────────────┘   │
                     │
              ┌──────▼──────┐
              │   Redis     │
              │             │
              │ - Cache     │
              │ - Sessions  │
              │ - Pub/Sub   │
              │ - Queue     │
              └─────────────┘
```

## Service Descriptions

### 1. Django Backend Service

**Responsibility**: Core business logic, data persistence, and RESTful API

**Key Components**:
- **Authentication & Authorization**: JWT-based auth with role-based access control
- **User Management**: Patient, Doctor, and Admin user management
- **Appointment System**: Scheduling, availability management, booking
- **Medical Records**: CRUD operations for medical history, prescriptions
- **Audit Logging**: Complete audit trail for compliance
- **File Management**: Medical document upload/download with encryption

**Technology Stack**:
- Django 5.0
- Django REST Framework
- PostgreSQL
- Celery for async tasks
- Redis for caching

**Database Schema** (Normalized):

```
Users
├── id (PK)
├── email (unique)
├── password_hash
├── role (patient/doctor/admin)
├── is_active
├── created_at
└── updated_at

UserProfiles
├── id (PK)
├── user_id (FK → Users)
├── first_name
├── last_name
├── phone
├── date_of_birth
├── gender
└── address

DoctorProfiles
├── id (PK)
├── user_id (FK → Users)
├── specialization
├── license_number
├── years_of_experience
├── consultation_fee
└── bio

Appointments
├── id (PK)
├── patient_id (FK → Users)
├── doctor_id (FK → Users)
├── scheduled_at
├── duration_minutes
├── status (pending/confirmed/completed/cancelled)
├── reason
├── created_at
└── updated_at

Consultations
├── id (PK)
├── appointment_id (FK → Appointments)
├── started_at
├── ended_at
├── session_id
├── notes
└── status

MedicalRecords
├── id (PK)
├── patient_id (FK → Users)
├── doctor_id (FK → Users)
├── consultation_id (FK → Consultations)
├── diagnosis
├── symptoms
├── notes
├── created_at
└── updated_at

Prescriptions
├── id (PK)
├── medical_record_id (FK → MedicalRecords)
├── medication_name
├── dosage
├── frequency
├── duration
├── instructions
└── created_at

MedicalDocuments
├── id (PK)
├── patient_id (FK → Users)
├── uploaded_by (FK → Users)
├── document_type
├── file_path (encrypted)
├── file_hash
├── uploaded_at
└── description

AuditLogs
├── id (PK)
├── user_id (FK → Users)
├── action
├── resource_type
├── resource_id
├── ip_address
├── user_agent
├── timestamp
└── metadata (JSON)
```

### 2. Node.js Real-time Service

**Responsibility**: Real-time communication, WebRTC signaling, chat

**Key Components**:
- **WebSocket Server**: Persistent connections for real-time updates
- **WebRTC Signaling**: SDP offer/answer exchange, ICE candidate handling
- **Chat Service**: Real-time messaging during consultations
- **Presence Management**: Online/offline status tracking
- **Session Management**: Consultation session lifecycle

**Technology Stack**:
- Node.js 20
- Express
- Socket.io
- Redis (Pub/Sub for horizontal scaling)

**WebSocket Events**:

```javascript
// Client → Server
'join-consultation'     // Join a consultation room
'leave-consultation'    // Leave a consultation room
'webrtc-offer'         // Send WebRTC offer
'webrtc-answer'        // Send WebRTC answer
'webrtc-ice-candidate' // Send ICE candidate
'chat-message'         // Send chat message
'typing'               // Typing indicator

// Server → Client
'consultation-joined'   // Confirmation of joining
'user-joined'          // Another user joined
'user-left'            // User left consultation
'webrtc-offer'         // Receive WebRTC offer
'webrtc-answer'        // Receive WebRTC answer
'webrtc-ice-candidate' // Receive ICE candidate
'chat-message'         // Receive chat message
'typing'               // User is typing
'error'                // Error occurred
```

**Session Management**:

```javascript
{
  sessionId: "uuid",
  consultationId: "consultation-id",
  participants: [
    { userId: "patient-id", socketId: "socket-1", role: "patient" },
    { userId: "doctor-id", socketId: "socket-2", role: "doctor" }
  ],
  startedAt: "timestamp",
  status: "active"
}
```

### 3. Patient Portal (Next.js)

**Responsibility**: Patient-facing web application

**Key Features**:
- Server-side rendering for SEO and performance
- Responsive design for mobile/tablet/desktop
- Progressive Web App (PWA) capabilities
- Optimistic UI updates
- Real-time consultation interface

**Pages**:
- `/` - Landing page
- `/login` - Authentication
- `/register` - Patient registration
- `/dashboard` - Patient dashboard
- `/appointments` - Appointment management
- `/appointments/book` - Book new appointment
- `/consultation/[id]` - Video consultation room
- `/medical-records` - Medical history
- `/prescriptions` - Prescription list
- `/profile` - Profile management

### 4. Doctor Dashboard (React)

**Responsibility**: Doctor-facing web application

**Key Features**:
- Rich data visualization
- Calendar integration
- Patient history access
- Prescription management
- Analytics and reporting

**Pages**:
- `/login` - Authentication
- `/dashboard` - Doctor dashboard with stats
- `/appointments` - Appointment calendar
- `/patients` - Patient list
- `/patients/[id]` - Patient details and history
- `/consultation/[id]` - Video consultation room
- `/prescriptions` - Prescription management
- `/analytics` - Performance analytics
- `/profile` - Profile management

## Data Flow

### 1. Appointment Booking Flow

```
Patient Portal
    ↓ (1) GET /api/doctors/?specialization=cardiology
Django Backend
    ↓ (2) Return available doctors
Patient Portal
    ↓ (3) GET /api/appointments/availability/?doctor_id=123&date=2026-02-05
Django Backend
    ↓ (4) Return available time slots
Patient Portal
    ↓ (5) POST /api/appointments/ {doctor_id, scheduled_at, reason}
Django Backend
    ↓ (6) Create appointment
    ↓ (7) Send confirmation email (async via Celery)
    ↓ (8) Return appointment details
Patient Portal
    ↓ (9) Display confirmation
```

### 2. Video Consultation Flow

```
Patient/Doctor Dashboard
    ↓ (1) GET /api/consultations/{id}/token
Django Backend
    ↓ (2) Validate user access
    ↓ (3) Generate session token
    ↓ (4) Return token and session details
Client
    ↓ (5) Connect to WebSocket with token
Node.js RT Service
    ↓ (6) Validate token with Django
    ↓ (7) Emit 'consultation-joined'
    ↓ (8) WebRTC signaling (offer/answer/ICE)
    ↓ (9) Establish peer connection
    ↓ (10) Video/audio streaming (P2P)
    ↓ (11) Chat messages via WebSocket
```

### 3. Medical Record Access Flow

```
Doctor Dashboard
    ↓ (1) GET /api/patients/{id}/medical-records
Django Backend
    ↓ (2) Check authorization (doctor has access to patient)
    ↓ (3) Log access in AuditLogs
    ↓ (4) Fetch medical records
    ↓ (5) Return records
Doctor Dashboard
    ↓ (6) Display records
```

## Security Architecture

### Authentication Flow

```
Client
    ↓ (1) POST /api/auth/login {email, password}
Django Backend
    ↓ (2) Validate credentials
    ↓ (3) Generate access token (15 min expiry)
    ↓ (4) Generate refresh token (7 day expiry)
    ↓ (5) Store refresh token hash in DB
    ↓ (6) Return {access_token, refresh_token, user}
Client
    ↓ (7) Store tokens securely
    ↓ (8) Include access token in Authorization header
```

### Authorization Layers

1. **API Level**: Django REST Framework permissions
2. **Object Level**: Custom permission classes
3. **Field Level**: Serializer field permissions
4. **Database Level**: Row-level security (future enhancement)

### Data Encryption

- **In Transit**: TLS 1.3 for all communications
- **At Rest**: 
  - Database: PostgreSQL encryption
  - Files: AES-256 encryption before storage
  - Passwords: Argon2 hashing

### Audit Logging

All sensitive operations are logged:
- Medical record access
- Prescription creation
- User authentication
- Data modifications
- File downloads

## Scalability Considerations

### Horizontal Scaling

- **Django Backend**: Stateless design allows multiple instances behind load balancer
- **Node.js RT Service**: Redis Pub/Sub enables multi-instance WebSocket scaling
- **Database**: Read replicas for read-heavy operations
- **File Storage**: CDN for static files, S3 for medical documents

### Caching Strategy

- **Redis Cache**: 
  - User sessions
  - API responses (with short TTL)
  - Doctor availability
  - Frequently accessed medical records metadata

### Async Processing

- **Celery Tasks**:
  - Email notifications
  - SMS reminders
  - Report generation
  - Data analytics
  - Scheduled appointment reminders

## Monitoring & Observability

### Metrics

- Request latency (p50, p95, p99)
- Error rates
- Active consultations
- Database query performance
- Cache hit rates
- WebSocket connection count

### Logging

- Structured JSON logs
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Centralized log aggregation (ELK/CloudWatch)

### Health Checks

- `/health/` - Basic health check
- `/health/db/` - Database connectivity
- `/health/redis/` - Redis connectivity
- `/health/storage/` - File storage accessibility

## Disaster Recovery

- **Database Backups**: Daily automated backups with 30-day retention
- **Point-in-Time Recovery**: Transaction log backups every 15 minutes
- **File Backups**: Versioned storage with replication
- **RTO**: 4 hours
- **RPO**: 15 minutes

## Compliance Considerations

### HIPAA Compliance

- Encrypted data storage and transmission
- Access controls and audit logs
- Business Associate Agreements (BAA)
- Regular security assessments
- Incident response plan

### GDPR Compliance

- Data minimization
- Right to access
- Right to erasure
- Data portability
- Consent management

---

This architecture is designed to be:
- **Secure**: Multiple layers of security
- **Scalable**: Horizontal scaling capabilities
- **Maintainable**: Clear service boundaries
- **Observable**: Comprehensive monitoring
- **Compliant**: Healthcare regulation ready
