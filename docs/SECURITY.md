# Security Documentation

## Security Overview

This document outlines the comprehensive security measures implemented in the Secure Telemedicine Platform to protect sensitive healthcare data and ensure compliance with industry regulations.

## Security Principles

1. **Defense in Depth**: Multiple layers of security controls
2. **Least Privilege**: Minimal access rights for users and services
3. **Zero Trust**: Verify every request, never assume trust
4. **Encryption Everywhere**: Data encrypted in transit and at rest
5. **Audit Everything**: Comprehensive logging of all sensitive operations

## Authentication

### JWT-Based Authentication

**Access Token**:
- Short-lived (15 minutes)
- Contains user ID, role, and permissions
- Signed with RS256 (asymmetric encryption)
- Cannot be revoked (short expiry mitigates risk)

**Refresh Token**:
- Long-lived (7 days)
- Stored as hashed value in database
- Can be revoked
- Rotated on each use
- Single-use only (prevents replay attacks)

**Implementation**:

```python
# Django Backend - Token Generation
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    
    # Customize token claims
    refresh['role'] = user.role
    refresh['email'] = user.email
    
    # Set custom expiry
    refresh.access_token.set_exp(lifetime=timedelta(minutes=15))
    
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
```

**Token Storage** (Client-side):
- Access token: Memory only (not localStorage)
- Refresh token: HttpOnly cookie (prevents XSS)
- CSRF token: Separate cookie for state-changing requests

### Multi-Factor Authentication (MFA)

**Supported Methods**:
- TOTP (Time-based One-Time Password) via authenticator apps
- SMS-based OTP (fallback)
- Email-based OTP (fallback)

**Implementation**:
- Required for doctors and admins
- Optional but recommended for patients
- Backup codes provided during setup

### Password Security

**Requirements**:
- Minimum 12 characters
- Mix of uppercase, lowercase, numbers, and symbols
- Not in common password lists
- Not similar to username or email

**Storage**:
- Hashed using Argon2id
- Unique salt per password
- Memory-hard algorithm (resistant to GPU attacks)

```python
# Django settings
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]
```

## Authorization

### Role-Based Access Control (RBAC)

**Roles**:

1. **Patient**
   - View own medical records
   - Book appointments
   - Join consultations as patient
   - Manage own profile

2. **Doctor**
   - View assigned patients' medical records
   - Manage appointments
   - Conduct consultations
   - Create prescriptions
   - Upload medical documents

3. **Admin**
   - User management
   - System configuration
   - View audit logs
   - Platform analytics

**Permission Matrix**:

| Resource | Patient | Doctor | Admin |
|----------|---------|--------|-------|
| Own Medical Records | Read | - | Read All |
| Patient Medical Records | - | Read (assigned) | Read All |
| Appointments | Create, Read (own) | Read, Update (assigned) | Read All |
| Prescriptions | Read (own) | Create, Read (assigned) | Read All |
| Users | Read (self) | Read (patients) | CRUD All |
| Audit Logs | - | - | Read All |

### Object-Level Permissions

Custom permission classes ensure users can only access resources they own or are authorized to access:

```python
# Django Backend - Custom Permission
from rest_framework import permissions

class IsDoctorOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.role == 'doctor'

class IsOwnerOrDoctor(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Patients can only access their own records
        if request.user.role == 'patient':
            return obj.patient == request.user
        
        # Doctors can access records of their patients
        if request.user.role == 'doctor':
            return obj.doctor == request.user or obj.patient in request.user.patients.all()
        
        # Admins have full access
        return request.user.role == 'admin'
```

## Data Encryption

### In Transit

**TLS Configuration**:
- TLS 1.3 only (TLS 1.2 minimum for compatibility)
- Strong cipher suites only
- Perfect Forward Secrecy (PFS)
- HSTS enabled (max-age=31536000)

