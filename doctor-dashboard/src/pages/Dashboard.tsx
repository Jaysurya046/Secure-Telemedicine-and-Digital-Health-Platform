import { CalendarCheck, FileText, Users, Clock, ArrowRight } from 'lucide-react';
import type { ReactNode } from 'react';

export function Dashboard({
  appointments,
  patients,
  onViewAppointments,
  onManageAvailability
}: {
  appointments: any[];
  patients: any[];
  onViewAppointments?: () => void;
  onManageAvailability?: () => void;
}) {
  const pendingCount = appointments.filter((item) => item.status === 'pending').length;
  const confirmedCount = appointments.filter((item) => item.status === 'confirmed').length;

  return (
    <section className="page-grid">
      <Metric label="Pending Approvals" value={pendingCount} icon={<CalendarCheck />} />
      <Metric label="Confirmed Visits" value={confirmedCount} icon={<FileText />} />
      <Metric label="Total Patients" value={patients.length} icon={<Users />} />

      <div className="panel wide">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div className="panel-title" style={{ margin: 0 }}>
            <CalendarCheck size={18} color="#2f9e8f" />
            Recent Appointment Queue
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {onManageAvailability && (
              <button className="icon-button" style={{ fontSize: '0.8rem' }} onClick={onManageAvailability}>
                <Clock size={14} /> Availability
              </button>
            )}
            {onViewAppointments && (
              <button className="icon-button" style={{ fontSize: '0.8rem' }} onClick={onViewAppointments}>
                View All Queue <ArrowRight size={14} />
              </button>
            )}
          </div>
        </div>

        {appointments.length === 0 ? (
          <p className="muted" style={{ padding: '1rem', textAlign: 'center' }}>No appointments in your queue yet.</p>
        ) : (
          <div className="stack">
            {appointments.slice(0, 5).map((appointment) => (
              <article className="row-card" key={appointment.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <strong>{appointment.patient_detail?.profile?.full_name || appointment.patient_detail?.email || 'Patient'}</strong>
                  <div className="muted">{new Date(appointment.scheduled_start).toLocaleString()} · {appointment.reason}</div>
                </div>
                <span
                  style={{
                    padding: '0.2rem 0.5rem',
                    borderRadius: '999px',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    textTransform: 'capitalize',
                    background:
                      appointment.status === 'confirmed'
                        ? '#d1fae5'
                        : appointment.status === 'completed'
                        ? '#e0f2fe'
                        : appointment.status === 'cancelled'
                        ? '#ffe4e6'
                        : '#fef3c7',
                    color:
                      appointment.status === 'confirmed'
                        ? '#065f46'
                        : appointment.status === 'completed'
                        ? '#0369a1'
                        : appointment.status === 'cancelled'
                        ? '#9f1239'
                        : '#92400e'
                  }}
                >
                  {appointment.status}
                </span>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function Metric({ label, value, icon }: { label: string; value: number; icon: ReactNode }) {
  return (
    <div className="panel metric">
      <div>{icon}</div>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
