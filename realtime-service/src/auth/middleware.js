import jwt from 'jsonwebtoken';

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

export function authenticateSocket(socket, next) {
  const token = socket.handshake.auth?.token || socket.handshake.headers?.authorization?.replace('Bearer ', '');

  if (!token) {
    socket.user = { id: 'anonymous', role: 'guest', email: 'guest@local' };
    return next();
  }

  try {
    const decoded = jwt.verify(token, getJwtSecret(), { algorithms: ['HS256'] });
    socket.user = {
      id: decoded.user_id || decoded.sub,
      role: decoded.role || 'user',
      email: decoded.email || '',
    };
    return next();
  } catch (error) {
    return next(new Error('Unauthorized socket connection'));
  }
}
