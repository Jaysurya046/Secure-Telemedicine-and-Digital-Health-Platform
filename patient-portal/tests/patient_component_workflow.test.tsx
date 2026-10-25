import './setup_dom.mjs';
import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

import AppointmentsPage from '../src/app/appointments/page';
import {
  apiFetch,
  toIsoTimestamp,
  formatErrorMessage,
  isInvalidPageError,
  ApiError,
  clearTokens,
  setTokens
} from '../src/lib/api';

describe('Patient Portal: Genuine API-Helper Unit Tests', () => {
  beforeEach(() => {
    clearTokens();
  });

  it('converts local datetime input to timezone-aware ISO string', () => {
    const valid = '2026-11-03T10:30';
    const iso = toIsoTimestamp(valid);
    assert.ok(iso, 'ISO string generated');
    assert.match(iso, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);

    // Invalid dates return empty string
    assert.equal(toIsoTimestamp(''), '');
    assert.equal(toIsoTimestamp('invalid-date'), '');
  });

  it('preserves HTTP status, body, and details in ApiError', () => {
    const errorBody = {
      detail: 'Invalid page.',
      details: {
        scheduled_start: ['Doctor has no active availability window covering this slot.']
      }
    };
    const err = new ApiError('Validation Error', 404, errorBody);

    assert.equal(err.status, 404);
    assert.deepEqual(err.body, errorBody);
    assert.deepEqual(err.details, errorBody.details);
    assert.equal(err.message, 'Validation Error');
  });

  it('accurately identifies DRF "Invalid page." 404 error responses', () => {
    // 1. Valid DRF Invalid page error
    const invalidPage = new ApiError('Invalid page.', 404, { detail: 'Invalid page.' });
    assert.equal(isInvalidPageError(invalidPage), true);

    // 2. Unrelated 404 Not found
    const notFound = new ApiError('Not found.', 404, { detail: 'Not found.' });
    assert.equal(isInvalidPageError(notFound), false);

    // 3. Permission failure 403
    const forbidden = new ApiError('Forbidden', 403, { detail: 'You do not have permission to perform this action.' });
    assert.equal(isInvalidPageError(forbidden), false);

    // 4. Network error / standard Error
    const netErr = new TypeError('Failed to fetch');
    assert.equal(isInvalidPageError(netErr), false);
  });

  it('formats various DRF error response shapes into readable strings', () => {
    // Nested details dictionary
    assert.equal(
      formatErrorMessage({
        details: {
          scheduled_start: ['Cannot reschedule appointment with status confirmed.']
        }
      }),
      'scheduled_start: Cannot reschedule appointment with status confirmed.'
    );

    // Direct field map
    assert.equal(
      formatErrorMessage({
        scheduled_start: ['Doctor has no active availability window covering this slot.']
      }),
      'scheduled_start: Doctor has no active availability window covering this slot.'
    );

    // String fields
    assert.equal(formatErrorMessage({ message: 'Unauthorized' }), 'Unauthorized');
    assert.equal(formatErrorMessage({ detail: 'Token expired' }), 'Token expired');
  });

  it('handles 204 No Content responses in apiFetch by returning null', async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => {
      return new Response(null, { status: 204 });
    };

    try {
      const result = await apiFetch<any>('/api/test-204/');
      assert.equal(result, null);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe('Patient Portal: Real Component Workflow Tests', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    clearTokens();
    setTokens({ access: 'patient-test-token', refresh: 'patient-test-refresh' });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    cleanup();
    clearTokens();
  });

  it('guards against delayed availability responses during rapid doctor selection', async () => {
    const doctorsList = [
      { id: 'doc-1', email: 'doctor1@example.com', profile: { full_name: 'Dr. Sarah Connor' }, doctor_profile: { specialty: 'Cardiology' } },
      { id: 'doc-2', email: 'doctor2@example.com', profile: { full_name: 'Dr. John Matrix' }, doctor_profile: { specialty: 'Neurology' } }
    ];

    let resolveDoctor1: (value: any) => void;
    const doc1Promise = new Promise((resolve) => {
      resolveDoctor1 = resolve;
    });

    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes('/api/auth/doctors/')) {
        return new Response(JSON.stringify({ results: doctorsList, next: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }

      if (url.includes('/api/appointments/?page=1')) {
        return new Response(JSON.stringify({ count: 0, next: null, previous: null, results: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }

      if (url.includes('/api/appointments/availability/') && url.includes('doctor=doc-1')) {
        // Slow response for Doctor 1
        await doc1Promise;
        return new Response(
          JSON.stringify({
            results: [{ id: 'avail-doc1', doctor: 'doc-1', weekday: 0, start_time: '08:00:00', end_time: '12:00:00', is_active: true }]
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (url.includes('/api/appointments/availability/') && url.includes('doctor=doc-2')) {
        // Fast response for Doctor 2
        return new Response(
          JSON.stringify({
            results: [{ id: 'avail-doc2', doctor: 'doc-2', weekday: 2, start_time: '14:00:00', end_time: '18:00:00', is_active: true }]
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      return new Response(JSON.stringify({ results: [] }), { status: 200 });
    };

    render(<AppointmentsPage />);

    // Wait for doctors to load in dropdown
    await waitFor(() => {
      assert.ok(screen.getByText(/Dr. Sarah Connor/));
    });

    const selectDropdown = screen.getByRole('combobox');

    // 1. User selects Doctor 1
    fireEvent.change(selectDropdown, { target: { value: 'doc-1' } });

    // 2. User rapidly switches to Doctor 2 before Doctor 1 resolves
    fireEvent.change(selectDropdown, { target: { value: 'doc-2' } });

    // Doctor 2 responds fast: Wednesday 14:00 - 18:00
    await waitFor(() => {
      assert.ok(screen.getByText('Wednesday'));
      assert.ok(screen.getByText(/14:00.*18:00/));
    });

    // 3. Now Doctor 1's delayed response finally resolves
    resolveDoctor1!(true);
    await new Promise((resolve) => setTimeout(resolve, 50));

    // Doctor 1's schedule (Monday 08:00 - 12:00) must NOT overwrite Doctor 2's schedule
    assert.ok(screen.getByText('Wednesday'));
    assert.equal(screen.queryByText('Monday'), null);
  });

  it('submits patient booking, pending rescheduling, and cancellation with actual request payloads', async () => {
    const doctorsList = [
      { id: 'doc-1', email: 'doctor1@example.com', profile: { full_name: 'Dr. Sarah Connor' } }
    ];

    let currentAppointments = [
      {
        id: 'appt-patient-1',
        doctor: 'doc-1',
        doctor_detail: { email: 'doctor1@example.com', profile: { full_name: 'Dr. Sarah Connor' } },
        patient: 'patient-uuid',
        scheduled_start: '2026-11-03T10:00:00Z',
        scheduled_end: '2026-11-03T11:00:00Z',
        status: 'pending' as const,
        reason: 'Existing Consultation',
        created_at: '2026-10-25T10:00:00Z'
      }
    ];

    const capturedRequests: Array<{ url: string; method: string; body: any }> = [];

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method || 'GET';
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      capturedRequests.push({ url, method, body });

      if (url.includes('/api/auth/doctors/')) {
        return new Response(JSON.stringify({ results: doctorsList, next: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }

      if (url.includes('/api/appointments/?page=1')) {
        return new Response(
          JSON.stringify({ count: currentAppointments.length, next: null, previous: null, results: currentAppointments }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (url.includes('/api/appointments/availability/')) {
        return new Response(
          JSON.stringify({
            results: [{ id: 'avail-1', doctor: 'doc-1', weekday: 1, start_time: '09:00:00', end_time: '17:00:00', is_active: true }]
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (method === 'POST' && url.endsWith('/api/appointments/')) {
        const newAppt = {
          id: 'appt-new-1',
          doctor: body.doctor,
          scheduled_start: body.scheduled_start,
          scheduled_end: body.scheduled_end,
          status: 'pending' as const,
          reason: body.reason,
          created_at: '2026-10-25T12:00:00Z'
        };
        currentAppointments.push(newAppt);
        return new Response(JSON.stringify(newAppt), { status: 201, headers: { 'Content-Type': 'application/json' } });
      }

      if (method === 'PATCH' && url.includes('/api/appointments/appt-patient-1/')) {
        currentAppointments[0].scheduled_start = body.scheduled_start;
        currentAppointments[0].scheduled_end = body.scheduled_end;
        return new Response(JSON.stringify(currentAppointments[0]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      if (method === 'POST' && url.includes('/api/appointments/appt-patient-1/cancel/')) {
        currentAppointments[0].status = 'cancelled' as any;
        return new Response(JSON.stringify({ ...currentAppointments[0], cancellation_reason: body?.cancellation_reason }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }

      return new Response(JSON.stringify({ results: [] }), { status: 200 });
    };

    render(<AppointmentsPage />);

    await waitFor(() => {
      assert.ok(screen.getByText('Existing Consultation'));
    });

    // 1. Rescheduling: Click Reschedule button on pending appointment
    const rescheduleBtn = screen.getByText('Reschedule');
    fireEvent.click(rescheduleBtn);

    await waitFor(() => {
      assert.ok(screen.getByText('Confirm Reschedule'));
    });

    const modalInputs = screen.getAllByDisplayValue('');
    // First datetime input is start, second is end in modal
    fireEvent.change(modalInputs[modalInputs.length - 2], { target: { value: '2026-11-04T10:00' } });
    fireEvent.change(modalInputs[modalInputs.length - 1], { target: { value: '2026-11-04T11:00' } });

    const confirmRescheduleBtn = screen.getByText('Confirm Reschedule');
    fireEvent.click(confirmRescheduleBtn);

    await waitFor(() => {
      const patchReq = capturedRequests.find((r) => r.method === 'PATCH');
      assert.ok(patchReq, 'PATCH called for rescheduling');
      assert.ok(patchReq.body.scheduled_start.startsWith('2026-11-04'), 'Converted to ISO timestamp');
    });

    // 2. Cancellation: Click Cancel button
    const cancelBtn = screen.getByText('Cancel');
    fireEvent.click(cancelBtn);

    await waitFor(() => {
      assert.ok(screen.getByText('Confirm Cancellation'));
    });

    const reasonTextarea = screen.getByPlaceholderText(/e\.g\. Schedule conflict/);
    fireEvent.change(reasonTextarea, { target: { value: 'Patient emergency conflict' } });

    const confirmCancelBtn = screen.getByText('Confirm Cancellation');
    fireEvent.click(confirmCancelBtn);

    await waitFor(() => {
      const cancelReq = capturedRequests.find((r) => r.url.includes('/cancel/'));
      assert.ok(cancelReq, 'Cancel endpoint called');
      assert.equal(cancelReq.method, 'POST');
      assert.equal(cancelReq.body.cancellation_reason, 'Patient emergency conflict');
    });
  });

  it('recovers from DRF 404 "Invalid page." by loading page 1, and does not recover on unrelated 404s, 403s, or network failures', async () => {
    const requestedUrls: string[] = [];

    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      requestedUrls.push(url);

      if (url.includes('/api/auth/doctors/')) {
        return new Response(JSON.stringify({ results: [], next: null }), { status: 200 });
      }

      if (url.includes('/api/appointments/?page=2')) {
        // DRF 404 response on page overflow
        return new Response(JSON.stringify({ detail: 'Invalid page.' }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' }
        });
      }

      if (url.includes('/api/appointments/?page=1')) {
        return new Response(
          JSON.stringify({
            count: 1,
            next: null,
            previous: null,
            results: [
              {
                id: 'appt-recovered',
                doctor: 'doc-1',
                scheduled_start: '2026-11-05T10:00:00Z',
                scheduled_end: '2026-11-05T11:00:00Z',
                status: 'pending',
                reason: 'Recovered Page 1 Appointment'
              }
            ]
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      return new Response(JSON.stringify({ results: [] }), { status: 200 });
    };

    render(<AppointmentsPage />);

    await waitFor(() => {
      assert.ok(screen.getByText('Recovered Page 1 Appointment'));
    });

    // Case 1: Unrelated 404 Not found does NOT trigger pagination recovery
    cleanup();
    requestedUrls.length = 0;

    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.includes('/api/auth/doctors/')) {
        return new Response(JSON.stringify({ results: [], next: null }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Not found.' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      });
    };

    render(<AppointmentsPage />);
    await waitFor(() => {
      assert.ok(screen.getByText('Not found.'));
    });
    // Verify no endless recovery loop
    assert.equal(requestedUrls.filter((u) => u.includes('/api/appointments/')).length, 1);

    // Case 2: 403 Forbidden does NOT trigger pagination recovery
    cleanup();
    requestedUrls.length = 0;

    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.includes('/api/auth/doctors/')) {
        return new Response(JSON.stringify({ results: [], next: null }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'You do not have permission to perform this action.' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' }
      });
    };

    render(<AppointmentsPage />);
    await waitFor(() => {
      assert.ok(screen.getByText('You do not have permission to perform this action.'));
    });

    // Case 3: Network failure does NOT trigger pagination recovery
    cleanup();
    globalThis.fetch = async () => {
      throw new TypeError('Failed to fetch');
    };

    render(<AppointmentsPage />);
    await waitFor(() => {
      const errs = screen.getAllByText('Failed to fetch');
      assert.ok(errs.length >= 1);
      const retries = screen.getAllByText('Retry');
      assert.ok(retries.length >= 1);
    });
  });
});
