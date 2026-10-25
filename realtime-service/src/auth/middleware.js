import jwt from 'jsonwebtoken';
import { fetchIdentity } from './django_client.js';

/**
 * Resolves the effective JWT secret following the unified configuration policy:
 * 1. JWT_SECRET_KEY if non-empty (trimmed).
 * 2. DJANGO_SECRET_KEY if non-empty (trimmed).
 * 3. Default fallback ('django-insecure-change-this-in-production').
 */
export function getJwtSecret() {
  const jwtKey = process.env.JWT_SECRET_KEY?.trim();
  if (jwtKey) return jwtKey;
  const djangoKey = process.env.DJANGO_SECRET_KEY?.trim();
  if (djangoKey) return djangoKey;
  return 'django-insecure-change-this-in-production';
}

export function getUserToken(socket) {
  const auth = socket.handshake.auth?.token;
  const header = socket.handshake.headers?.authorization;
  return typeof auth === 'string' && auth ? auth :
    (typeof header === 'string' ? header.replace(/^Bearer\s+/i, '') : '');
}

export async function authenticateSocket(socket, next) {
  try {
    const token = getUserToken(socket);
    if (!token) throw new Error('no token provided');
    const claims = jwt.verify(token, getJwtSecret(), { algorithms: ['HS256'] });
    if (claims.token_type !== 'access') throw new Error('refresh token or missing access token type');
    if (!claims.user_id || !claims.exp) throw new Error('token lacks identity or expiration');
    const user = await fetchIdentity(token);
    if (!user || String(user.id) !== String(claims.user_id)) throw new Error('current user could not be verified');
    socket.user = user;
    socket.accessToken = token;
    const delay = Math.max(1, Math.min(2147483647, claims.exp * 1000 - Date.now()));
    const timer = setTimeout(() => socket.disconnect(true), delay);
    timer.unref?.();
    socket.once('disconnect', () => clearTimeout(timer));
    next();
  } catch (error) {
    next(new Error(`Authentication required: ${error.message}`));
  }
}
