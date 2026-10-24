import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert';
import jwt from 'jsonwebtoken';
import { authenticateSocket, getJwtSecret } from '../src/auth/middleware.js';

describe('Realtime Auth Middleware & JWT Resolution', () => {
  const origEnv = { ...process.env };

  beforeEach(() => {
    process.env = { ...origEnv };
  });

  describe('getJwtSecret() resolution policy', () => {
    it('uses JWT_SECRET_KEY when provided and non-empty', () => {
      process.env.JWT_SECRET_KEY = 'test-jwt-secret-123';
      process.env.DJANGO_SECRET_KEY = 'test-django-secret-456';
      assert.strictEqual(getJwtSecret(), 'test-jwt-secret-123');
    });

    it('falls back to DJANGO_SECRET_KEY when JWT_SECRET_KEY is empty or blank', () => {
      process.env.JWT_SECRET_KEY = '   ';
      process.env.DJANGO_SECRET_KEY = 'test-django-fallback-secret';
      assert.strictEqual(getJwtSecret(), 'test-django-fallback-secret');
    });

    it('falls back to DJANGO_SECRET_KEY when JWT_SECRET_KEY is undefined', () => {
      delete process.env.JWT_SECRET_KEY;
      process.env.DJANGO_SECRET_KEY = 'test-django-fallback-secret';
      assert.strictEqual(getJwtSecret(), 'test-django-fallback-secret');
    });

    it('falls back to default insecure key when both secrets are blank or undefined', () => {
      delete process.env.JWT_SECRET_KEY;
      delete process.env.DJANGO_SECRET_KEY;
      assert.strictEqual(getJwtSecret(), 'django-insecure-change-this-in-production');

      process.env.JWT_SECRET_KEY = '';
      process.env.DJANGO_SECRET_KEY = '  ';
      assert.strictEqual(getJwtSecret(), 'django-insecure-change-this-in-production');
    });
  });

  describe('authenticateSocket() token verification', () => {
    it('successfully verifies token signed with effective JWT_SECRET_KEY', (t, done) => {
      process.env.JWT_SECRET_KEY = 'synthetic-jwt-key-abc';
      process.env.DJANGO_SECRET_KEY = 'synthetic-django-key-def';

      const token = jwt.sign(
        { user_id: 'user-uuid-1', role: 'patient', email: 'patient@example.com' },
        'synthetic-jwt-key-abc',
        { algorithm: 'HS256' }
      );

      const fakeSocket = {
        handshake: {
          auth: { token },
          headers: {}
        }
      };

      authenticateSocket(fakeSocket, (err) => {
        assert.ifError(err);
        assert.strictEqual(fakeSocket.user.id, 'user-uuid-1');
        assert.strictEqual(fakeSocket.user.role, 'patient');
        assert.strictEqual(fakeSocket.user.email, 'patient@example.com');
        done();
      });
    });

    it('successfully verifies token using DJANGO_SECRET_KEY when JWT_SECRET_KEY is blank', (t, done) => {
      delete process.env.JWT_SECRET_KEY;
      process.env.DJANGO_SECRET_KEY = 'synthetic-django-shared-key';

      const token = jwt.sign(
        { user_id: 'doctor-uuid-2', role: 'doctor', email: 'doctor@example.com' },
        'synthetic-django-shared-key',
        { algorithm: 'HS256' }
      );

      const fakeSocket = {
        handshake: {
          auth: { token },
          headers: {}
        }
      };

      authenticateSocket(fakeSocket, (err) => {
        assert.ifError(err);
        assert.strictEqual(fakeSocket.user.id, 'doctor-uuid-2');
        assert.strictEqual(fakeSocket.user.role, 'doctor');
        done();
      });
    });

    it('rejects token signed with a different key', (t, done) => {
      process.env.JWT_SECRET_KEY = 'configured-jwt-key';

      const token = jwt.sign(
        { user_id: 'user-uuid-3', role: 'patient', email: 'attacker@example.com' },
        'different-unauthorized-key',
        { algorithm: 'HS256' }
      );

      const fakeSocket = {
        handshake: {
          auth: { token },
          headers: {}
        }
      };

      authenticateSocket(fakeSocket, (err) => {
        assert.ok(err instanceof Error);
        assert.strictEqual(err.message, 'Unauthorized socket connection');
        done();
      });
    });

    it('permits guest connection when token is absent', (t, done) => {
      const fakeSocket = {
        handshake: {
          auth: {},
          headers: {}
        }
      };

      authenticateSocket(fakeSocket, (err) => {
        assert.ifError(err);
        assert.strictEqual(fakeSocket.user.id, 'anonymous');
        assert.strictEqual(fakeSocket.user.role, 'guest');
        done();
      });
    });
  });
});
