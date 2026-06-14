import { Users } from 'lucide-react';

export function Patients({ patients, onSelect }: { patients: any[]; onSelect: (patient: any) => void }) {
  return (
    <section className="panel">
      <div className="panel-title"><Users size={18} />Patients</div>
      <div className="stack">
        {patients.map((patient) => (
          <button className="row-card selectable" key={patient.id} onClick={() => onSelect(patient)}>
            <strong>{patient.profile?.full_name || patient.email}</strong>
            <span>{patient.email}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
