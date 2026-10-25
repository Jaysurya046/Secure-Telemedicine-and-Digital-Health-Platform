const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export type AuthPayload = {
  email: string;
  password: string;
};

export class ApiError extends Error {
  status: number;
  body: any;
  details?: any;

  constructor(message: string, status: number, body: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.details = body?.details || (typeof body === 'object' ? body : undefined);
  }
}

export function isInvalidPageError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const apiErr = err as ApiError;
  if (apiErr.status !== 404) return false;
  const detail = apiErr.body?.detail || apiErr.body?.message || apiErr.message || '';
  return /invalid page/i.test(String(detail));
}

export function getAccessToken() {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('accessToken') || '';
}

export function setTokens(tokens: { access: string; refresh: string }) {
  if (typeof window === 'undefined') return;
  localStorage.setItem('accessToken', tokens.access);
  localStorage.setItem('refreshToken', tokens.refresh);
}

export function clearTokens() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem('accessToken');
  localStorage.removeItem('refreshToken');
}

export function formatErrorMessage(body: any): string {
  if (!body) return 'Request failed';
  if (typeof body === 'string') return body;
  if (body.message && typeof body.message === 'string') return body.message;
  if (body.error && typeof body.error === 'string') return body.error;
  if (body.detail && typeof body.detail === 'string') return body.detail;
  if (body.details && typeof body.details === 'object') {
    return Object.entries(body.details)
      .map(([field, err]) => `${field}: ${Array.isArray(err) ? err.join(', ') : err}`)
      .join(' | ');
  }
  if (typeof body === 'object') {
    const entries = Object.entries(body);
    if (entries.length > 0) {
      return entries
        .map(([field, err]) => `${field}: ${Array.isArray(err) ? err.join(', ') : err}`)
        .join(' | ');
    }
  }
  return 'Request failed';
}

export function toIsoTimestamp(localDateTimeString: string): string {
  if (!localDateTimeString) return '';
  const date = new Date(localDateTimeString);
  if (isNaN(date.getTime())) return '';
  return date.toISOString();
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (response.status === 204) {
    return null as T;
  }

  const text = await response.text();
  let body: any = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(formatErrorMessage(body), response.status, body);
  }
  return body as T;
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
