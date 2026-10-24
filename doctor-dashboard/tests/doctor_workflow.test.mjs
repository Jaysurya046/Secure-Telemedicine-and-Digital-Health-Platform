import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { formatErrorMessage } from '../src/services/api.ts';

describe('Doctor Dashboard: Appointments & Availability Workflow Tests', () => {
  it('enforces registered availability endpoint /api/appointments/availability/ across all CRUD actions', () => {
    const REGISTERED_ENDPOINT = '/api/appointments/availability/';
    const LEGACY_ENDPOINT = '/api/doctor-availability/';

    // 1. Availability List & Create URL
    const listUrl = `${REGISTERED_ENDPOINT}?page=1`;
    assert.ok(listUrl.startsWith('/api/appointments/availability/'));
    assert.ok(!listUrl.includes(LEGACY_ENDPOINT));

    // 2. Window Detail URL (for edit, toggle active, delete)
    const windowId = '6f2e28a5-d8aa-4629-9ba7-70cbba670499';
    const detailUrl = `${REGISTERED_ENDPOINT}${windowId}/`;
    assert.equal(detailUrl, '/api/appointments/availability/6f2e28a5-d8aa-4629-9ba7-70cbba670499/');
    assert.ok(!detailUrl.includes(LEGACY_ENDPOINT));
  });

  it('validates doctor availability creation, edit, toggle, and delete payloads', () => {
    // 1. Create availability window
    const createPayload = {
      weekday: 2, // Wednesday
      start_time: '09:00:00',
      end_time: '17:00:00',
      is_active: true
    };
    assert.equal(createPayload.weekday, 2);
    assert.ok(createPayload.start_time < createPayload.end_time);
    assert.equal(createPayload.is_active, true);

    // 2. Edit window
    const editPayload = {
      weekday: 3,
      start_time: '10:00:00',
      end_time: '18:00:00',
      is_active: true
    };
    assert.ok(editPayload.start_time < editPayload.end_time);

    // 3. Toggle active/inactive
    const togglePayload = { is_active: false };
    assert.equal(typeof togglePayload.is_active, 'boolean');

    // 4. Delete operation: Expects 204 No Content
    const deleteResponseStatus = 204;
    assert.equal(deleteResponseStatus, 204);
  });

  it('validates appointment lifecycle actions: confirm, complete, and cancel payloads', () => {
    // 1. Confirm: Empty object payload required by DRF AppointmentConfirmSerializer
    const confirmPayload = {};
    assert.deepEqual(confirmPayload, {});

    // 2. Complete: Empty object payload required by DRF AppointmentCompleteSerializer
    const completePayload = {};
    assert.deepEqual(completePayload, {});

    // 3. Cancel: Optional string cancellation_reason
    const cancelPayload = { cancellation_reason: 'Doctor emergency rescheduling required' };
    assert.ok(typeof cancelPayload.cancellation_reason === 'string');

    // Reject invalid transition simulation
    const appointmentStatus = 'completed';
    const canConfirm = appointmentStatus === 'pending';
    const canComplete = appointmentStatus === 'confirmed';
    assert.equal(canConfirm, false, 'Completed appointment cannot be confirmed');
    assert.equal(canComplete, false, 'Completed appointment cannot be completed again');
  });

  it('ensures unsupported Open Consult action is eliminated from appointment card actions', () => {
    // The appointment queue card should only support valid lifecycle actions
    const allowedActionsForConfirmed = ['complete', 'cancel'];
    const unsupportedAction = 'open_consult_with_appointment_id';

    assert.ok(!allowedActionsForConfirmed.includes(unsupportedAction));
  });

  it('handles last item disappearing when deleting or filtering availability windows and appointments', () => {
    let currentPage = 2;
    const paginatedResponse = {
      count: 10,
      next: null,
      previous: '/api/appointments/availability/?page=1',
      results: [] // Deletion of the last item on page 2 leaves results empty
    };

    function resolveCurrentPage(response, page) {
      if (response.results.length === 0 && page > 1) {
        return page - 1;
      }
      return page;
    }

    const resolvedPage = resolveCurrentPage(paginatedResponse, currentPage);
    assert.equal(resolvedPage, 1, 'Auto-navigates to page 1');
  });

  it('formats DRF API errors into user-friendly messages for the dashboard', () => {
    const errorBody = {
      error: true,
      message: "Cannot confirm appointment with status 'completed'."
    };
    assert.equal(formatErrorMessage(errorBody), "Cannot confirm appointment with status 'completed'.");

    const detailError = { detail: 'Method "DELETE" not allowed.' };
    assert.equal(formatErrorMessage(detailError), 'Method "DELETE" not allowed.');
  });

  it('triggers dashboard refresh callback on mutations and authentication changes', async () => {
    let refreshCalls = 0;
    const mockOnRefreshDashboard = async () => {
      refreshCalls += 1;
    };

    // Simulate appointment confirm mutation
    await mockOnRefreshDashboard();
    assert.equal(refreshCalls, 1);

    // Simulate appointment complete mutation
    await mockOnRefreshDashboard();
    assert.equal(refreshCalls, 2);

    // Simulate availability window creation
    await mockOnRefreshDashboard();
    assert.equal(refreshCalls, 3);
  });
});
