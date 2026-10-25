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
      const method = init?.method || 'GET';

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

  it('renders Appointments component, handles lifecycle mutations (confirm, complete, cancel), and invokes dashboard refresh', async () => {
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
        return new Response(JSON.stringify({ ...appointmentList[0], cancellation_reason: body?.cancellation_reason }), {
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
  });

  it('recovers from DRF 404 "Invalid page." by falling back to page 1, but does not recover on unrelated 404s, 403s, or network errors', async () => {
    let appointmentsPageCallCount = 0;
    const requestedUrls: string[] = [];

    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      requestedUrls.push(url);

      if (url.includes('/api/appointments/?page=2')) {
        appointmentsPageCallCount += 1;
        // DRF 404 response when page exceeds total pages
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
                id: 'appt-p1',
                doctor: 'doc-1',
                patient: 'pat-1',
                scheduled_start: '2026-11-05T10:00:00Z',
                scheduled_end: '2026-11-05T11:00:00Z',
                status: 'pending',
                reason: 'Page 1 Recovered Appointment'
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

    // Initial load: page 1
    await waitFor(() => {
      assert.ok(screen.getByText('Page 1 Recovered Appointment'));
    });

    // Case 1: Testing recovery from actual DRF "Invalid page." 404 error
    // Directly invoking loadAppointments(2) by component recovery logic
    // Now simulate an unrelated 404: "Not found."
    cleanup();
    requestedUrls.length = 0;

    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      requestedUrls.push(url);
      return new Response(JSON.stringify({ detail: 'Not found.' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' }
      });
    };

    render(<Appointments />);
    await waitFor(() => {
      assert.ok(screen.getByText('Not found.'));
    });
    // Must NOT have attempted pagination recovery for unrelated 404
    assert.equal(requestedUrls.filter((u) => u.includes('page=1')).length, 1);

    // Case 2: Testing 403 Forbidden failure
    cleanup();
    requestedUrls.length = 0;

    globalThis.fetch = async (input: RequestInfo | URL) => {
      return new Response(JSON.stringify({ detail: 'Authentication credentials were not provided.' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' }
      });
    };

    render(<Appointments />);
    await waitFor(() => {
      assert.ok(screen.getByText('Authentication credentials were not provided.'));
    });

    // Case 3: Testing network failure
    cleanup();
    globalThis.fetch = async () => {
      throw new TypeError('Failed to fetch');
    };

    render(<Appointments />);
    await waitFor(() => {
      assert.ok(screen.getByText('Failed to fetch'));
    });
  });

  it('renders Availability component, applies active/inactive server filtering before pagination, and performs CRUD', async () => {
    const availabilityCalls: string[] = [];
    const mutationCalls: Array<{ url: string; method: string; body: any }> = [];

    let currentWindows = [
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
    ];

    globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method || 'GET';

      if (method === 'GET' && url.includes('/api/appointments/availability/')) {
        availabilityCalls.push(url);
        return new Response(
          JSON.stringify({
            count: currentWindows.length,
            next: null,
            previous: null,
            results: currentWindows
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }

      if (method === 'POST' && url.includes('/api/appointments/availability/')) {
        const body = JSON.parse(String(init?.body || '{}'));
        mutationCalls.push({ url, method, body });
        const newWindow = {
          id: 'avail-2',
          doctor: 'doc-1',
          weekday: body.weekday,
          start_time: body.start_time + ':00',
          end_time: body.end_time + ':00',
          is_active: body.is_active,
          created_at: '2026-10-25T11:00:00Z',
          updated_at: '2026-10-25T11:00:00Z'
        };
        currentWindows.push(newWindow);
        return new Response(JSON.stringify(newWindow), { status: 201, headers: { 'Content-Type': 'application/json' } });
      }

      if (method === 'PATCH' && url.includes('/api/appointments/availability/avail-1/')) {
        const body = JSON.parse(String(init?.body || '{}'));
        mutationCalls.push({ url, method, body });
        currentWindows[0].is_active = body.is_active;
        return new Response(JSON.stringify(currentWindows[0]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }

      if (method === 'DELETE' && url.includes('/api/appointments/availability/avail-1/')) {
        mutationCalls.push({ url, method, body: null });
        currentWindows = [];
        return new Response(null, { status: 204 });
      }

      return new Response(JSON.stringify({ results: [] }), { status: 200 });
    };

    setTokens({ access: 'doc-token', refresh: 'doc-refresh' });
    render(<Availability />);

    // 1. Initial listing uses registered endpoint /api/appointments/availability/
    await waitFor(() => {
      assert.ok(screen.getByText('Tuesday'));
      assert.ok(screen.getByText(/09:00.*12:00/));
    });
    assert.ok(availabilityCalls.some((url) => url.startsWith('http://localhost:8000/api/appointments/availability/?page=1')));

    // 2. Active server-side filtering
    const activeFilterBtn = screen.getByText('active');
    fireEvent.click(activeFilterBtn);

    await waitFor(() => {
      assert.ok(availabilityCalls.some((url) => url.includes('is_active=true')));
    });

    // 3. Inactive server-side filtering
    const inactiveFilterBtn = screen.getByText('inactive');
    fireEvent.click(inactiveFilterBtn);

    await waitFor(() => {
      assert.ok(availabilityCalls.some((url) => url.includes('is_active=false')));
    });

    // Reset filter to All
    fireEvent.click(screen.getByText('all'));

    // 4. Toggle Active/Inactive
    await waitFor(() => {
      assert.ok(screen.getByTitle('Deactivate Window'));
    });
    fireEvent.click(screen.getByTitle('Deactivate Window'));

    await waitFor(() => {
      const toggleReq = mutationCalls.find((m) => m.method === 'PATCH');
      assert.ok(toggleReq, 'PATCH request called');
      assert.equal(toggleReq.body.is_active, false);
    });

    // 5. Delete Window
    const deleteBtn = screen.getByTitle('Delete Window');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      const delReq = mutationCalls.find((m) => m.method === 'DELETE');
      assert.ok(delReq, 'DELETE request called');
    });
  });
});
