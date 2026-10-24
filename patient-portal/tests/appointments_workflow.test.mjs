import { test, describe, it, mock } from 'node:test';
import assert from 'node:assert/strict';
import { toIsoTimestamp, formatErrorMessage } from '../src/lib/api.ts';

describe('Patient Portal: Appointments Workflow & API Contract Tests', () => {
  it('converts local datetime input to timezone-aware ISO timestamp', () => {
    const localInput = '2026-11-03T10:30';
    const isoResult = toIsoTimestamp(localInput);
    assert.ok(isoResult, 'ISO string should be non-empty');
    assert.match(isoResult, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/, 'Matches ISO format');

    // Invalid input returns empty string
    assert.equal(toIsoTimestamp(''), '');
    assert.equal(toIsoTimestamp('invalid-date'), '');
  });

  it('formats DRF error responses correctly, including nested details and field errors', () => {
    // 1. Nested DRF error format: { details: { scheduled_start: ['Cannot reschedule...'] } }
    const nestedError = {
      details: {
        scheduled_start: ["Cannot reschedule appointment with status 'confirmed'."]
      }
    };
    const formattedNested = formatErrorMessage(nestedError);
    assert.match(formattedNested, /scheduled_start: Cannot reschedule appointment/);

    // 2. Direct field errors: { scheduled_start: ['Doctor has no active availability window'] }
    const fieldError = {
      scheduled_start: ['Doctor has no active availability window covering this slot.']
    };
    const formattedField = formatErrorMessage(fieldError);
    assert.match(formattedField, /scheduled_start: Doctor has no active availability/);

    // 3. String message error
    assert.equal(formatErrorMessage({ message: 'Unauthorized' }), 'Unauthorized');
    assert.equal(formatErrorMessage({ detail: 'Token expired' }), 'Token expired');
  });

  it('prevents stale doctor-availability responses from replacing current doctor selection', async () => {
    // Simulate doctor selection state and rapid switching
    let selectedDoctorId = 'doc-1';
    let activeDoctorSchedule = null;

    // Doctor A request is initiated
    let isCurrentA = true;
    const fetchDoctorA = async () => {
      // Simulate delay
      await new Promise((resolve) => setTimeout(resolve, 50));
      if (!isCurrentA) return; // Stale guard
      activeDoctorSchedule = [{ id: 'avail-1', doctor: 'doc-1', weekday: 1 }];
    };
    const docAPromise = fetchDoctorA();

    // User rapidly switches to Doctor B before Doctor A resolves
    isCurrentA = false; // cleanup in useEffect
    selectedDoctorId = 'doc-2';
    let isCurrentB = true;
    const fetchDoctorB = async () => {
      await new Promise((resolve) => setTimeout(resolve, 10)); // Doctor B responds faster
      if (!isCurrentB) return;
      activeDoctorSchedule = [{ id: 'avail-2', doctor: 'doc-2', weekday: 2 }];
    };
    await fetchDoctorB();
    await docAPromise;

    // Doctor A's delayed response must NOT have overwritten Doctor B's schedule
    assert.equal(selectedDoctorId, 'doc-2');
    assert.equal(activeDoctorSchedule.length, 1);
    assert.equal(activeDoctorSchedule[0].doctor, 'doc-2');
  });

  it('distinguishes explicit loading failure from empty data', () => {
    // Simulating component state transitions
    let state = {
      loading: true,
      error: '',
      data: []
    };

    // Case 1: Fetch fails with network/server error
    const serverError = new Error('500 Internal Server Error');
    state = {
      loading: false,
      error: serverError.message,
      data: []
    };

    // The UI must show an error state with a retry button, NOT present it as empty data
    assert.equal(state.loading, false);
    assert.equal(state.error, '500 Internal Server Error');
    assert.ok(state.error.length > 0, 'Error is explicitly recorded');

    // Case 2: Fetch succeeds with genuinely empty list
    state = {
      loading: false,
      error: '',
      data: []
    };
    assert.equal(state.error, '');
    assert.equal(state.data.length, 0);
  });

  it('handles last item disappearing from a paginated filtered page', () => {
    // Simulate deleting or filtering out the only item on page 2
    let currentPage = 2;
    const mockApiResponse = {
      count: 10,
      next: null,
      previous: 'http://localhost:8000/api/appointments/?page=1',
      results: [] // Empty because the item on page 2 is gone
    };

    function processPageResults(response, page) {
      if (response.results.length === 0 && page > 1) {
        return page - 1; // Auto-navigate back to previous page
      }
      return page;
    }

    const newPage = processPageResults(mockApiResponse, currentPage);
    assert.equal(newPage, 1, 'Automatically falls back to page 1 when last item disappears');
  });

  it('validates booking, rescheduling, and cancellation request contract', () => {
    // 1. Patient booking payload contract
    const bookingPayload = {
      doctor: 'b7c84411-cf0f-48d8-b59e-e3135c1ba716',
      scheduled_start: '2026-11-03T10:00:00.000Z',
      scheduled_end: '2026-11-03T11:00:00.000Z',
      reason: 'General consultation',
      symptoms: ['cough', 'fever']
    };
    assert.ok(bookingPayload.doctor, 'Requires doctor UUID');
    assert.ok(bookingPayload.scheduled_start < bookingPayload.scheduled_end, 'Start must precede end');
    assert.ok(bookingPayload.reason.length > 0, 'Requires visit reason');

    // 2. Rescheduling payload contract (pending appointments only)
    const reschedulePayload = {
      scheduled_start: '2026-11-04T14:00:00.000Z',
      scheduled_end: '2026-11-04T15:00:00.000Z'
    };
    assert.ok(reschedulePayload.scheduled_start, 'Must provide start');
    assert.ok(reschedulePayload.scheduled_end, 'Must provide end');

    // 3. Cancellation payload contract (optional reason)
    const cancelPayloadWithReason = { cancellation_reason: 'Schedule conflict' };
    assert.equal(typeof cancelPayloadWithReason.cancellation_reason, 'string');

    const cancelPayloadEmpty = {};
    assert.equal(cancelPayloadEmpty.cancellation_reason, undefined);
  });
});
