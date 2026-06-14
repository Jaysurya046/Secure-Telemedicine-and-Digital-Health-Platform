import Link from 'next/link';
import { Activity, CalendarPlus, ShieldCheck } from 'lucide-react';
import { AppNav } from '@/components/AppNav';

export default function HomePage() {
  return (
    <main className="app-shell">
      <AppNav />
      <section className="mx-auto grid max-w-6xl gap-8 px-5 py-10 lg:grid-cols-[1fr_0.85fr]">
        <div className="py-10">
          <h1 className="max-w-3xl text-5xl font-black leading-tight text-ink">CareBridge Patient Portal</h1>
          <p className="mt-5 max-w-2xl text-lg text-slate-600">Book appointments, join secure consultations, review prescriptions, and keep medical documents organized from one focused workspace.</p>
          <div className="mt-7 flex gap-3">
            <Link className="btn btn-primary" href="/appointments"><CalendarPlus className="h-5 w-5" aria-hidden />Book appointment</Link>
            <Link className="btn btn-secondary" href="/dashboard"><Activity className="h-5 w-5" aria-hidden />Open dashboard</Link>
          </div>
        </div>
        <div className="panel overflow-hidden">
          <div className="h-48 bg-[linear-gradient(135deg,#2f9e8f,#f6d365_55%,#e46d5f)]" />
          <div className="grid gap-4 p-5">
            {['Encrypted records', 'JWT-protected sessions', 'Live video and chat'].map((item) => (
              <div className="flex items-center gap-3 rounded-md border border-slate-200 p-3" key={item}>
                <ShieldCheck className="h-5 w-5 text-mint" aria-hidden />
                <span className="font-bold">{item}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
