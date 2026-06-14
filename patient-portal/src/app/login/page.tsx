'use client';

import { useState } from 'react';
import type { FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { LogIn } from 'lucide-react';
import { AppNav } from '@/components/AppNav';
import { login } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    try {
      await login({ email, password });
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    }
  }

  return (
    <main className="app-shell">
      <AppNav />
      <form onSubmit={submit} className="panel mx-auto mt-12 grid max-w-md gap-4 p-6">
        <h1 className="text-2xl font-black">Sign in</h1>
        <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        <input className="rounded-md border border-slate-300 px-3 py-2" placeholder="Password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        {error ? <p className="rounded-md bg-red-50 p-3 text-sm font-semibold text-red-700">{error}</p> : null}
        <button className="btn btn-primary justify-center"><LogIn className="h-4 w-4" aria-hidden />Sign in</button>
      </form>
    </main>
  );
}