```nginx
# Nginx Configuration
ssl_protocols TLSv1.3 TLSv1.2;
ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
ssl_prefer_server_ciphers off;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

**WebSocket Security**:
- WSS (WebSocket Secure) only
- Same TLS configuration as HTTPS
- Token-based authentication before upgrade

### At Rest

**Database Encryption**:
- PostgreSQL Transparent Data Encryption (TDE)
- Encrypted backups
- Encrypted WAL files

**File Encryption**:
- AES-256-GCM for medical documents
- Unique encryption key per file
- Keys stored in secure key management service (AWS KMS/HashiCorp Vault)

```python
# Django Backend - File Encryption
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

def encrypt_file(file_data, key):
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, file_data, None)
    return nonce + ciphertext

def decrypt_file(encrypted_data, key):
    aesgcm = AESGCM(key)
    nonce = encrypted_data[:12]
    ciphertext = encrypted_data[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)
```

## Input Validation & Sanitization

### API Input Validation

**Django REST Framework Serializers**:

```python
from rest_framework import serializers
from django.core.validators import RegexValidator

class AppointmentSerializer(serializers.ModelSerializer):
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    
    patient_phone = serializers.CharField(validators=[phone_regex], max_length=17)
    reason = serializers.CharField(max_length=500, required=True)
    scheduled_at = serializers.DateTimeField()
    
    def validate_scheduled_at(self, value):
        if value < timezone.now():
            raise serializers.ValidationError("Cannot schedule appointments in the past")
        return value
    
    class Meta:
        model = Appointment
        fields = ['id', 'patient', 'doctor', 'scheduled_at', 'reason']
```

### SQL Injection Prevention

- **ORM Usage**: Always use Django ORM (parameterized queries)
- **Raw Queries**: Avoided; when necessary, use parameterized queries
- **Input Validation**: All user inputs validated before database operations

### XSS Prevention

**Content Security Policy**:

```python
# Django Middleware
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com")
CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com")
CSP_IMG_SRC = ("'self'", "data:", "https:")
CSP_CONNECT_SRC = ("'self'", "wss:", "https:")
```

**Output Encoding**:
- React automatically escapes JSX
- Django templates use auto-escaping
- Sanitize HTML in rich text fields

### CSRF Protection

- CSRF tokens for all state-changing requests
- SameSite cookie attribute
- Double-submit cookie pattern

```python
# Django settings
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
```

## Rate Limiting

### API Rate Limiting

**Django REST Framework Throttling**:

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'auth': '5/minute',  # Login attempts
    }
}
```

**Custom Throttling for Sensitive Endpoints**:

```python
from rest_framework.throttling import UserRateThrottle

class MedicalRecordThrottle(UserRateThrottle):
    rate = '100/hour'

class PrescriptionThrottle(UserRateThrottle):
    rate = '50/hour'
```

### WebSocket Rate Limiting

- Maximum 100 messages per minute per connection
- Automatic disconnection on violation
- IP-based rate limiting for connection attempts

## Audit Logging

### What We Log

1. **Authentication Events**
   - Login attempts (success/failure)
   - Logout events
   - Token refresh
   - Password changes
   - MFA setup/changes

2. **Authorization Events**
   - Permission denied events
   - Role changes
   - Access to sensitive resources

3. **Data Access**
   - Medical record views
   - Prescription access
   - Document downloads
   - Patient information access

4. **Data Modifications**
   - Medical record creation/updates
   - Prescription creation
   - Appointment changes
   - User profile updates

### Audit Log Structure

```python
class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)  # e.g., "VIEW_MEDICAL_RECORD"
    resource_type = models.CharField(max_length=50)  # e.g., "MedicalRecord"
    resource_id = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict)  # Additional context
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id']),
            models.Index(fields=['timestamp']),
        ]
```

### Audit Log Retention

- **Hot Storage**: 90 days in primary database
- **Warm Storage**: 1 year in compressed format
- **Cold Storage**: 7 years in archival storage (compliance requirement)

## Security Headers

```python
# Django Middleware
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
```

## File Upload Security

### Validation

