'use client';

import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { CalendarPlus } from 'lucide-react';
import { AppNav } from '@/components/AppNav';
import { apiFetch } from '@/lib/api';

export default function AppointmentsPage() {
  const [doctors, setDoctors] = useState<any[]>([]);
  const [appointments, setAppointments] = useState<any[]>([]);
  const [form, setForm] = useState({ doctor: '', scheduled_start: '', scheduled_end: '', reason: '' });

  useEffect(() => {
    apiFetch<any>('/api/auth/doctors/').then((data) => setDoctors(data.results || data)).catch(() => {});
    apiFetch<any>('/api/appointments/').then((data) => setAppointments(data.results || data)).catch(() => {});
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await apiFetch('/api/appointments/', {
      method: 'POST',
      body: JSON.stringify({ ...form, symptoms: [] })
    });
    const data = await apiFetch<any>('/api/appointments/');
    setAppointments(data.results || data);
  }

  return (
    <main className="app-shell">
      <AppNav />
      <section className="mx-auto grid max-w-6xl gap-6 px-5 py-8 lg:grid-cols-[0.8fr_1.2fr]">
        <form onSubmit={submit} className="panel grid gap-4 p-5">
          <h1 className="text-2xl font-black">Book appointment</h1>
          <select className="rounded-md border border-slate-300 px-3 py-2" value={form.doctor} onChange={(event) => setForm({ ...form, doctor: event.target.value })} required>
            <option value="">Select doctor</option>
            {doctors.map((doctor) => <option key={doctor.id} value={doctor.id}>{doctor.profile?.full_name || doctor.email}</option>)}
          </select>
          <input className="rounded-md border border-slate-300 px-3 py-2" type="datetime-local" value={form.scheduled_start} onChange={(event) => setForm({ ...form, scheduled_start: event.target.value })} required />
          <input className="rounded-md border border-slate-300 px-3 py-2" type="datetime-local" value={form.scheduled_end} onChange={(event) => setForm({ ...form, scheduled_end: event.target.value })} required />
          <textarea className="rounded-md border border-slate-300 px-3 py-2" placeholder="Reason" value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} required />
          <button className="btn btn-primary justify-center"><CalendarPlus className="h-4 w-4" aria-hidden />Book</button>
        </form>
        <div className="panel p-5">
          <h2 className="text-xl font-black">Appointments</h2>
          <div className="mt-4 grid gap-3">
            {appointments.map((appointment) => (
              <div key={appointment.id} className="rounded-md border border-slate-200 p-4">
                <div className="font-bold">{appointment.reason}</div>
                <div className="text-sm text-slate-600">{new Date(appointment.scheduled_start).toLocaleString()} - {appointment.status}</div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
