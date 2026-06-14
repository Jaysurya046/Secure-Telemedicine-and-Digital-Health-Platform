import { CalendarCheck, FileText, Users } from 'lucide-react';
import type { ReactNode } from 'react';

export function Dashboard({ appointments, patients }: { appointments: any[]; patients: any[] }) {
  return (
    <section className="page-grid">
      <Metric label="Today's queue" value={appointments.length} icon={<CalendarCheck />} />
      <Metric label="Patients" value={patients.length} icon={<Users />} />
      <Metric label="Open notes" value={appointments.filter((item) => item.status === 'confirmed').length} icon={<FileText />} />
      <div className="panel wide">
        <div className="panel-title"><CalendarCheck size={18} />Appointment queue</div>
        <div className="stack">
          {appointments.map((appointment) => (
            <article className="row-card" key={appointment.id}>
              <strong>{appointment.patient_detail?.profile?.full_name || appointment.patient_detail?.email || 'Patient'}</strong>
              <span>{new Date(appointment.scheduled_start).toLocaleString()} · {appointment.status}</span>
            </article>
          ))}
        </div>
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