```python
# Django Backend
ALLOWED_FILE_TYPES = [
    'application/pdf',
    'image/jpeg',
    'image/png',
    'application/dicom',  # Medical imaging
]

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def validate_file(file):
    # Check file size
    if file.size > MAX_FILE_SIZE:
        raise ValidationError("File too large")
    
    # Check file type
    if file.content_type not in ALLOWED_FILE_TYPES:
        raise ValidationError("Invalid file type")
    
    # Verify file signature (magic bytes)
    file_signature = file.read(8)
    file.seek(0)
    
    # Additional validation...
    
    return True
```

### Storage

- Files stored outside web root
- Randomized filenames (UUID)
- Encrypted before storage
- Virus scanning (ClamAV integration)
- Access via signed URLs only

## WebRTC Security

### Signaling Security

- Authentication required before signaling
- Room-based access control
- Encrypted signaling messages

### Media Security

- DTLS-SRTP for media encryption
- ICE with TURN server for NAT traversal
- TURN server authentication

```javascript
// WebRTC Configuration
const rtcConfig = {
  iceServers: [
    {
      urls: 'stun:stun.l.google.com:19302'
    },
    {
      urls: 'turn:turn.example.com:3478',
      username: 'username',
      credential: 'password'
    }
  ],
  iceTransportPolicy: 'relay',  // Force TURN for privacy
  iceCandidatePoolSize: 10
};
```

## Dependency Security

### Vulnerability Scanning

- **Python**: `pip-audit` and `safety`
- **Node.js**: `npm audit` and Snyk
- **Docker**: Trivy for image scanning

### Update Policy

- Security patches: Applied within 24 hours
- Minor updates: Weekly review and update
- Major updates: Monthly review with testing

## Incident Response

### Detection

- Real-time monitoring with alerts
- Anomaly detection (unusual access patterns)
- Failed authentication tracking
- Rate limit violations

### Response Plan

1. **Identification**: Detect and verify security incident
2. **Containment**: Isolate affected systems
3. **Eradication**: Remove threat and vulnerabilities
4. **Recovery**: Restore systems to normal operation
5. **Lessons Learned**: Post-incident review and improvements

### Breach Notification

- Affected users notified within 72 hours
- Regulatory bodies notified as required
- Detailed incident report prepared

## Compliance

### HIPAA Compliance

✅ **Administrative Safeguards**:
- Security management process
- Workforce security
- Information access management
- Security awareness training

✅ **Physical Safeguards**:
- Facility access controls
- Workstation security
- Device and media controls

✅ **Technical Safeguards**:
- Access control
- Audit controls
- Integrity controls
- Transmission security

### GDPR Compliance

✅ **Data Protection Principles**:
- Lawfulness, fairness, transparency
- Purpose limitation
- Data minimization
- Accuracy
- Storage limitation
- Integrity and confidentiality

✅ **Individual Rights**:
- Right to access
- Right to rectification
- Right to erasure
- Right to data portability
- Right to object

## Security Testing

### Regular Testing

- **Penetration Testing**: Quarterly by third-party
- **Vulnerability Scanning**: Weekly automated scans
- **Code Review**: All code reviewed before merge
- **Security Audits**: Annual comprehensive audit

### Bug Bounty Program

- Responsible disclosure policy
- Rewards for valid security findings
- Scope: All production systems
- Out of scope: Social engineering, DoS

## Security Checklist

### Development

- [ ] Input validation on all user inputs
- [ ] Parameterized queries (no raw SQL)
- [ ] Proper error handling (no sensitive info in errors)
- [ ] Secure defaults
- [ ] Principle of least privilege

### Deployment

- [ ] HTTPS/WSS only
- [ ] Security headers configured
- [ ] Secrets in environment variables (not code)
- [ ] Database encryption enabled
- [ ] Backups encrypted
- [ ] Monitoring and alerting configured
- [ ] Rate limiting enabled
- [ ] CORS properly configured

### Operations

- [ ] Regular security updates
- [ ] Access logs reviewed
- [ ] Audit logs monitored
- [ ] Incident response plan tested
- [ ] Backup restoration tested
- [ ] Disaster recovery plan documented

---

**Security is an ongoing process, not a one-time implementation. Regular reviews and updates are essential.**
