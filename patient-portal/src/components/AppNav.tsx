'use client';

import Link from 'next/link';
import { clearTokens } from '../lib/api';
import { CalendarDays, ClipboardList, HeartPulse, LogIn, Video } from 'lucide-react';

export function AppNav() {
  return (
    <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
        <Link href="/" className="flex items-center gap-2 font-black text-ink">
          <HeartPulse className="h-6 w-6 text-mint" aria-hidden />
          CareBridge
        </Link>
        <nav className="flex items-center gap-2 text-sm font-semibold text-slate-600">
          <Link className="btn btn-secondary px-3 py-2" href="/dashboard"><ClipboardList className="h-4 w-4" aria-hidden />Dashboard</Link>
          <Link className="btn btn-secondary px-3 py-2" href="/appointments"><CalendarDays className="h-4 w-4" aria-hidden />Appointments</Link>
          <Link className="btn btn-secondary px-3 py-2" href="/appointments"><Video className="h-4 w-4" aria-hidden />Consult</Link>
          <button type="button" onClick={() => { clearTokens(); window.location.assign('/login'); }}>Sign out</button>
          <Link className="btn btn-primary px-3 py-2" href="/login"><LogIn className="h-4 w-4" aria-hidden />Sign in</Link>
        </nav>
      </div>
    </header>
  );
}
