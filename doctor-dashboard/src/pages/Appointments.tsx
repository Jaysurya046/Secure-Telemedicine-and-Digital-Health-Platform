import { useState, useEffect } from 'react';
import type { FormEvent } from 'react';
import {
  CalendarCheck,
  Check,
  X,
  Clock,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Filter,
  User
} from 'lucide-react';
import { apiFetch } from '../services/api';

type StatusFilter = 'all' | 'pending' | 'confirmed' | 'completed' | 'cancelled';

type Appointment = {
  id: string;
  doctor: string;
  patient: string;
  patient_detail?: {
    email: string;
    profile?: {
      first_name?: string;
      last_name?: string;
      full_name?: string;
      phone?: string;
    };
  };
  scheduled_start: string;
  scheduled_end: string;
  status: 'pending' | 'confirmed' | 'cancelled' | 'completed' | 'no_show';
  reason: string;
  symptoms?: string[];
  notes?: string;
  cancellation_reason?: string;
  meeting_link?: string;
  created_at: string;
};

export function Appointments({ onRefreshDashboard }: { onRefreshDashboard?: () => Promise<void> | void }) {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadingError, setLoadingError] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [page, setPage] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [hasNextPage, setHasNextPage] = useState<boolean>(false);
  const [hasPrevPage, setHasPrevPage] = useState<boolean>(false);

  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string>('');
  const [feedbackError, setFeedbackError] = useState<string>('');

  // Cancel modal
  const [cancellingAppointment, setCancellingAppointment] = useState<Appointment | null>(null);
  const [cancellationReason, setCancellationReason] = useState<string>('');

  useEffect(() => {
    loadAppointments(1, statusFilter);
  }, [statusFilter]);

  async function loadAppointments(pageNumber: number = page, currentFilter: StatusFilter = statusFilter) {
    setLoading(true);
    setLoadingError('');
    try {
      let url = `/api/appointments/?page=${pageNumber}`;
      if (currentFilter !== 'all') {
        url += `&status=${currentFilter}`;
      }
      const data = await apiFetch<any>(url);
      if (Array.isArray(data)) {
        setAppointments(data);
        setTotalCount(data.length);
        setHasNextPage(false);
        setHasPrevPage(false);
        setPage(1);
      } else {
        const results = data.results || [];
        const count = data.count !== undefined ? data.count : results.length;

        // Handle the last item disappearing from a filtered/subsequent page
        if (results.length === 0 && pageNumber > 1) {
          return loadAppointments(pageNumber - 1, currentFilter);
        }

        setAppointments(results);
        setTotalCount(count);
        setHasNextPage(Boolean(data.next));
        setHasPrevPage(Boolean(data.previous));
        setPage(pageNumber);
      }
    } catch (err: any) {
      setLoadingError(err.message || 'Failed to load appointments.');
      setAppointments([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm(apptId: string) {
    setActionInProgress(apptId);
    setFeedbackError('');
    setFeedbackSuccess('');
    try {
      await apiFetch(`/api/appointments/${apptId}/confirm/`, {
        method: 'POST',
        body: JSON.stringify({})
      });
      setFeedbackSuccess('Appointment confirmed successfully.');
      await loadAppointments(page, statusFilter);
      if (onRefreshDashboard) await onRefreshDashboard();
    } catch (err: any) {
      setFeedbackError(err.message || 'Failed to confirm appointment.');
    } finally {
      setActionInProgress(null);
    }
  }

  async function handleComplete(apptId: string) {
    setActionInProgress(apptId);
    setFeedbackError('');
    setFeedbackSuccess('');
    try {
      await apiFetch(`/api/appointments/${apptId}/complete/`, {
        method: 'POST',
        body: JSON.stringify({})
      });
      setFeedbackSuccess('Appointment marked as completed.');
      await loadAppointments(page, statusFilter);
      if (onRefreshDashboard) await onRefreshDashboard();
    } catch (err: any) {
      setFeedbackError(err.message || 'Failed to complete appointment.');
    } finally {
      setActionInProgress(null);
    }
  }

  async function handleCancelSubmit(event: FormEvent) {
    event.preventDefault();
    if (!cancellingAppointment) return;
    const apptId = cancellingAppointment.id;
    setActionInProgress(apptId);
    setFeedbackError('');
    setFeedbackSuccess('');
    try {
      await apiFetch(`/api/appointments/${apptId}/cancel/`, {
        method: 'POST',
        body: JSON.stringify({ cancellation_reason: cancellationReason })
      });
      setFeedbackSuccess('Appointment cancelled successfully.');
      setCancellingAppointment(null);
      setCancellationReason('');
      await loadAppointments(page, statusFilter);
      if (onRefreshDashboard) await onRefreshDashboard();
    } catch (err: any) {
      setFeedbackError(err.message || 'Failed to cancel appointment.');
    } finally {
      setActionInProgress(null);
    }
  }

  function renderStatusBadge(status: string) {
    const map: Record<string, { bg: string; color: string; label: string }> = {
      pending: { bg: '#fef3c7', color: '#92400e', label: 'Pending' },
      confirmed: { bg: '#d1fae5', color: '#065f46', label: 'Confirmed' },
      completed: { bg: '#e0f2fe', color: '#0369a1', label: 'Completed' },
      cancelled: { bg: '#ffe4e6', color: '#9f1239', label: 'Cancelled' },
      no_show: { bg: '#f1f5f9', color: '#475569', label: 'No Show' }
    };
    const s = map[status] || map.pending;
    return (
      <span
        style={{
          background: s.bg,
          color: s.color,
          fontSize: '0.75rem',
          fontWeight: 700,
          padding: '0.2rem 0.6rem',
          borderRadius: '999px',
          textTransform: 'capitalize'
        }}
      >
        {s.label}
      </span>
    );
  }

  return (
    <section className="stack">
      {/* Top Controls & Banner */}
      <div className="panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 900, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <CalendarCheck size={22} color="#2f9e8f" />
              Appointment Queue
            </h2>
            <span className="muted">{totalCount} total appointment{totalCount === 1 ? '' : 's'}</span>
          </div>

          <button className="icon-button" onClick={() => loadAppointments(page, statusFilter)} disabled={loading} title="Refresh appointments">
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {/* Filter pills */}
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', borderTop: '1px solid #e2e8f0', paddingTop: '0.75rem', flexWrap: 'wrap' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.8rem', fontWeight: 700, color: '#64748b', marginRight: '0.5rem' }}>
            <Filter size={14} /> Filter:
          </span>
          {(['all', 'pending', 'confirmed', 'completed', 'cancelled'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => {
                setStatusFilter(mode);
                setPage(1);
              }}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid',
                borderColor: statusFilter === mode ? '#2f9e8f' : '#cbd5e1',
                background: statusFilter === mode ? '#e6f7f5' : '#ffffff',
                color: statusFilter === mode ? '#0f766e' : '#334155',
                fontSize: '0.8rem',
                fontWeight: 700,
                cursor: 'pointer',
                textTransform: 'capitalize'
              }}
            >
              {mode}
            </button>
          ))}
        </div>

        {feedbackSuccess && (
          <div style={{ marginTop: '0.75rem', padding: '0.6rem 0.9rem', background: '#ecfdf5', color: '#065f46', borderRadius: '6px', fontSize: '0.85rem', fontWeight: 600, border: '1px solid #a7f3d0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <CheckCircle2 size={16} />
            <span>{feedbackSuccess}</span>
          </div>
        )}

        {feedbackError && (
          <div style={{ marginTop: '0.75rem', padding: '0.6rem 0.9rem', background: '#fff1f2', color: '#be123c', borderRadius: '6px', fontSize: '0.85rem', fontWeight: 600, border: '1px solid #fecdd3', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertCircle size={16} />
            <span>{feedbackError}</span>
          </div>
        )}
      </div>

      {/* Appointment Cards */}
      {loading ? (
        <div className="panel" style={{ textAlign: 'center', padding: '2rem' }}>
          <RefreshCw size={24} color="#2f9e8f" className="animate-spin" style={{ margin: '0 auto 0.5rem' }} />
          <p className="muted">Loading appointment queue...</p>
        </div>
      ) : loadingError ? (
        <div className="panel" style={{ textAlign: 'center', padding: '2rem', border: '1px solid #fecdd3', background: '#fff1f2' }}>
          <AlertCircle size={32} color="#be123c" style={{ margin: '0 auto 0.5rem' }} />
          <p style={{ fontWeight: 700, color: '#be123c', margin: '0.5rem 0' }}>{loadingError}</p>
          <button className="primary" onClick={() => loadAppointments(page, statusFilter)} style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
            <RefreshCw size={14} /> Retry Loading
          </button>
        </div>
      ) : appointments.length === 0 ? (
        <div className="panel" style={{ textAlign: 'center', padding: '3rem' }}>
          <CalendarCheck size={36} color="#94a3b8" style={{ margin: '0 auto 0.5rem' }} />
          <p style={{ fontWeight: 700, margin: '0.5rem 0 0.2rem' }}>No appointments found</p>
          <span className="muted">No records match the current status filter.</span>
        </div>
      ) : (
        <div className="stack">
          {appointments.map((appt) => (
            <article key={appt.id} className="panel" style={{ display: 'grid', gap: '0.6rem', padding: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div>
                  <strong style={{ fontSize: '1.05rem', color: '#0f172a' }}>
                    {appt.patient_detail?.profile?.full_name || appt.patient_detail?.email || 'Patient'}
                  </strong>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', color: '#64748b', marginTop: '0.1rem' }}>
                    <User size={13} />
                    <span>{appt.patient_detail?.email} {appt.patient_detail?.profile?.phone ? `· ${appt.patient_detail.profile.phone}` : ''}</span>
                  </div>
                </div>
                {renderStatusBadge(appt.status)}
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', fontSize: '0.85rem', color: '#475569', background: '#f8fafc', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                  <Clock size={14} color="#64748b" />
                  <strong>Schedule:</strong> {new Date(appt.scheduled_start).toLocaleString()} - {new Date(appt.scheduled_end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
                <span><strong>Reason:</strong> {appt.reason}</span>
                {appt.symptoms && appt.symptoms.length > 0 && (
                  <span><strong>Symptoms:</strong> {appt.symptoms.join(', ')}</span>
                )}
              </div>

              {appt.cancellation_reason && (
                <div style={{ fontSize: '0.8rem', color: '#9f1239', background: '#fff1f2', padding: '0.4rem 0.6rem', borderRadius: '4px', border: '1px solid #ffe4e6' }}>
                  <strong>Cancellation reason:</strong> {appt.cancellation_reason}
                </div>
              )}

              {/* Action Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '0.5rem', borderTop: '1px solid #f1f5f9', paddingTop: '0.6rem', marginTop: '0.3rem' }}>
                {appt.status === 'pending' && (
                  <button
                    className="primary"
                    style={{ fontSize: '0.8rem', minHeight: '2.2rem', padding: '0.4rem 0.8rem' }}
                    disabled={actionInProgress === appt.id}
                    onClick={() => handleConfirm(appt.id)}
                  >
                    <Check size={14} />
                    {actionInProgress === appt.id ? 'Confirming...' : 'Confirm'}
                  </button>
                )}

                {appt.status === 'confirmed' && (
                  <button
                    className="primary"
                    style={{ background: '#0284c7', fontSize: '0.8rem', minHeight: '2.2rem', padding: '0.4rem 0.8rem' }}
                    disabled={actionInProgress === appt.id}
                    onClick={() => handleComplete(appt.id)}
                  >
                    <Check size={14} />
                    {actionInProgress === appt.id ? 'Completing...' : 'Mark Complete'}
                  </button>
                )}

                {(appt.status === 'pending' || appt.status === 'confirmed') && (
                  <button
                    className="icon-button"
                    style={{ color: '#be123c', borderColor: '#fecdd3', fontSize: '0.8rem', minHeight: '2.2rem', padding: '0.4rem 0.8rem' }}
                    disabled={actionInProgress === appt.id}
                    onClick={() => {
                      setCancellingAppointment(appt);
                      setCancellationReason('');
                    }}
                  >
                    <X size={14} />
                    Cancel
                  </button>
                )}
              </div>
            </article>
          ))}

          {/* Working Pagination controls using API next/previous metadata */}
          {(hasPrevPage || hasNextPage || totalCount > 10) && (
            <div className="panel" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.8rem 1rem' }}>
              <button
                className="icon-button"
                disabled={!hasPrevPage && page <= 1}
                onClick={() => loadAppointments(page - 1, statusFilter)}
                style={{ fontSize: '0.85rem' }}
              >
                <ChevronLeft size={16} /> Previous
              </button>
              <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#475569' }}>
                Page {page}
              </span>
              <button
                className="icon-button"
                disabled={!hasNextPage}
                onClick={() => loadAppointments(page + 1, statusFilter)}
                style={{ fontSize: '0.85rem' }}
              >
                Next <ChevronRight size={16} />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Cancel Modal */}
      {cancellingAppointment && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.45)', backdropFilter: 'blur(3px)', display: 'grid', placeItems: 'center', zIndex: 100, padding: '1rem' }}>
          <div className="panel" style={{ width: '100%', maxWidth: '28rem', display: 'grid', gap: '0.8rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong style={{ fontSize: '1.1rem' }}>Cancel Appointment</strong>
              <button className="icon-button icon-only" onClick={() => setCancellingAppointment(null)}><X size={16} /></button>
            </div>

            <form onSubmit={handleCancelSubmit} style={{ display: 'grid', gap: '0.8rem' }}>
              <p style={{ margin: 0, fontSize: '0.9rem', color: '#475569' }}>
                Are you sure you want to cancel the appointment for <strong>{cancellingAppointment.patient_detail?.profile?.full_name || cancellingAppointment.patient_detail?.email || 'this patient'}</strong>?
              </p>

              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', marginBottom: '0.25rem' }}>
                  Cancellation Reason (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Doctor emergency, patient request"
                  value={cancellationReason}
                  onChange={(e) => setCancellationReason(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
                <button type="button" className="icon-button" onClick={() => setCancellingAppointment(null)}>Go Back</button>
                <button type="submit" className="primary" style={{ background: '#be123c' }} disabled={actionInProgress === cancellingAppointment.id}>
                  {actionInProgress === cancellingAppointment.id ? 'Cancelling...' : 'Confirm Cancellation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
