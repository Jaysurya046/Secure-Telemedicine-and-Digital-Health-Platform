import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Activity, LogIn, Stethoscope, CalendarCheck, Clock, Users, Video } from 'lucide-react';
import { Dashboard } from './pages/Dashboard';
import { Appointments } from './pages/Appointments';
import { Availability } from './pages/Availability';
import { Patients } from './pages/Patients';
import { Consultation } from './pages/Consultation';
import { PatientHistory } from './components/PatientHistory';
import { PrescriptionForm } from './components/PrescriptionForm';
import { apiFetch, login, clearTokens, getToken } from './services/api';

type Tab = 'dashboard' | 'appointments' | 'availability' | 'patients' | 'consultation';

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => Boolean(getToken()));
  const [appointments, setAppointments] = useState<any[]>([]);
  const [patients, setPatients] = useState<any[]>([]);
  const [records, setRecords] = useState<any[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<any>(null);
  const [consultationRoomId, setConsultationRoomId] = useState<string>('demo');
  const [error, setError] = useState('');

  async function loadData() {
    const [appointmentData, patientData] = await Promise.all([
      apiFetch<any>('/api/appointments/').catch(() => ({ results: [] })),
      apiFetch<any>('/api/auth/patients/').catch(() => ({ results: [] }))
    ]);
    setAppointments(appointmentData.results || appointmentData || []);
    setPatients(patientData.results || patientData || []);
  }

  useEffect(() => {
    loadData().catch(() => {});
  }, []);

  async function submitLogin(event: FormEvent) {
    event.preventDefault();
    setError('');
    try {
      await login(email, password);
      setIsAuthenticated(true);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    }
  }

  async function handleLogout() {
    clearTokens();
    setIsAuthenticated(false);
    setAppointments([]);
    setPatients([]);
    setRecords([]);
    setSelectedPatient(null);
    await loadData().catch(() => {});
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
        <button className={tab === 'dashboard' ? 'active' : ''} onClick={() => setTab('dashboard')}>
          <Activity size={18} />Dashboard
        </button>
        <button className={tab === 'appointments' ? 'active' : ''} onClick={() => setTab('appointments')}>
          <CalendarCheck size={18} />Appointments
        </button>
        <button className={tab === 'availability' ? 'active' : ''} onClick={() => setTab('availability')}>
          <Clock size={18} />Availability
        </button>
        <button className={tab === 'patients' ? 'active' : ''} onClick={() => setTab('patients')}>
          <Users size={18} />Patients
        </button>
        <button className={tab === 'consultation' ? 'active' : ''} onClick={() => setTab('consultation')}>
          <Video size={18} />Consultation
        </button>
      </aside>

      <section className="workspace">
        {isAuthenticated ? (
          <div className="login-strip" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#334155' }}>
              Doctor Session Active {email ? `(${email})` : ''}
            </span>
            <button type="button" className="icon-button" onClick={handleLogout} style={{ fontSize: '0.8rem' }}>
              <LogIn size={14} /> Sign out
            </button>
          </div>
        ) : (
          <form className="login-strip" onSubmit={submitLogin}>
            <input placeholder="Doctor email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
            <input placeholder="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
            <button className="primary"><LogIn size={16} />Sign in</button>
            {error ? <span className="error">{error}</span> : null}
          </form>
        )}

        {tab === 'dashboard' ? (
          <Dashboard
            appointments={appointments}
            patients={patients}
            onViewAppointments={() => setTab('appointments')}
            onManageAvailability={() => setTab('availability')}
          />
        ) : null}

        {tab === 'appointments' ? (
          <Appointments onRefreshDashboard={loadData} />
        ) : null}

        {tab === 'availability' ? (
          <Availability onRefreshDashboard={loadData} />
        ) : null}

        {tab === 'patients' ? (
          <div className="split">
            <Patients patients={patients} onSelect={selectPatient} />
            <div className="stack">
              <PatientHistory records={records} />
              <PrescriptionForm patientId={selectedPatient?.id} />
            </div>
          </div>
        ) : null}

        {tab === 'consultation' ? (
          <Consultation roomId={consultationRoomId} />
        ) : null}
      </section>
    </main>
  );
}
