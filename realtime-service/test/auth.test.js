import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import jwt from 'jsonwebtoken';
import { authenticateSocket, getJwtSecret } from '../src/auth/middleware.js';
const originalFetch = globalThis.fetch;
const originalEnv = { ...process.env };
afterEach(() => { globalThis.fetch = originalFetch; process.env = { ...originalEnv }; });
test('signing secret follows trimmed JWT, Django, fallback priority', () => {
  process.env.JWT_SECRET_KEY = ' jwt '; process.env.DJANGO_SECRET_KEY = ' django ';
  assert.equal(getJwtSecret(), 'jwt'); process.env.JWT_SECRET_KEY = ' ';
  assert.equal(getJwtSecret(), 'django'); delete process.env.DJANGO_SECRET_KEY;
  assert.equal(getJwtSecret(), 'django-insecure-change-this-in-production');
});
test('identity uses current Django role and email instead of JWT claims', async () => {
  process.env.JWT_SECRET_KEY = 'synthetic-long-enough-key-for-testing';
  const token = jwt.sign({ user_id: 'user1', role: 'admin', token_type: 'access' }, getJwtSecret(), { expiresIn: 60 });
  globalThis.fetch = async () => new Response(JSON.stringify({ id: 'user1', role: 'patient', email: 'current@test.com' }));
  const socket = { handshake: { auth: { token } }, once() {}, disconnect() {} };
  await authenticateSocket(socket, error => assert.ifError(error));
  assert.equal(socket.user.role, 'patient'); assert.equal(socket.user.email, 'current@test.com');
});
test('identity outage, unsupported roles and mismatched identities fail closed', async () => {
  process.env.JWT_SECRET_KEY = 'synthetic-long-enough-key-for-testing';
  const token = jwt.sign({ user_id: 'user1', token_type: 'access' }, getJwtSecret(), { expiresIn: 60 });
  for (const response of [null, { id: 'user1', role: 'nurse' }, { id: 'different', role: 'patient' }]) {
    globalThis.fetch = async () => { if (!response) throw new Error('offline'); return new Response(JSON.stringify(response)); };
    await authenticateSocket({ handshake: { auth: { token } } }, error => assert.match(error.message, /Authentication required/));
  }
});
