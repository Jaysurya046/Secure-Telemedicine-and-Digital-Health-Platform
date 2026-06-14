const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function getToken() {
  return localStorage.getItem('doctorAccessToken') || '';
}

export function setTokens(tokens: { access: string; refresh: string }) {
  localStorage.setItem('doctorAccessToken', tokens.access);
  localStorage.setItem('doctorRefreshToken', tokens.refresh);
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || body.detail || 'Request failed');
  }
  return response.json();
}

export async function login(email: string, password: string) {
  const data = await apiFetch<{ tokens: { access: string; refresh: string } }>('/api/auth/login/', {
    method: 'POST',
    body: JSON.stringify({ email, password })
  });
  setTokens(data.tokens);
  return data;
}
