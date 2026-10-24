const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export type AuthPayload = {
  email: string;
  password: string;
};

export function getAccessToken() {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('accessToken') || '';
}

export function setTokens(tokens: { access: string; refresh: string }) {
  localStorage.setItem('accessToken', tokens.access);
  localStorage.setItem('refreshToken', tokens.refresh);
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || body.detail || 'Request failed');
  }
  return response.json();
}

export async function login(payload: AuthPayload) {
  const data = await apiFetch<{ tokens: { access: string; refresh: string } }>('/api/auth/login/', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  setTokens(data.tokens);
  return data;
}

export async function registerPatient(payload: AuthPayload & { first_name: string; last_name: string; phone?: string }) {
  const data = await apiFetch<{ tokens: { access: string; refresh: string } }>('/api/auth/register/', {
    method: 'POST',
    body: JSON.stringify({ ...payload, password_confirm: payload.password, role: 'patient' })
  });
  setTokens(data.tokens);
  return data;
}
