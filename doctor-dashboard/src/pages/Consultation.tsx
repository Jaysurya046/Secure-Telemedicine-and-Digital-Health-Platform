import React, { useEffect, useState } from 'react';
import { apiFetch } from '../services/api';
import { Chat } from '../components/Chat';
import type { Socket } from 'socket.io-client';

interface ConsultationData {
  id: string; room_id: string; status: string; started_at: string | null; ended_at: string | null;
  chief_complaint: string; diagnosis: string; clinical_notes: string; follow_up_required: boolean; follow_up_notes: string;
  patient_detail?: { email: string }; doctor_detail?: { email: string };
}
export function Consultation({ consultationId, onCompleted, socketFactory }: { consultationId?: string; onCompleted?: () => void; socketFactory?: () => Socket }) {
  const [data, setData] = useState<ConsultationData | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [ending, setEnding] = useState(false);
  const [form, setForm] = useState({ diagnosis: '', clinical_notes: '', follow_up_required: false, follow_up_notes: '' });
  useEffect(() => {
    let active = true;
    setData(null); setError(''); setEnding(false);
    if (consultationId) apiFetch<ConsultationData>(`/api/consultations/${consultationId}/`).then(result => {
      if (!active) return;
      setData(result); setForm({ diagnosis: result.diagnosis, clinical_notes: result.clinical_notes,
        follow_up_required: result.follow_up_required, follow_up_notes: result.follow_up_notes });
    }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [consultationId]);
  async function transition(action: 'start' | 'end') {
    if (!data || busy) return;
    setBusy(true); setError('');
    try {
      const updated = await apiFetch<ConsultationData>(`/api/consultations/${data.id}/${action}/`, {
        method: 'POST', body: JSON.stringify(action === 'start' ? {} : form),
      });
      setData(updated); setEnding(false); if (action === 'end') onCompleted?.();
    } catch (err) { setError(err instanceof Error ? err.message : 'Request failed.'); }
    finally { setBusy(false); }
  }
  if (!consultationId) return <p>Select a confirmed appointment and open its consultation.</p>;
  return <section>
    {error && <p role="alert">{error}</p>}
    {!data ? <p>Loading consultation…</p> : <>
      <div className="panel"><h2>Consultation</h2><p>Patient: {data.patient_detail?.email}</p>
        <p>Status: {data.status}</p><p>{data.chief_complaint}</p>
        <p>Video media is planned for a separate module.</p>
        {data.status === 'scheduled' && <button id="btn-start-consultation" disabled={busy} onClick={() => void transition('start')}>Start Consultation</button>}
        {data.status === 'in_progress' && <button id="btn-end-consultation" disabled={busy} onClick={() => setEnding(true)}>End Consultation</button>}
        {ending && <form onSubmit={event => { event.preventDefault(); void transition('end'); }}>
          <label>Diagnosis<textarea id="input-diagnosis" value={form.diagnosis} onChange={e => setForm({ ...form, diagnosis: e.target.value })} /></label>
          <label>Clinical Notes<textarea id="input-clinical-notes" value={form.clinical_notes} onChange={e => setForm({ ...form, clinical_notes: e.target.value })} /></label>
          <label>Follow-up Required<input type="checkbox" checked={form.follow_up_required} onChange={e => setForm({ ...form, follow_up_required: e.target.checked })} /></label>
          <label>Follow-up Notes<textarea value={form.follow_up_notes} onChange={e => setForm({ ...form, follow_up_notes: e.target.value })} /></label>
          <button id="btn-confirm-end" type="submit" disabled={busy}>Confirm End</button><button type="button" onClick={() => setEnding(false)}>Cancel</button>
        </form>}
        {data.status === 'completed' && <div><h3>Clinical Summary</h3><p>Diagnosis: {data.diagnosis}</p><p>Notes: {data.clinical_notes}</p>
          {data.follow_up_required && <p>Follow-up required: {data.follow_up_notes}</p>}</div>}
      </div>
      <Chat socketFactory={socketFactory} key={data.id} consultationId={data.id} roomId={data.room_id} closed={['completed', 'cancelled'].includes(data.status)} />
    </>}
  </section>;
}
