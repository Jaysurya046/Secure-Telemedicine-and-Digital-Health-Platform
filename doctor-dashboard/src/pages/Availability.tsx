import { useState, useEffect, useRef } from 'react';
import type { FormEvent } from 'react';
import {
  Clock,
  Plus,
  Trash2,
  Edit2,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Power,
  X,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';
import { apiFetch, isInvalidPageError } from '../services/api';

const WEEKDAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday'
];

type AvailabilityWindow = {
  id: string;
  doctor: string;
  weekday: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export function Availability({ onRefreshDashboard }: { onRefreshDashboard?: () => Promise<void> | void }) {
  const [windows, setWindows] = useState<AvailabilityWindow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [filterActive, setFilterActive] = useState<'all' | 'active' | 'inactive'>('all');
  const [page, setPage] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [hasNextPage, setHasNextPage] = useState<boolean>(false);
  const [hasPrevPage, setHasPrevPage] = useState<boolean>(false);

  const [feedbackSuccess, setFeedbackSuccess] = useState<string>('');
  const [feedbackError, setFeedbackError] = useState<string>('');
  const [loadingError, setLoadingError] = useState<string>('');

  // Create Form State
  const [showCreateForm, setShowCreateForm] = useState<boolean>(false);
  const [createForm, setCreateForm] = useState({
    weekday: 0,
    start_time: '09:00',
    end_time: '17:00',
    is_active: true
  });
  const [isSubmittingCreate, setIsSubmittingCreate] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string>('');

  // Edit Modal State
  const [editingWindow, setEditingWindow] = useState<AvailabilityWindow | null>(null);
  const [editForm, setEditForm] = useState({
    weekday: 0,
    start_time: '09:00',
    end_time: '17:00',
    is_active: true
  });
  const [isSubmittingEdit, setIsSubmittingEdit] = useState<boolean>(false);
  const [editError, setEditError] = useState<string>('');

  // Delete Action In Progress
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const activeReqIdRef = useRef<number>(0);

  useEffect(() => {
    loadAvailability(1, filterActive);
  }, []);

  async function loadAvailability(
    pageNumber: number = page,
    currentFilter: 'all' | 'active' | 'inactive' = filterActive
  ) {
    const reqId = ++activeReqIdRef.current;
    setLoading(true);
    setLoadingError('');
    try {
      // Backend DoctorAvailabilityViewSet is registered at /api/appointments/availability/
      // Server-side filtering by is_active is applied before pagination
      let url = `/api/appointments/availability/?page=${pageNumber}`;
      if (currentFilter === 'active') {
        url += '&is_active=true';
      } else if (currentFilter === 'inactive') {
        url += '&is_active=false';
      }

      const data = await apiFetch<any>(url);
      if (reqId !== activeReqIdRef.current) return;

      if (Array.isArray(data)) {
        setWindows(data);
        setTotalCount(data.length);
        setHasNextPage(false);
        setHasPrevPage(false);
        setPage(1);
      } else {
        const results = data.results || [];
        const count = data.count !== undefined ? data.count : results.length;

        // Handle the last item disappearing from a filtered/subsequent page
        if (results.length === 0 && pageNumber > 1) {
          return loadAvailability(pageNumber - 1, currentFilter);
        }

        setWindows(results);
        setTotalCount(count);
        setHasNextPage(Boolean(data.next));
        setHasPrevPage(Boolean(data.previous));
        setPage(pageNumber);
      }
    } catch (err: any) {
      if (reqId !== activeReqIdRef.current) return;
      if (isInvalidPageError(err) && pageNumber > 1) {
        return loadAvailability(pageNumber - 1, currentFilter);
      }
      setLoadingError(err.message || 'Failed to load availability windows.');
      setWindows([]);
    } finally {
      if (reqId === activeReqIdRef.current) {
        setLoading(false);
      }
    }
  }

  function handleFilterChange(mode: 'all' | 'active' | 'inactive') {
    setFilterActive(mode);
    setPage(1);
    loadAvailability(1, mode);
  }

  async function handleCreateSubmit(event: FormEvent) {
    event.preventDefault();
    setCreateError('');
    setFeedbackSuccess('');

    if (createForm.end_time <= createForm.start_time) {
      setCreateError('End time must be strictly after start time.');
      return;
    }

    setIsSubmittingCreate(true);
    try {
      const startTimeFormatted = createForm.start_time.length === 5 ? `${createForm.start_time}:00` : createForm.start_time;
      const endTimeFormatted = createForm.end_time.length === 5 ? `${createForm.end_time}:00` : createForm.end_time;

      await apiFetch('/api/appointments/availability/', {
        method: 'POST',
        body: JSON.stringify({
          weekday: Number(createForm.weekday),
          start_time: startTimeFormatted,
          end_time: endTimeFormatted,
          is_active: createForm.is_active
        })
      });

      setFeedbackSuccess('Availability window created successfully.');
      setShowCreateForm(false);
      setCreateForm({ weekday: 0, start_time: '09:00', end_time: '17:00', is_active: true });
      await loadAvailability(page, filterActive);
      if (onRefreshDashboard) await onRefreshDashboard();
    } catch (err: any) {
      setCreateError(err.message || 'Failed to create availability window.');
    } finally {
      setIsSubmittingCreate(false);
    }
  }

  async function handleEditSubmit(event: FormEvent) {
    event.preventDefault();
    if (!editingWindow) return;
    setEditError('');

    if (editForm.end_time <= editForm.start_time) {
      setEditError('End time must be strictly after start time.');
      return;
    }

    setIsSubmittingEdit(true);
    try {
      const startTimeFormatted = editForm.start_time.length === 5 ? `${editForm.start_time}:00` : editForm.start_time;
      const endTimeFormatted = editForm.end_time.length === 5 ? `${editForm.end_time}:00` : editForm.end_time;

      await apiFetch(`/api/appointments/availability/${editingWindow.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({
          weekday: Number(editForm.weekday),
          start_time: startTimeFormatted,
          end_time: endTimeFormatted,
          is_active: editForm.is_active
        })
      });

      setFeedbackSuccess('Availability window updated successfully.');
      setEditingWindow(null);
      await loadAvailability(page, filterActive);
      if (onRefreshDashboard) await onRefreshDashboard();
    } catch (err: any) {
      setEditError(err.message || 'Failed to update availability window.');
    } finally {
      setIsSubmittingEdit(false);
    }
  }

  async function handleToggleActive(windowItem: AvailabilityWindow) {
    setActionInProgress(windowItem.id);
    setFeedbackError('');
    setFeedbackSuccess('');
    try {
      await apiFetch(`/api/appointments/availability/${windowItem.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !windowItem.is_active })
      });
      setFeedbackSuccess(`Window set to ${!windowItem.is_active ? 'Active' : 'Inactive'}.`);
      await loadAvailability(page, filterActive);
      if (onRefreshDashboard) await onRefreshDashboard();
    } catch (err: any) {
      setFeedbackError(err.message || 'Failed to update window status.');
    } finally {
      setActionInProgress(null);
    }
  }

  async function handleDelete(windowId: string) {
    if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
      if (!window.confirm('Are you sure you want to delete this availability window?')) return;
    }
    setActionInProgress(windowId);
    setFeedbackError('');
    setFeedbackSuccess('');
    try {
      await apiFetch(`/api/appointments/availability/${windowId}/`, {
        method: 'DELETE'
      });
      setFeedbackSuccess('Availability window deleted.');
      await loadAvailability(page, filterActive);
      if (onRefreshDashboard) await onRefreshDashboard();
    } catch (err: any) {
      setFeedbackError(err.message || 'Failed to delete availability window.');
    } finally {
      setActionInProgress(null);
    }
  }

  return (
    <section className="stack">
      {/* Top Controls & Banner */}
      <div className="panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 900, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Clock size={22} color="#2f9e8f" />
              Doctor Availability Management
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.2rem' }}>
              <span className="muted">{totalCount} total window{totalCount === 1 ? '' : 's'} matching filter</span>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, background: '#f1f5f9', color: '#475569', padding: '0.15rem 0.5rem', borderRadius: '4px' }}>
                Timezone: UTC
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button className="primary" onClick={() => setShowCreateForm(!showCreateForm)}>
              <Plus size={16} />
              {showCreateForm ? 'Cancel New Window' : 'Add Availability Window'}
            </button>
            <button className="icon-button" onClick={() => loadAvailability(page, filterActive)} disabled={loading} title="Refresh windows">
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {/* Server-side Filter controls */}
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', borderTop: '1px solid #e2e8f0', paddingTop: '0.75rem' }}>
          {(['all', 'active', 'inactive'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => handleFilterChange(mode)}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid',
                borderColor: filterActive === mode ? '#2f9e8f' : '#cbd5e1',
                background: filterActive === mode ? '#e6f7f5' : '#ffffff',
                color: filterActive === mode ? '#0f766e' : '#334155',
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

      {/* Create Availability Form Panel */}
      {showCreateForm && (
        <form onSubmit={handleCreateSubmit} className="panel" style={{ display: 'grid', gap: '0.9rem', background: '#f8fafc', border: '1px solid #cbd5e1' }}>
          <strong style={{ fontSize: '1.1rem' }}>Define New Availability Window</strong>

          {createError && (
            <div style={{ padding: '0.5rem 0.8rem', background: '#fff1f2', color: '#be123c', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 600, border: '1px solid #fecdd3' }}>
              {createError}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(10rem, 1fr))', gap: '0.75rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', marginBottom: '0.25rem' }}>Weekday</label>
              <select
                value={createForm.weekday}
                onChange={(e) => setCreateForm({ ...createForm, weekday: Number(e.target.value) })}
                style={{ width: '100%', minHeight: '2.6rem', padding: '0.5rem', borderRadius: '8px', border: '1px solid #cbd5e1' }}
              >
                {WEEKDAYS.map((name, idx) => (
                  <option key={name} value={idx}>{name}</option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', marginBottom: '0.25rem' }}>Start Time (UTC)</label>
              <input
                type="time"
                value={createForm.start_time}
                onChange={(e) => setCreateForm({ ...createForm, start_time: e.target.value })}
                required
                style={{ width: '100%' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', marginBottom: '0.25rem' }}>End Time (UTC)</label>
              <input
                type="time"
                value={createForm.end_time}
                onChange={(e) => setCreateForm({ ...createForm, end_time: e.target.value })}
                required
                style={{ width: '100%' }}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '1.2rem' }}>
              <input
                type="checkbox"
                id="is_active_create"
                checked={createForm.is_active}
                onChange={(e) => setCreateForm({ ...createForm, is_active: e.target.checked })}
                style={{ minHeight: 'auto', width: '1.2rem', height: '1.2rem' }}
              />
              <label htmlFor="is_active_create" style={{ fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer' }}>Active for Booking</label>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
            <button type="button" className="icon-button" onClick={() => setShowCreateForm(false)}>Cancel</button>
            <button type="submit" className="primary" disabled={isSubmittingCreate}>
              {isSubmittingCreate ? 'Saving Window...' : 'Save Availability Window'}
            </button>
          </div>
        </form>
      )}

      {/* Availability Windows List */}
      {loading ? (
        <div className="panel" style={{ textAlign: 'center', padding: '2rem' }}>
          <RefreshCw size={24} color="#2f9e8f" className="animate-spin" style={{ margin: '0 auto 0.5rem' }} />
          <p className="muted">Loading availability windows...</p>
        </div>
      ) : loadingError ? (
        <div className="panel" style={{ textAlign: 'center', padding: '2rem', border: '1px solid #fecdd3', background: '#fff1f2' }}>
          <AlertCircle size={32} color="#be123c" style={{ margin: '0 auto 0.5rem' }} />
          <p style={{ fontWeight: 700, color: '#be123c', margin: '0.5rem 0' }}>{loadingError}</p>
          <button className="primary" onClick={() => loadAvailability(page, filterActive)} style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
            <RefreshCw size={14} /> Retry Loading
          </button>
        </div>
      ) : windows.length === 0 ? (
        <div className="panel" style={{ textAlign: 'center', padding: '3rem' }}>
          <Clock size={36} color="#94a3b8" style={{ margin: '0 auto 0.5rem' }} />
          <p style={{ fontWeight: 700, margin: '0.5rem 0 0.2rem' }}>No availability windows found</p>
          <span className="muted">Click &quot;Add Availability Window&quot; above to configure your consultation schedule.</span>
        </div>
      ) : (
        <div className="stack">
          {windows.map((item) => (
            <article
              key={item.id}
              className="panel"
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '0.75rem',
                borderLeft: item.is_active ? '4px solid #10b981' : '4px solid #cbd5e1'
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <strong style={{ fontSize: '1.1rem' }}>{WEEKDAYS[item.weekday]}</strong>
                  <span
                    style={{
                      background: item.is_active ? '#d1fae5' : '#f1f5f9',
                      color: item.is_active ? '#065f46' : '#64748b',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      padding: '0.15rem 0.55rem',
                      borderRadius: '999px'
                    }}
                  >
                    {item.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.9rem', color: '#475569', marginTop: '0.2rem' }}>
                  <Clock size={14} color="#64748b" />
                  <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{item.start_time.slice(0, 5)} - {item.end_time.slice(0, 5)} UTC</span>
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <button
                  className="icon-button"
                  style={{ fontSize: '0.8rem', color: item.is_active ? '#b45309' : '#065f46' }}
                  disabled={actionInProgress === item.id}
                  onClick={() => handleToggleActive(item)}
                  title={item.is_active ? 'Deactivate Window' : 'Activate Window'}
                >
                  <Power size={14} />
                  {item.is_active ? 'Deactivate' : 'Activate'}
                </button>

                <button
                  className="icon-button"
                  style={{ fontSize: '0.8rem' }}
                  onClick={() => {
                    setEditingWindow(item);
                    setEditForm({
                      weekday: item.weekday,
                      start_time: item.start_time.slice(0, 5),
                      end_time: item.end_time.slice(0, 5),
                      is_active: item.is_active
                    });
                    setEditError('');
                  }}
                  title="Edit Window"
                >
                  <Edit2 size={14} /> Edit
                </button>

                <button
                  className="icon-button"
                  style={{ fontSize: '0.8rem', color: '#be123c' }}
                  disabled={actionInProgress === item.id}
                  onClick={() => handleDelete(item.id)}
                  title="Delete Window"
                >
                  <Trash2 size={14} /> Delete
                </button>
              </div>
            </article>
          ))}

          {/* Working Pagination controls using API next/previous metadata */}
          {(hasPrevPage || hasNextPage || totalCount > 10) && (
            <div className="panel" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.8rem 1rem' }}>
              <button
                className="icon-button"
                disabled={!hasPrevPage || page <= 1}
                onClick={() => loadAvailability(page - 1, filterActive)}
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
                onClick={() => loadAvailability(page + 1, filterActive)}
                style={{ fontSize: '0.85rem' }}
              >
                Next <ChevronRight size={16} />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Edit Availability Modal */}
      {editingWindow && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.45)', backdropFilter: 'blur(3px)', display: 'grid', placeItems: 'center', zIndex: 100, padding: '1rem' }}>
          <div className="panel" style={{ width: '100%', maxWidth: '28rem', display: 'grid', gap: '0.8rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong style={{ fontSize: '1.1rem' }}>Edit Availability Window</strong>
              <button className="icon-button icon-only" onClick={() => setEditingWindow(null)}><X size={16} /></button>
            </div>

            {editError && (
              <div style={{ padding: '0.5rem 0.8rem', background: '#fff1f2', color: '#be123c', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 600, border: '1px solid #fecdd3' }}>
                {editError}
              </div>
            )}

            <form onSubmit={handleEditSubmit} style={{ display: 'grid', gap: '0.8rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', marginBottom: '0.25rem' }}>Weekday</label>
                <select
                  value={editForm.weekday}
                  onChange={(e) => setEditForm({ ...editForm, weekday: Number(e.target.value) })}
                  style={{ width: '100%', minHeight: '2.6rem', padding: '0.5rem', borderRadius: '8px', border: '1px solid #cbd5e1' }}
                >
                  {WEEKDAYS.map((name, idx) => (
                    <option key={name} value={idx}>{name}</option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', marginBottom: '0.25rem' }}>Start Time (UTC)</label>
                  <input
                    type="time"
                    value={editForm.start_time}
                    onChange={(e) => setEditForm({ ...editForm, start_time: e.target.value })}
                    required
                    style={{ width: '100%' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', marginBottom: '0.25rem' }}>End Time (UTC)</label>
                  <input
                    type="time"
                    value={editForm.end_time}
                    onChange={(e) => setEditForm({ ...editForm, end_time: e.target.value })}
                    required
                    style={{ width: '100%' }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <input
                  type="checkbox"
                  id="is_active_edit"
                  checked={editForm.is_active}
                  onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                  style={{ minHeight: 'auto', width: '1.2rem', height: '1.2rem' }}
                />
                <label htmlFor="is_active_edit" style={{ fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer' }}>Active for Booking</label>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
                <button type="button" className="icon-button" onClick={() => setEditingWindow(null)}>Cancel</button>
                <button type="submit" className="primary" disabled={isSubmittingEdit}>
                  {isSubmittingEdit ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
