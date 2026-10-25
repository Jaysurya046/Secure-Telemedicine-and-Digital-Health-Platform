'use client';
import { PatientConsultation } from '@/components/PatientConsultation';
export default function ConsultationPage({ params }: { params: { id: string } }) {
  return <PatientConsultation key={params.id} id={params.id} />;
}
