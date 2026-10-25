import { apiFetch, ApiError } from './api';

type Consultation = { id: string };
type List = { results: Consultation[] };
export async function getOrCreateConsultation(appointmentId: string): Promise<Consultation> {
  const path = `/api/consultations/?appointment=${encodeURIComponent(appointmentId)}`;
  const find = async () => (await apiFetch<List>(path)).results[0];
  const existing = await find();
  if (existing) return existing;
  try {
    return await apiFetch<Consultation>('/api/consultations/', {
      method: 'POST', body: JSON.stringify({ appointment: appointmentId }),
    });
  } catch (error) {
    // Another participant may have created the consultation after our lookup.
    if (error instanceof ApiError && (error.status === 400 || error.status === 409)) {
      const created = await find();
      if (created) return created;
    }
    throw error;
  }
}
