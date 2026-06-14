import jwt from 'jsonwebtoken';

const jwtSecret = process.env.JWT_SECRET_KEY || process.env.DJANGO_SECRET_KEY || 'django-insecure-change-this-in-production';

export function authenticateSocket(socket, next) {
  const token = socket.handshake.auth?.token || socket.handshake.headers?.authorization?.replace('Bearer ', '');

  if (!token) {
    socket.user = { id: 'anonymous', role: 'guest', email: 'guest@local' };
    return next();
  }

  try {
    const decoded = jwt.verify(token, jwtSecret, { algorithms: ['HS256'] });
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
