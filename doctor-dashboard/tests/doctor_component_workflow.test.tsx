import './setup_dom.mjs';
import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

import App from '../src/App';
import { Appointments } from '../src/pages/Appointments';
import { Availability } from '../src/pages/Availability';
import {
  apiFetch,
  formatErrorMessage,
  isInvalidPageError,
  ApiError,
  clearTokens,
  setTokens,
  getToken
} from '../src/services/api';

describe('Doctor Dashboard: Genuine API-Helper Unit Tests', () => {
  beforeEach(() => {
    clearTokens();
  });

  it('preserves HTTP status and structured details in ApiError', () => {
    const errorBody = {
      detail: 'Invalid page.',
      details: {
        scheduled_start: ['Cannot reschedule appointment with status completed.']
      }
    };
    const err = new ApiError('Validation Error', 404, errorBody);

    assert.equal(err.status, 404);
    assert.deepEqual(err.body, errorBody);
    assert.deepEqual(err.details, errorBody.details);
    assert.equal(err.message, 'Validation Error');
  });

  it('accurately identifies DRF "Invalid page." 404 error responses', () => {
    // 1. DRF Invalid page error (404 with detail "Invalid page.")
    const invalidPageErr = new ApiError('Invalid page.', 404, { detail: 'Invalid page.' });
    assert.equal(isInvalidPageError(invalidPageErr), true);

    // 2. Unrelated resource not found 404
    const notFoundErr = new ApiError('Not found.', 404, { detail: 'Not found.' });
    assert.equal(isInvalidPageError(notFoundErr), false);

    // 3. Permission failure 403
    const forbiddenErr = new ApiError('Permission Denied', 403, { detail: 'Authentication credentials were not provided.' });
    assert.equal(isInvalidPageError(forbiddenErr), false);

    // 4. Network error / standard Error
    const networkErr = new TypeError('Failed to fetch');
    assert.equal(isInvalidPageError(networkErr), false);

    // 5. Non-object or empty errors
    assert.equal(isInvalidPageError(null), false);
    assert.equal(isInvalidPageError(undefined), false);
  });

  it('formats various DRF error response shapes into readable strings', () => {
    // Nested details dictionary
    assert.equal(
      formatErrorMessage({
        details: {
          scheduled_start: ['Doctor has no active availability window covering this slot.']
        }
      }),
      'scheduled_start: Doctor has no active availability window covering this slot.'
    );

    // Direct error / message / detail
    assert.equal(formatErrorMessage({ detail: 'Method "DELETE" not allowed.' }), 'Method "DELETE" not allowed.');
    assert.equal(formatErrorMessage({ message: 'Invalid credentials' }), 'Invalid credentials');
    assert.equal(formatErrorMessage({ error: 'Conflict' }), 'Conflict');

    // Direct field mapping
    assert.equal(
      formatErrorMessage({
        start_time: ['Must be before end time.'],
        weekday: ['Invalid day.']
      }),
      'start_time: Must be before end time. | weekday: Invalid day.'
    );
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

describe('Doctor Dashboard: Real Component Workflow Tests', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    clearTokens();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    cleanup();
    clearTokens();
  });

  it('enforces session isolation: unmounts on logout, switches between Doctor A and Doctor B, and never leaks data', async () => {
    const doctorAAppointments = [
      {
        id: 'appt-a1',
        doctor: 'doc-a',
        patient: 'pat-1',
        patient_detail: { email: 'alice@example.com', profile: { full_name: 'Alice Smith' } },
        scheduled_start: '2026-11-03T10:00:00Z',
        scheduled_end: '2026-11-03T11:00:00Z',
        status: 'pending',
        reason: 'Alice Routine Examination'
      }
    ];
    const doctorAPatients = [
      { id: 'pat-1', email: 'alice@example.com', role: 'patient' }
    ];

    const doctorBAppointments = [
      {
        id: 'appt-b1',
        doctor: 'doc-b',
        patient: 'pat-2',
        patient_detail: { email: 'bob@example.com', profile: { full_name: 'Bob Jones' } },
        scheduled_start: '2026-11-04T14:00:00Z',
        scheduled_end: '2026-11-04T15:00:00Z',
        status: 'confirmed',
        reason: 'Bob Cardiac Consultation'
      }
    ];
    const doctorBPatients = [
      { id: 'pat-2', email: 'bob@example.com', role: 'patient' }
    ];

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.includes('/api/auth/login/')) {
        const body = JSON.parse(String(init?.body || '{}'));
        return new Response(
          JSON.stringify({
            tokens: {
              access: `mock-token-for-${body.email}`,
              refresh: 'mock-refresh'
            }
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      const token = getToken();
      if (token.includes('doctorA')) {
        if (url.includes('/api/appointments/')) {
          return new Response(
            JSON.stringify({ count: 1, next: null, previous: null, results: doctorAAppointments }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (url.includes('/api/auth/patients/')) {
          return new Response(
            JSON.stringify({ count: 1, next: null, previous: null, results: doctorAPatients }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
      } else if (token.includes('doctorB')) {
        if (url.includes('/api/appointments/')) {
          return new Response(
            JSON.stringify({ count: 1, next: null, previous: null, results: doctorBAppointments }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (url.includes('/api/auth/patients/')) {
          return new Response(
            JSON.stringify({ count: 1, next: null, previous: null, results: doctorBPatients }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
      }

      return new Response(JSON.stringify({ results: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    };

    // 1. Initial State: Unauthenticated
    render(<App />);
    assert.ok(screen.getByText('Doctor Portal Access'));
    assert.equal(screen.queryByText('Alice Routine Examination'), null);

    // 2. Doctor A Logs In
    const emailInput = screen.getByPlaceholderText('Doctor email');
    const passwordInput = screen.getByPlaceholderText('Password');
    const signInBtn = screen.getByText('Sign in');

    fireEvent.change(emailInput, { target: { value: 'doctorA@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'Password123!' } });
    fireEvent.click(signInBtn);

    await waitFor(() => {
      assert.ok(screen.getByText('Alice Smith'));
      assert.ok(screen.getByText(/Alice Routine Examination/));
    });
    assert.ok(screen.getByText('Doctor Session Active (doctorA@example.com)'));
    assert.equal(screen.queryByText('Bob Jones'), null);

    // 3. Doctor A Logs Out
    const signOutBtn = screen.getByText('Sign out');
    fireEvent.click(signOutBtn);

    await waitFor(() => {
      // Protected screens unmount immediately
      assert.ok(screen.getByText('Doctor Portal Access'));
    });
    assert.equal(screen.queryByText('Alice Smith'), null);
    assert.equal(getToken(), '');

    // 4. Doctor B Logs In
    const emailInputB = screen.getByPlaceholderText('Doctor email');
    const passwordInputB = screen.getByPlaceholderText('Password');
    const signInBtnB = screen.getByText('Sign in');

    fireEvent.change(emailInputB, { target: { value: 'doctorB@example.com' } });
    fireEvent.change(passwordInputB, { target: { value: 'Password123!' } });
    fireEvent.click(signInBtnB);

    await waitFor(() => {
      assert.ok(screen.getByText('Bob Jones'));
      assert.ok(screen.getByText(/Bob Cardiac Consultation/));
    });
    assert.ok(screen.getByText('Doctor Session Active (doctorB@example.com)'));

    // Verify Doctor A's data is NEVER visible in Doctor B's session
    assert.equal(screen.queryByText('Alice Smith'), null);
    assert.equal(screen.queryByText(/Alice Routine Examination/), null);
    assert.equal(screen.queryByText('alice@example.com'), null);
  });

  it('discards delayed responses from Doctor A session so they cannot overwrite Doctor B session', async () => {
    let resolveDelayedDoctorA: (value: any) => void;
    const delayedDoctorAPromise = new Promise((resolve) => {
      resolveDelayedDoctorA = resolve;
    });

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.includes('/api/auth/login/')) {
        const body = JSON.parse(String(init?.body || '{}'));
        return new Response(
          JSON.stringify({
            tokens: { access: `token-${body.email}`, refresh: 'refresh' }
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (url.includes('/api/appointments/')) {
        const token = getToken();
        if (token.includes('doctorA')) {
          // Delay Doctor A's response
          await delayedDoctorAPromise;
          return new Response(
            JSON.stringify({
              count: 1,
              results: [{ id: 'delayed-a', reason: 'Delayed Doctor A Appointment', status: 'pending' }]
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (token.includes('doctorB')) {
          return new Response(
            JSON.stringify({
              count: 1,
              results: [{ id: 'b1', patient_detail: { profile: { full_name: 'Patient Bob' } }, reason: 'Immediate Doctor B Appointment', status: 'confirmed' }]
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
      }

      return new Response(JSON.stringify({ results: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    };

    render(<App />);

    // Doctor A logs in
    fireEvent.change(screen.getByPlaceholderText('Doctor email'), { target: { value: 'doctorA@example.com' } });
    fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'passA' } });
    fireEvent.click(screen.getByText('Sign in'));

    await waitFor(() => {
      assert.ok(screen.getByText('Doctor Session Active (doctorA@example.com)'));
    });

    // While Doctor A appointment request is still in-flight, Doctor A logs out
    fireEvent.click(screen.getByText('Sign out'));
    await waitFor(() => {
      assert.ok(screen.getByText('Doctor Portal Access'));
    });

    // Doctor B logs in immediately
    fireEvent.change(screen.getByPlaceholderText('Doctor email'), { target: { value: 'doctorB@example.com' } });
    fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'passB' } });
    fireEvent.click(screen.getByText('Sign in'));

    await waitFor(() => {
      assert.ok(screen.getByText('Patient Bob'));
      assert.ok(screen.getByText(/Immediate Doctor B Appointment/));
    });

    // Now resolve the delayed Doctor A request
    resolveDelayedDoctorA!(true);
    await new Promise((resolve) => setTimeout(resolve, 50));

    // Doctor A's delayed appointment must be discarded and NOT overwrite Doctor B's screen
    assert.ok(screen.getByText(/Immediate Doctor B Appointment/));
    assert.equal(screen.queryByText(/Delayed Doctor A Appointment/), null);
  });

  it('renders Appointments component and performs actual rendered-form submissions for confirmation, completion, and doctor cancellation', async () => {
    let refreshCalls = 0;
    const mockRefresh = async () => {
      refreshCalls += 1;
    };

    let appointmentList = [
      {
        id: 'appt-1',
        doctor: 'doc-1',
        patient: 'pat-1',
        patient_detail: { email: 'patient@example.com', profile: { full_name: 'Patient One' } },
        scheduled_start: '2026-11-05T10:00:00Z',
        scheduled_end: '2026-11-05T11:00:00Z',
        status: 'pending' as const,
        reason: 'Post-Surgery Followup',
        created_at: '2026-10-25T10:00:00Z'
      }
    ];

    const capturedRequests: Array<{ url: string; method: string; body: any }> = [];

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method || 'GET';
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      capturedRequests.push({ url, method, body });

      if (url.includes('/api/appointments/?page=1')) {
        return new Response(
          JSON.stringify({ count: appointmentList.length, next: null, previous: null, results: appointmentList }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (url.includes('/api/appointments/appt-1/confirm/')) {
        appointmentList[0].status = 'confirmed';
        return new Response(JSON.stringify(appointmentList[0]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }

      if (url.includes('/api/appointments/appt-1/complete/')) {
        appointmentList[0].status = 'completed';
        return new Response(JSON.stringify(appointmentList[0]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }

      if (url.includes('/api/appointments/appt-1/cancel/')) {
        appointmentList[0].status = 'cancelled';
        (appointmentList[0] as any).cancellation_reason = body?.cancellation_reason;
        return new Response(JSON.stringify(appointmentList[0]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }

      return new Response(JSON.stringify({ results: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    };

    setTokens({ access: 'doc-token', refresh: 'doc-refresh' });
    render(<Appointments onRefreshDashboard={mockRefresh} />);

    // 1. Initial Load
    await waitFor(() => {
      assert.ok(screen.getByText('Post-Surgery Followup'));
    });
    assert.ok(screen.getByText('Confirm'));

    // 2. Doctor Confirms Appointment
    const confirmBtn = screen.getByText('Confirm');
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      assert.ok(screen.getByText(/Appointment confirmed successfully/));
    });

    const confirmReq = capturedRequests.find((r) => r.url.includes('/confirm/'));
    assert.ok(confirmReq, 'Confirm endpoint called');
    assert.equal(confirmReq.method, 'POST');
    assert.deepEqual(confirmReq.body, {}, 'Confirm sends empty object');
    assert.equal(refreshCalls, 1, 'onRefreshDashboard called on confirm');

    // 3. Doctor Completes Appointment
    await waitFor(() => {
      assert.ok(screen.getByText('Mark Complete'));
    });
    const completeBtn = screen.getByText('Mark Complete');
    fireEvent.click(completeBtn);

    await waitFor(() => {
      assert.ok(screen.getByText(/Appointment marked as completed/));
    });

    const completeReq = capturedRequests.find((r) => r.url.includes('/complete/'));
    assert.ok(completeReq, 'Complete endpoint called');
    assert.equal(completeReq.method, 'POST');
    assert.deepEqual(completeReq.body, {}, 'Complete sends empty object');
    assert.equal(refreshCalls, 2, 'onRefreshDashboard called on complete');

    // 4. Actual Rendered-Form Submission for Doctor Cancellation
    // Reset status to confirmed so Cancel button is present
    appointmentList[0].status = 'confirmed';
    fireEvent.click(screen.getByTitle('Refresh appointments'));

    await waitFor(() => {
      assert.ok(screen.getByText('Cancel'));
    });

    // Click Cancel button to open cancel modal
    fireEvent.click(screen.getByText('Cancel'));

    await waitFor(() => {
      assert.ok(screen.getByText('Cancel Appointment'));
    });

    // Fill in cancellation reason in the rendered form
    const reasonInput = screen.getByPlaceholderText('e.g. Doctor emergency, patient request');
    fireEvent.change(reasonInput, { target: { value: 'Doctor emergency surgery' } });

    // Submit rendered cancellation form
    const confirmCancelBtn = screen.getByRole('button', { name: 'Confirm Cancellation' });
    fireEvent.click(confirmCancelBtn);

    await waitFor(() => {
      assert.ok(screen.getByText(/Appointment cancelled/));
    });

    const cancelReq = capturedRequests.find((r) => r.url.includes('/cancel/'));
    assert.ok(cancelReq, 'Cancel endpoint was called');
    assert.equal(cancelReq.method, 'POST');
    assert.deepEqual(cancelReq.body, { cancellation_reason: 'Doctor emergency surgery' });
    assert.ok(screen.getByText(/Doctor emergency surgery/));
    assert.equal(refreshCalls, 3, 'onRefreshDashboard called on cancel');
  });

  it('navigates doctor appointments to page 2, cancels final item via rendered form, returns DRF 404 Invalid page, and recovers to page 1', async () => {
    const requestedUrls: string[] = [];
    const capturedMutations: Array<{ url: string; method: string; body: any }> = [];

    const page1Items = Array.from({ length: 10 }, (_, i) => ({
      id: `appt-p1-${i + 1}`,
      doctor: 'doc-1',
      patient: `pat-${i + 1}`,
      patient_detail: { email: `patient${i + 1}@example.com`, profile: { full_name: `Patient ${i + 1}` } },
      scheduled_start: '2026-11-05T10:00:00Z',
      scheduled_end: '2026-11-05T11:00:00Z',
      status: 'pending' as const,
      reason: `Page 1 Appointment ${i + 1}`,
      created_at: '2026-10-25T10:00:00Z'
    }));

    let page2Exists = true;

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method || 'GET';
      requestedUrls.push(url);

      if (method === 'POST' && url.includes('/api/appointments/appt-p2-1/cancel/')) {
        const body = init?.body ? JSON.parse(String(init.body)) : null;
        capturedMutations.push({ url, method, body });
        // The final item on page 2 is removed/cancelled
        page2Exists = false;
        return new Response(
          JSON.stringify({
            id: 'appt-p2-1',
            status: 'cancelled',
            cancellation_reason: body?.cancellation_reason
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (url.includes('/api/appointments/?page=1')) {
        return new Response(
          JSON.stringify({
            count: page2Exists ? 11 : 10,
            next: page2Exists ? 'http://localhost:8000/api/appointments/?page=2' : null,
            previous: null,
            results: page1Items
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (url.includes('/api/appointments/?page=2')) {
        if (!page2Exists) {
          // DRF actual 404 response on out-of-range page request
          return new Response(
            JSON.stringify({ detail: 'Invalid page.' }),
            { status: 404, headers: { 'Content-Type': 'application/json' } }
          );
        }
        return new Response(
          JSON.stringify({
            count: 11,
            next: null,
            previous: 'http://localhost:8000/api/appointments/?page=1',
            results: [
              {
                id: 'appt-p2-1',
                doctor: 'doc-1',
                patient: 'pat-11',
                patient_detail: { email: 'pat11@example.com', profile: { full_name: 'Patient Eleven' } },
                scheduled_start: '2026-11-06T15:00:00Z',
                scheduled_end: '2026-11-06T16:00:00Z',
                status: 'pending' as const,
                reason: 'Final Item On Page 2',
                created_at: '2026-10-25T11:00:00Z'
              }
            ]
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      return new Response(JSON.stringify({ results: [] }), { status: 200 });
    };

    setTokens({ access: 'doc-token', refresh: 'doc-refresh' });
    render(<Appointments />);

    // 1. Initial Load: Page 1 items are displayed
    await waitFor(() => {
      assert.ok(screen.getByText('Page 1 Appointment 1'));
    });
    assert.ok(screen.getByText('Page 1'));

    // 2. Navigate to Page 2 through rendered Next button
    const nextBtn = screen.getByRole('button', { name: /Next/i });
    assert.equal(nextBtn.hasAttribute('disabled'), false, 'Next button enabled on page 1');
    fireEvent.click(nextBtn);

    // 3. Verify Page 2 items are rendered
    await waitFor(() => {
      assert.ok(screen.getByText('Final Item On Page 2'));
    });
    assert.ok(screen.getByText('Page 2'));

    // 4. Remove final item through rendered Cancel form submission
    const cancelBtn = screen.getByText('Cancel');
    fireEvent.click(cancelBtn);

    await waitFor(() => {
      assert.ok(screen.getByText('Cancel Appointment'));
    });

    const reasonInput = screen.getByPlaceholderText('e.g. Doctor emergency, patient request');
    fireEvent.change(reasonInput, { target: { value: 'Cancelling final item on page 2' } });

    const submitCancelBtn = screen.getByRole('button', { name: 'Confirm Cancellation' });
    fireEvent.click(submitCancelBtn);

    // 5. Assert mutation details
    await waitFor(() => {
      const cancelMutation = capturedMutations.find((m) => m.url.includes('/api/appointments/appt-p2-1/cancel/'));
      assert.ok(cancelMutation, 'Cancel mutation executed');
      assert.equal(cancelMutation.method, 'POST');
      assert.deepEqual(cancelMutation.body, { cancellation_reason: 'Cancelling final item on page 2' });
    });

    // 6. Assert recovery to Page 1 occurred after DRF 404 on Page 2
    await waitFor(() => {
      assert.ok(screen.getByText('Page 1 Appointment 1'));
      assert.ok(screen.getByText(/10 total appointment/));
    });

    // Assert that page 2 was requested after mutation, got 404, and then page 1 was requested
    const lastPage2ReqIdx = requestedUrls.findLastIndex((u) => u.includes('page=2'));
    const lastPage1ReqIdx = requestedUrls.findLastIndex((u) => u.includes('page=1'));
    assert.ok(lastPage2ReqIdx > 0, 'Page 2 was requested after mutation');
    assert.ok(lastPage1ReqIdx > lastPage2ReqIdx, 'Page 1 recovery request occurred after DRF 404 on page 2');
    assert.equal(screen.queryByText('Final Item On Page 2'), null);
  });

  it('renders Availability component: rendered-form creation, editing, and pagination recovery from DRF 404', async () => {
    const requestedUrls: string[] = [];
    const mutationCalls: Array<{ url: string; method: string; body: any }> = [];

    const page1Windows = Array.from({ length: 10 }, (_, i) => ({
      id: `avail-p1-${i + 1}`,
      doctor: 'doc-1',
      weekday: i % 7,
      start_time: '08:00:00',
      end_time: '12:00:00',
      is_active: true,
      created_at: '2026-10-25T10:00:00Z',
      updated_at: '2026-10-25T10:00:00Z'
    }));

    let page2Exists = true;

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method || 'GET';
      requestedUrls.push(url);

      if (method === 'POST' && url.includes('/api/appointments/availability/')) {
        const body = JSON.parse(String(init?.body || '{}'));
        mutationCalls.push({ url, method, body });
        const newWin = {
          id: 'avail-created-1',
          doctor: 'doc-1',
          weekday: body.weekday,
          start_time: body.start_time,
          end_time: body.end_time,
          is_active: body.is_active,
          created_at: '2026-10-25T12:00:00Z',
          updated_at: '2026-10-25T12:00:00Z'
        };
        return new Response(JSON.stringify(newWin), { status: 201, headers: { 'Content-Type': 'application/json' } });
      }

      if (method === 'PATCH' && url.includes('/api/appointments/availability/avail-p1-1/')) {
        const body = JSON.parse(String(init?.body || '{}'));
        mutationCalls.push({ url, method, body });
        const updatedWin = {
          ...page1Windows[0],
          weekday: body.weekday !== undefined ? body.weekday : page1Windows[0].weekday,
          start_time: body.start_time || page1Windows[0].start_time,
          end_time: body.end_time || page1Windows[0].end_time,
          is_active: body.is_active !== undefined ? body.is_active : page1Windows[0].is_active
        };
        page1Windows[0] = updatedWin;
        return new Response(JSON.stringify(updatedWin), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      if (method === 'DELETE' && url.includes('/api/appointments/availability/avail-p2-1/')) {
        mutationCalls.push({ url, method, body: null });
        page2Exists = false;
        return new Response(null, { status: 204 });
      }

      if (url.includes('/api/appointments/availability/?page=1')) {
        return new Response(
          JSON.stringify({
            count: page2Exists ? 11 : 10,
            next: page2Exists ? 'http://localhost:8000/api/appointments/availability/?page=2' : null,
            previous: null,
            results: page1Windows
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (url.includes('/api/appointments/availability/?page=2')) {
        if (!page2Exists) {
          // DRF actual 404 response on out-of-range page request
          return new Response(
            JSON.stringify({ detail: 'Invalid page.' }),
            { status: 404, headers: { 'Content-Type': 'application/json' } }
          );
        }
        return new Response(
          JSON.stringify({
            count: 11,
            next: null,
            previous: 'http://localhost:8000/api/appointments/availability/?page=1',
            results: [
              {
                id: 'avail-p2-1',
                doctor: 'doc-1',
                weekday: 4, // Friday
                start_time: '14:00:00',
                end_time: '18:00:00',
                is_active: true,
                created_at: '2026-10-25T10:00:00Z',
                updated_at: '2026-10-25T10:00:00Z'
              }
            ]
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      return new Response(JSON.stringify({ results: [] }), { status: 200 });
    };

    setTokens({ access: 'doc-token', refresh: 'doc-refresh' });
    render(<Availability />);

    // 1. Initial Load: Page 1 is displayed
    await waitFor(() => {
      assert.ok(screen.getByText('Page 1'));
    });

    // 2. Rendered-Form Submission: Create Availability Window
    const addWindowBtn = screen.getByText('Add Availability Window');
    fireEvent.click(addWindowBtn);

    await waitFor(() => {
      assert.ok(screen.getByText('Define New Availability Window'));
    });

    const createWeekdaySelect = screen.getByDisplayValue('Monday');
    fireEvent.change(createWeekdaySelect, { target: { value: '2' } }); // Wednesday

    const timeInputs = screen.getAllByDisplayValue(/^(09:00|17:00)$/);
    fireEvent.change(timeInputs[0], { target: { value: '08:30' } });
    fireEvent.change(timeInputs[1], { target: { value: '16:30' } });

    const submitCreateBtn = screen.getByRole('button', { name: 'Save Availability Window' });
    fireEvent.click(submitCreateBtn);

    await waitFor(() => {
      assert.ok(screen.getByText('Availability window created successfully.'));
    });

    const createReq = mutationCalls.find((m) => m.method === 'POST');
    assert.ok(createReq, 'POST availability was sent');
    assert.equal(createReq.url, 'http://localhost:8000/api/appointments/availability/');
    assert.deepEqual(createReq.body, {
      weekday: 2,
      start_time: '08:30:00',
      end_time: '16:30:00',
      is_active: true
    });

    // 3. Rendered-Form Submission: Edit Availability Window
    const editBtns = screen.getAllByTitle('Edit Window');
    fireEvent.click(editBtns[0]);

    await waitFor(() => {
      assert.ok(screen.getByText('Edit Availability Window'));
    });

    const editWeekdaySelect = screen.getAllByDisplayValue('Monday')[0];
    fireEvent.change(editWeekdaySelect, { target: { value: '1' } }); // Tuesday

    const editSubmitBtn = screen.getByRole('button', { name: 'Save Changes' });
    fireEvent.click(editSubmitBtn);

    await waitFor(() => {
      assert.ok(screen.getByText('Availability window updated successfully.'));
    });

    const editReq = mutationCalls.find((m) => m.method === 'PATCH');
    assert.ok(editReq, 'PATCH availability was sent');
    assert.equal(editReq.url, 'http://localhost:8000/api/appointments/availability/avail-p1-1/');
    assert.equal(editReq.body.weekday, 1);

    // 4. Navigate through rendered controls to Page 2
    const nextBtn = screen.getByRole('button', { name: /Next/i });
    fireEvent.click(nextBtn);

    await waitFor(() => {
      assert.ok(screen.getByText('Friday'));
      assert.ok(screen.getByText(/14:00 - 18:00 UTC/));
    });
    assert.ok(screen.getByText('Page 2'));

    // 5. Remove final item through rendered Delete button
    const deleteBtn = screen.getByTitle('Delete Window');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      const deleteReq = mutationCalls.find((m) => m.method === 'DELETE');
      assert.ok(deleteReq, 'DELETE called on final item');
      assert.equal(deleteReq.url, 'http://localhost:8000/api/appointments/availability/avail-p2-1/');
    });

    // 6. Assert recovery to Page 1 occurred after DRF 404 Invalid page on Page 2
    await waitFor(() => {
      assert.ok(screen.getByText(/10 total windows matching filter/));
    });

    const lastPage2ReqIdx = requestedUrls.findLastIndex((u) => u.includes('/api/appointments/availability/?page=2'));
    const lastPage1ReqIdx = requestedUrls.findLastIndex((u) => u.includes('/api/appointments/availability/?page=1'));
    assert.ok(lastPage2ReqIdx > 0, 'Page 2 was requested after delete');
    assert.ok(lastPage1ReqIdx > lastPage2ReqIdx, 'Page 1 recovery request occurred after DRF 404 on page 2');
    assert.equal(screen.queryByText(/14:00 - 18:00 UTC/), null);
  });

  it('rejects pagination recovery for unrelated 404s, 403s, and network failures', async () => {
    const requestedUrls: string[] = [];

    // Case 1: Unrelated 404 Not found
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      requestedUrls.push(url);
      return new Response(JSON.stringify({ detail: 'Not found.' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      });
    };

    setTokens({ access: 'doc-token', refresh: 'doc-refresh' });
    render(<Appointments />);

    await waitFor(() => {
      assert.ok(screen.getByText('Not found.'));
    });
    assert.equal(requestedUrls.filter((u) => u.includes('page=1')).length, 1);

    // Case 2: 403 Forbidden
    cleanup();
    requestedUrls.length = 0;

    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      requestedUrls.push(url);
      return new Response(JSON.stringify({ detail: 'Authentication credentials were not provided.' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' }
      });
    };

    render(<Appointments />);
    await waitFor(() => {
      assert.ok(screen.getByText('Authentication credentials were not provided.'));
    });

    // Case 3: Network error
    cleanup();
    globalThis.fetch = async () => {
      throw new TypeError('Failed to fetch');
    };

    render(<Appointments />);
    await waitFor(() => {
      assert.ok(screen.getByText('Failed to fetch'));
    });
  });

  it('applies server-side active/inactive filtering before pagination on Availability', async () => {
    const availabilityCalls: string[] = [];

    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      availabilityCalls.push(url);
      return new Response(
        JSON.stringify({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: 'avail-1',
              doctor: 'doc-1',
              weekday: 1,
              start_time: '09:00:00',
              end_time: '12:00:00',
              is_active: true,
              created_at: '2026-10-25T10:00:00Z',
              updated_at: '2026-10-25T10:00:00Z'
            }
          ]
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    };

    setTokens({ access: 'doc-token', refresh: 'doc-refresh' });
    render(<Availability />);

    await waitFor(() => {
      assert.ok(screen.getByText('Tuesday'));
    });
    assert.ok(availabilityCalls.some((url) => url.startsWith('http://localhost:8000/api/appointments/availability/?page=1')));

    // Filter Active
    const activeFilterBtn = screen.getByText('active');
    fireEvent.click(activeFilterBtn);

    await waitFor(() => {
      assert.ok(availabilityCalls.some((url) => url.includes('is_active=true')));
    });

    // Filter Inactive
    const inactiveFilterBtn = screen.getByText('inactive');
    fireEvent.click(inactiveFilterBtn);

    await waitFor(() => {
      assert.ok(availabilityCalls.some((url) => url.includes('is_active=false')));
    });

    // Filter All
    const allFilterBtn = screen.getByText('all');
    fireEvent.click(allFilterBtn);

    await waitFor(() => {
      assert.ok(availabilityCalls.some((url) => url.endsWith('availability/?page=1')));
    });
  });
});
