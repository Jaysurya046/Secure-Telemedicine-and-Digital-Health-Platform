'use client';

import React, { useEffect, useState } from 'react';
import { AppNav } from './AppNav';
import { Chat } from './Chat';
import type { Socket } from 'socket.io-client';
import { apiFetch, getAccessToken } from '../lib/api';

type Consultation = { id: string; room_id: string; status: string; diagnosis: string; clinical_notes: string;
  follow_up_required: boolean; follow_up_notes: string; doctor_detail?: { email: string } };
export function PatientConsultation({ id, socketFactory }: { id: string; socketFactory?: () => Socket }) {
  const [data, setData] = useState<Consultation | null>(null);
  const [error, setError] = useState('');
  const [session, setSession] = useState('');
  useEffect(() => {
    let active = true;
    const token = getAccessToken();
    setSession(token); setData(null); setError('');
    if (!token) { setError('Sign in to open this consultation.'); return; }
    const load = () => apiFetch<Consultation>(`/api/consultations/${id}/`).then(result => {
      if (active && getAccessToken() === token) setData(result);
    }).catch(err => { if (active) { setError(err.message); if (err.status === 401 || err.status === 403 || err.status === 404) setData(null); } });
    void load();
    const timer = setInterval(() => {
      if (getAccessToken() !== token) { setData(null); setSession(''); setError('Session ended. Please sign in.'); }
      else void load();
    }, 5000);
    const onSession = () => { setData(null); setSession(''); setError('Session ended. Please sign in.'); };
    window.addEventListener('auth:changed', onSession); window.addEventListener('storage', onSession);
    return () => { active = false; clearInterval(timer); window.removeEventListener('auth:changed', onSession); window.removeEventListener('storage', onSession); };
  }, [id]);
  return <main className="app-shell"><AppNav /><section className="mx-auto max-w-6xl space-y-4 px-5 py-8">
    {error && <p role="alert">{error}</p>}
    {!data ? <p>Consultation details unavailable until loaded.</p> : <>
      <section className="panel p-5"><h1>Consultation with {data.doctor_detail?.email}</h1><p>Status: {data.status}</p>
        <p>Video media is planned for a separate module.</p>
        <h2>Clinical information</h2><p>Diagnosis: {data.diagnosis || 'Not recorded'}</p><p>Clinical notes: {data.clinical_notes || 'Not recorded'}</p>
        {data.follow_up_required && <p>Follow-up required: {data.follow_up_notes}</p>}
      </section>
      <Chat socketFactory={socketFactory} key={`${session}:${data.id}`} consultationId={data.id} roomId={data.room_id} closed={['completed', 'cancelled'].includes(data.status)} />
    </>}
  </section></main>;
}
