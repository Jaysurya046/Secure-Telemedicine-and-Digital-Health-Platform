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
  User,
  Video
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

export function Appointments({ onNavigateConsultation }: { onNavigateConsultation?: (roomId: string) => void }) {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [page, setPage] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);

  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string>('');
  const [feedbackError, setFeedbackError] = useState<string>('');

  // Cancel modal
  const [cancellingAppointment, setCancellingAppointment] = useState<Appointment | null>(null);
  const [cancellationReason, setCancellationReason] = useState<string>('');

  useEffect(() => {
    loadAppointments(1, statusFilter);
  }, [statusFilter]);

  async function loadAppointments(pageNumber: number = 1, currentFilter: StatusFilter = statusFilter) {
    setLoading(true);
    setFeedbackError('');
    try {
      let url = `/api/appointments/?page=${pageNumber}`;
      if (currentFilter !== 'all') {
        url += `&status=${currentFilter}`;
      }
      const data = await apiFetch<any>(url);
      if (Array.isArray(data)) {
        setAppointments(data);
        setTotalCount(data.length);
      } else {
        setAppointments(data.results || []);
        setTotalCount(data.count || (data.results || []).length);
      }
      setPage(pageNumber);
    } catch (err: any) {
      setFeedbackError(err.message || 'Failed to load appointments.');
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
      await loadAppointments(page);
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
      await loadAppointments(page);
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
      await loadAppointments(page);
    } catch (err: any) {
      setFeedbackError(err.message || 'Failed to cancel appointment.');
    } finally {
      setActionInProgress(null);
    }
  }

  function renderStatusBadge(status: string) {
    const badgeStyle: Record<string, { bg: string; color: string; label: string }> = {
      pending: { bg: '#fef3c7', color: '#92400e', label: 'Pending' },
      confirmed: { bg: '#d1fae5', color: '#065f46', label: 'Confirmed' },
      completed: { bg: '#e0f2fe', color: '#0369a1', label: 'Completed' },
      cancelled: { bg: '#ffe4e6', color: '#9f1239', label: 'Cancelled' },
      no_show: { bg: '#f1f5f9', color: '#475569', label: 'No Show' }
    };
    const b = badgeStyle[status] || badgeStyle.pending;
    return (
      <span
        style={{
          background: b.bg,
          color: b.color,
          padding: '0.2rem 0.6rem',
          borderRadius: '999px',
          fontSize: '0.75rem',
          fontWeight: 700
        }}
      >
        {b.label}
      </span>
    );
  }

  return (
    <section className="stack">
      <div className="panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 900, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <CalendarCheck size={22} color="#2f9e8f" />
              Appointment Queue
            </h2>
            <span className="muted">{totalCount} total appointment{totalCount === 1 ? '' : 's'}</span>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button
              className="icon-button"
              onClick={() => loadAppointments(page)}
              disabled={loading}
              title="Refresh queue"
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '1rem', borderTop: '1px solid #e2e8f0', paddingTop: '0.75rem' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.85rem', fontWeight: 700, color: '#64748b', marginRight: '0.5rem' }}>
            <Filter size={14} /> Filter:
          </span>
          {(['all', 'pending', 'confirmed', 'completed', 'cancelled'] as StatusFilter[]).map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid',
                borderColor: statusFilter === st ? '#2f9e8f' : '#cbd5e1',
                background: statusFilter === st ? '#e6f7f5' : '#ffffff',
                color: statusFilter === st ? '#0f766e' : '#334155',
                fontSize: '0.8rem',
                fontWeight: 700,
                cursor: 'pointer',
                textTransform: 'capitalize'
              }}
            >
              {st}
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
                {appt.status === 'confirmed' && onNavigateConsultation && (
                  <button
                    className="icon-button"
                    style={{ background: '#ecfdf5', color: '#065f46', borderColor: '#a7f3d0', fontSize: '0.8rem' }}
                    onClick={() => onNavigateConsultation(appt.id)}
                  >
                    <Video size={14} /> Open Consult
                  </button>
                )}

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
                    className="danger"
                    style={{ fontSize: '0.8rem', minHeight: '2.2rem', padding: '0.4rem 0.8rem' }}
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

          {/* Pagination */}
          {totalCount > 10 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0' }}>
              <button
                className="icon-button"
                disabled={page <= 1}
                onClick={() => loadAppointments(page - 1)}
              >
                <ChevronLeft size={16} /> Prev
              </button>
              <span className="muted" style={{ fontWeight: 700 }}>Page {page}</span>
              <button
                className="icon-button"
                disabled={page * 10 >= totalCount}
                onClick={() => loadAppointments(page + 1)}
              >
                Next <ChevronRight size={16} />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Cancel Prompt Modal */}
      {cancellingAppointment && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.45)', backdropFilter: 'blur(3px)', display: 'grid', placeItems: 'center', zIndex: 100, padding: '1rem' }}>
          <div className="panel" style={{ width: '100%', maxWidth: '28rem', display: 'grid', gap: '0.8rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong style={{ fontSize: '1.1rem' }}>Cancel Appointment</strong>
              <button className="icon-button icon-only" onClick={() => setCancellingAppointment(null)}><X size={16} /></button>
            </div>
            <p className="muted" style={{ margin: 0 }}>
              Cancel appointment with <strong>{cancellingAppointment.patient_detail?.profile?.full_name || cancellingAppointment.patient_detail?.email}</strong>?
            </p>
            <form onSubmit={handleCancelSubmit} style={{ display: 'grid', gap: '0.8rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', marginBottom: '0.25rem' }}>Cancellation Reason (optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Doctor emergency, patient requested cancel"
                  value={cancellationReason}
                  onChange={(e) => setCancellationReason(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                <button type="button" className="icon-button" onClick={() => setCancellingAppointment(null)}>Keep Appointment</button>
                <button type="submit" className="danger" disabled={actionInProgress === cancellingAppointment.id}>
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
