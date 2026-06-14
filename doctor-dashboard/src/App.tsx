import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Activity, LogIn, Stethoscope } from 'lucide-react';
import { Dashboard } from './pages/Dashboard';
import { Patients } from './pages/Patients';
import { Consultation } from './pages/Consultation';
import { PatientHistory } from './components/PatientHistory';
import { PrescriptionForm } from './components/PrescriptionForm';
import { apiFetch, login } from './services/api';

type Tab = 'dashboard' | 'patients' | 'consultation';

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [appointments, setAppointments] = useState<any[]>([]);
  const [patients, setPatients] = useState<any[]>([]);
  const [records, setRecords] = useState<any[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<any>(null);
  const [error, setError] = useState('');

  async function loadData() {
    const [appointmentData, patientData] = await Promise.all([
      apiFetch<any>('/api/appointments/'),
      apiFetch<any>('/api/auth/patients/')
    ]);
    setAppointments(appointmentData.results || appointmentData);
    setPatients(patientData.results || patientData);
  }

  useEffect(() => {
    loadData().catch(() => {});
  }, []);

  async function submitLogin(event: FormEvent) {
    event.preventDefault();
    setError('');
    try {
      await login(email, password);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    }
  }

  async function selectPatient(patient: any) {
    setSelectedPatient(patient);
    setTab('patients');
    const data = await apiFetch<any>(`/api/medical-records/?patient=${patient.id}`).catch(() => ({ results: [] }));
    setRecords(data.results || data);
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><Stethoscope size={24} />CareBridge MD</div>
        <button className={tab === 'dashboard' ? 'active' : ''} onClick={() => setTab('dashboard')}><Activity size={18} />Dashboard</button>
        <button className={tab === 'patients' ? 'active' : ''} onClick={() => setTab('patients')}>Patients</button>
        <button className={tab === 'consultation' ? 'active' : ''} onClick={() => setTab('consultation')}>Consultation</button>
      </aside>
      <section className="workspace">
        <form className="login-strip" onSubmit={submitLogin}>
          <input placeholder="Doctor email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          <input placeholder="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          <button className="primary"><LogIn size={16} />Sign in</button>
          {error ? <span className="error">{error}</span> : null}
        </form>
        {tab === 'dashboard' ? <Dashboard appointments={appointments} patients={patients} /> : null}
        {tab === 'patients' ? (
          <div className="split">
            <Patients patients={patients} onSelect={selectPatient} />
            <div className="stack">
              <PatientHistory records={records} />
              <PrescriptionForm patientId={selectedPatient?.id} />
            </div>
          </div>
        ) : null}
        {tab === 'consultation' ? <Consultation roomId={appointments[0]?.consultation?.room_id || 'demo'} /> : null}
      </section>
    </main>
  );
}
