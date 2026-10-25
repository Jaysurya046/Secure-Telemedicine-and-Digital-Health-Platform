import { useEffect, useState, useRef, useCallback } from 'react';
import type { FormEvent } from 'react';
import { Activity, LogIn, Stethoscope, CalendarCheck, Clock, Users, Video, ShieldAlert } from 'lucide-react';
import { Dashboard } from './pages/Dashboard';
import { Appointments } from './pages/Appointments';
import { Availability } from './pages/Availability';
import { Patients } from './pages/Patients';
import { Consultation } from './pages/Consultation';
import { getOrCreateConsultation } from './services/consultations';
import { PatientHistory } from './components/PatientHistory';
import { PrescriptionForm } from './components/PrescriptionForm';
import { apiFetch, login, clearTokens, getToken, formatErrorMessage } from './services/api';

type Tab = 'dashboard' | 'appointments' | 'availability' | 'patients' | 'consultation';

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => Boolean(getToken()));
  const [sessionId, setSessionId] = useState<number>(1);
  const sessionIdRef = useRef<number>(1);

  const [appointments, setAppointments] = useState<any[]>([]);
  const [patients, setPatients] = useState<any[]>([]);
  const [records, setRecords] = useState<any[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<any>(null);
  const [error, setError] = useState('');
  const [loadingSession, setLoadingSession] = useState<boolean>(false);

  // Active consultation opened from an appointment
  const [activeConsultationId, setActiveConsultationId] = useState<string | undefined>(undefined);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  async function loadData() {
    if (!getToken()) {
      setAppointments([]);
      setPatients([]);
      return;
    }

    const currentSession = sessionIdRef.current;
    setLoadingSession(true);
    try {
      const [appointmentData, patientData] = await Promise.all([
        apiFetch<any>('/api/appointments/').catch(() => ({ results: [] })),
        apiFetch<any>('/api/auth/patients/').catch(() => ({ results: [] }))
      ]);

      // Discard responses from a previous session or if logged out
      if (currentSession !== sessionIdRef.current || !getToken()) {
        return;
      }

      setAppointments(appointmentData.results || appointmentData || []);
      setPatients(patientData.results || patientData || []);
    } finally {
      if (currentSession === sessionIdRef.current) {
        setLoadingSession(false);
      }
    }
  }

  useEffect(() => {
    if (isAuthenticated) {
      loadData().catch(() => {});
    } else {
      setAppointments([]);
      setPatients([]);
      setRecords([]);
      setSelectedPatient(null);
      setActiveConsultationId(undefined);
    }
  }, [isAuthenticated, sessionId]);

  async function submitLogin(event: FormEvent) {
    event.preventDefault();
    setError('');

    // Clear previous session state immediately before authenticating
    setAppointments([]);
    setPatients([]);
    setRecords([]);
    setSelectedPatient(null);
    setActiveConsultationId(undefined);

    try {
      await login(email, password);
      const nextSession = sessionIdRef.current + 1;
      sessionIdRef.current = nextSession;
      setSessionId(nextSession);
      setIsAuthenticated(true);
      setTab('dashboard');
    } catch (err: any) {
      setError(err instanceof Error ? err.message : 'Login failed');
    }
  }

  function handleLogout() {
    clearTokens();
    const nextSession = sessionIdRef.current + 1;
    sessionIdRef.current = nextSession;
    setSessionId(nextSession);

    // Unmount and wipe all session-specific state
    // Active consultation unmounts → its useEffect cleanup disconnects its socket
    setIsAuthenticated(false);
    setEmail('');
    setPassword('');
    setError('');
    setAppointments([]);
    setPatients([]);
    setRecords([]);
    setSelectedPatient(null);
    setActiveConsultationId(undefined);
    setTab('dashboard');
  }

  async function selectPatient(patient: any) {
    setSelectedPatient(patient);
    setTab('patients');
    const currentSession = sessionIdRef.current;
    const data = await apiFetch<any>(`/api/medical-records/?patient=${patient.id}`).catch(() => ({ results: [] }));
    if (currentSession === sessionIdRef.current && getToken()) {
      setRecords(data.results || data);
    }
  }

  /**
   * Opens (or creates) the consultation for a confirmed appointment.
   * 1. Check if the appointment already has a consultation via the API.
   * 2. If not, create one.
   * 3. Navigate to the consultation tab with the real consultation ID.
   */
  const openingConsultation = useRef(false);
  const openConsultationForAppointment = useCallback(async (appointmentId: string) => {
    if (!appointmentId || openingConsultation.current) return;
    const session = sessionIdRef.current;
    openingConsultation.current = true;
    try {
      const consultation = await getOrCreateConsultation(appointmentId);
      if (session !== sessionIdRef.current || !getToken()) return;
      setActiveConsultationId(consultation.id); setTab('consultation');
    } catch (error) {
      if (session === sessionIdRef.current && getToken()) setError(formatErrorMessage(error));
    } finally { openingConsultation.current = false; }
  }, []);

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><Stethoscope size={24} />CareBridge MD</div>
        <button
          className={tab === 'dashboard' ? 'active' : ''}
          onClick={() => setTab('dashboard')}
          disabled={!isAuthenticated}
        >
          <Activity size={18} />Dashboard
        </button>
        <button
          className={tab === 'appointments' ? 'active' : ''}
          onClick={() => setTab('appointments')}
          disabled={!isAuthenticated}
        >
          <CalendarCheck size={18} />Appointments
        </button>
        <button
          className={tab === 'availability' ? 'active' : ''}
          onClick={() => setTab('availability')}
          disabled={!isAuthenticated}
        >
          <Clock size={18} />Availability
        </button>
        <button
          className={tab === 'patients' ? 'active' : ''}
          onClick={() => setTab('patients')}
          disabled={!isAuthenticated}
        >
          <Users size={18} />Patients
        </button>
        <button
          className={tab === 'consultation' ? 'active' : ''}
          onClick={() => setTab('consultation')}
          disabled={!isAuthenticated}
        >
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
            <input placeholder="Doctor email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            <input placeholder="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
            <button className="primary"><LogIn size={16} />Sign in</button>
            {error ? <span className="error">{error}</span> : null}
          </form>
        )}

        {/* Protected screens are unmounted on logout and keyed by sessionId */}
        {!isAuthenticated ? (
          <div className="panel" style={{ textAlign: 'center', padding: '3.5rem 1.5rem', maxWidth: '32rem', margin: '2rem auto' }}>
            <ShieldAlert size={48} color="#2f9e8f" style={{ margin: '0 auto 1rem' }} />
            <h2 style={{ fontSize: '1.4rem', fontWeight: 900 }}>Doctor Portal Access</h2>
            <p className="muted" style={{ marginTop: '0.5rem' }}>
              Please sign in with your doctor credentials above to access your clinical dashboard, appointments, and availability schedule.
            </p>
          </div>
        ) : (
          <>
            {tab === 'dashboard' ? (
              <Dashboard
                key={`dash-${sessionId}`}
                appointments={appointments}
                patients={patients}
                onViewAppointments={() => setTab('appointments')}
                onManageAvailability={() => setTab('availability')}
              />
            ) : null}

            {tab === 'appointments' ? (
              <Appointments
                key={`appts-${sessionId}`}
                onRefreshDashboard={loadData}
                onOpenConsultation={openConsultationForAppointment}
              />
            ) : null}

            {tab === 'availability' ? (
              <Availability key={`avail-${sessionId}`} onRefreshDashboard={loadData} />
            ) : null}

            {tab === 'patients' ? (
              <div className="split" key={`pts-${sessionId}`}>
                <Patients patients={patients} onSelect={selectPatient} />
                <div className="stack">
                  <PatientHistory records={records} />
                  <PrescriptionForm patientId={selectedPatient?.id} />
                </div>
              </div>
            ) : null}

            {tab === 'consultation' ? (
              <Consultation
                key={`consult-${sessionId}-${activeConsultationId}`}
                consultationId={activeConsultationId}
                onCompleted={loadData}
              />
            ) : null}
          </>
        )}
      </section>
    </main>
  );
}
