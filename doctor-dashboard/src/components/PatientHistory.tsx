import { FileText } from 'lucide-react';

export function PatientHistory({ records }: { records: any[] }) {
  return (
    <section className="panel">
      <div className="panel-title"><FileText size={18} />Patient history</div>
      <div className="stack">
        {records.length === 0 ? <p className="muted">No records loaded.</p> : null}
        {records.map((record) => (
          <article className="row-card" key={record.id}>
            <strong>{record.title}</strong>
            <span>{record.record_type} · {new Date(record.created_at).toLocaleDateString()}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
