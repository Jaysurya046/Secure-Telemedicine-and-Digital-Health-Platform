'use client';

import { useState } from 'react';
import type { FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { UserPlus } from 'lucide-react';
import { AppNav } from '@/components/AppNav';
import { registerPatient } from '@/lib/api';

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ first_name: '', last_name: '', phone: '', email: '', password: '' });
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    try {
      await registerPatient(form);
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    }
  }

  return (
    <main className="app-shell">
      <AppNav />
      <form onSubmit={submit} className="panel mx-auto mt-12 grid max-w-xl gap-4 p-6">
        <h1 className="text-2xl font-black">Create patient account</h1>
        <div className="grid gap-4 sm:grid-cols-2">
          <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="First name" value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} required />
          <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="Last name" value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} required />
        </div>
        <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="Phone" value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} />
        <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="Email" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
        <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="Password" type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required />
        {error ? <p className="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-700">{error}</p> : null}
        <button className="btn btn-primary justify-center"><UserPlus className="h-4 w-4" aria-hidden />Create account</button>
      </form>
    </main>
  );
}
