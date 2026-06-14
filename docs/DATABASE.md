# Database Schema

The platform uses a normalized PostgreSQL schema centered on users, appointments, consultations, medical records, prescriptions, documents, and audit logs.

## Identity

- `users`: custom email-based users with `patient`, `doctor`, and `admin` roles.
- `user_profiles`: demographic and contact profile data.
- `doctor_profiles`: specialization, license, fees, availability status, ratings, and professional metadata.
- `patient_medical_info`: blood group, height, weight, allergies, chronic conditions, medications, and emergency contact data.
- `two_factor_auth`: per-user 2FA settings and backup codes.

## Care Workflow

- `doctor_availability`: weekly availability windows for doctors.
- `appointments`: patient/doctor scheduling with status, reason, symptoms, notes, cancellation reason, and meeting link metadata.
- `consultations`: video consultation sessions with room IDs, lifecycle timestamps, diagnosis, notes, and follow-up data.
- `consultation_messages`: persisted chat messages tied to a consultation.

## Clinical Records

- `medical_records`: patient clinical entries created by doctors and optionally linked to consultations.
- `prescriptions`: digital prescriptions with status, validity date, verification code, patient, doctor, and optional consultation.
- `prescription_items`: medication line items with dosage, frequency, duration, and instructions.
- `medical_documents`: uploaded reports and documents with document type, uploader, patient, optional record, file path, and SHA-256 file hash.

## Security and Compliance

- `audit_logs`: immutable-style application audit trail for sensitive API reads and mutating requests, including actor, action, path, method, status, IP address, user agent, metadata, and timestamp.

## Relationship Summary

- A patient and doctor can have many appointments.
- An appointment can have one consultation.
- A consultation can have many messages, records, and prescriptions.
- A patient can have many medical records, prescriptions, and documents.
- A doctor can create many records and prescriptions.
- Audit logs may reference any authenticated user or anonymous API activity.
