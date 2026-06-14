import { useState } from 'react';
import type { FormEvent } from 'react';
import { Pill, Plus } from 'lucide-react';
import { apiFetch } from '../services/api';

export function PrescriptionForm({ patientId, consultationId }: { patientId?: string; consultationId?: string }) {
  const [medication, setMedication] = useState('');
  const [status, setStatus] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!patientId) {
      setStatus('Select a patient first.');
      return;
    }
    await apiFetch('/api/medical-records/prescriptions/', {
      method: 'POST',
      body: JSON.stringify({
        patient: patientId,
        consultation: consultationId || null,
        instructions: 'Take as directed',
        items: [{ medication_name: medication, dosage: '1 tablet', frequency: 'Daily', duration: '7 days', instructions: '' }]
      })
    });
    setMedication('');
    setStatus('Prescription issued.');
  }

  return (
    <form className="panel" onSubmit={submit}>
      <div className="panel-title"><Pill size={18} />Prescription</div>
      <input value={medication} onChange={(event) => setMedication(event.target.value)} placeholder="Medication name" required />
      <button className="primary"><Plus size={16} />Issue</button>
      {status ? <p className="muted">{status}</p> : null}
    </form>
  );
}
