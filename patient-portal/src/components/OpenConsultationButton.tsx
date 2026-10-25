'use client';
import React, { useRef, useState } from 'react';
import { getOrCreateConsultation } from '../lib/consultations';
import { getAccessToken } from '../lib/api';
const defaultNavigate = (url: string) => window.location.assign(url);
export function OpenConsultationButton({ appointmentId, navigate = defaultNavigate }: { appointmentId: string; navigate?: (url: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const working = useRef(false);
  async function open() {
    if (working.current) return;
    const token = getAccessToken();
    working.current = true; setBusy(true); setError('');
    try {
      const consultation = await getOrCreateConsultation(appointmentId);
      if (token && getAccessToken() === token) navigate(`/consultation/${consultation.id}`);
    } catch (err) { if (getAccessToken() === token) setError(err instanceof Error ? err.message : 'Could not open consultation.'); }
    finally { working.current = false; setBusy(false); }
  }
  return <span><button className="btn btn-secondary" disabled={busy} onClick={() => void open()}>{busy ? 'Opening…' : 'Open Consultation'}</button>
    {error && <span role="alert">{error}</span>}</span>;
}
