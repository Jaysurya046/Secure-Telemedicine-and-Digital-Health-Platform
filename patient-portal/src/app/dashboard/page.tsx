'use client';

import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Activity, FileText, Pill, Video } from 'lucide-react';
import { AppNav } from '@/components/AppNav';
import { apiFetch } from '@/lib/api';

export default function DashboardPage() {
  const [profile, setProfile] = useState<any>(null);
  const [stats, setStats] = useState({ appointments: 0, records: 0, prescriptions: 0 });

  useEffect(() => {
    apiFetch('/api/auth/profile/').then(setProfile).catch(() => {});
    Promise.all([
      apiFetch<any>('/api/appointments/'),
      apiFetch<any>('/api/medical-records/'),
      apiFetch<any>('/api/medical-records/prescriptions/')
    ]).then(([appointments, records, prescriptions]) => {
      setStats({
        appointments: appointments.count ?? appointments.length ?? 0,
        records: records.count ?? records.length ?? 0,
        prescriptions: prescriptions.count ?? prescriptions.length ?? 0
      });
    }).catch(() => {});
  }, []);

  return (
    <main className="app-shell">
      <AppNav />
      <section className="mx-auto max-w-6xl px-5 py-8">
        <h1 className="text-3xl font-black">Welcome{profile?.profile?.first_name ? `, ${profile.profile.first_name}` : ''}</h1>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <Metric icon={<Video />} label="Appointments" value={stats.appointments} />
          <Metric icon={<FileText />} label="Records" value={stats.records} />
          <Metric icon={<Pill />} label="Prescriptions" value={stats.prescriptions} />
        </div>
        <div className="panel mt-6 p-5">
          <div className="flex items-center gap-2 font-black"><Activity className="h-5 w-5 text-mint" aria-hidden />Care timeline</div>
          <p className="mt-3 text-slate-600">Your appointments, records, and prescription data appear here as soon as the backend has entries for this account.</p>
        </div>
      </section>
    </main>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="panel p-5">
      <div className="text-mint">{icon}</div>
      <div className="mt-4 text-3xl font-black">{value}</div>
      <div className="font-semibold text-slate-600">{label}</div>
    </div>
  );
}
