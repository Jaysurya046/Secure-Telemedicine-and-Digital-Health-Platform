import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Server } from 'socket.io';
import { io as client } from 'socket.io-client';
import jwt from 'jsonwebtoken';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const secret = 'socket-integration-only-signing-key-at-least-32';
let fixture, directory, config, io, http, url, api;
const clients = [];
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
function once(socket, event) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { socket.off(event, listener); reject(new Error('Timed out: '+event)); }, 6000);
    const listener = data => { clearTimeout(timer); resolve(data); };
    socket.once(event, listener);
  });
}
async function connect(token) {
  const socket = client(url, { transports: ['websocket'], auth: { token }, reconnection: false, autoConnect: false });
  clients.push(socket); const ready = once(socket, 'connect'); socket.connect(); await ready; return socket;
}
async function join(socket, roomId=config.roomId) {
  const ready = once(socket, 'consultation:joined'); socket.emit('consultation:join', { roomId }); return ready;
}
async function state(data={}) {
  return (await fetch(api+'/__test__/state/', { method: 'POST', body: JSON.stringify(data) })).json();
}
async function history() {
  const res = await fetch(`${api}/api/consultations/${config.consultationId}/messages/`, {
    headers: { Authorization: 'Bearer '+config.tokens.doctor },
  }); assert.equal(res.status, 200); return res.json();
}

before(async () => {
  directory = await mkdtemp(path.join(tmpdir(), 'telemedicine-socket-'));
  fixture = spawn(path.join(root, 'venv', process.platform==='win32' ? 'Scripts/python.exe' : 'bin/python'),
    [path.join(root, 'realtime-service/test/django_fixture.py')], {
      env: { ...process.env, PYTHONUNBUFFERED: '1', TEST_DB_PATH: path.join(directory, 'fixture.sqlite3'), JWT_SECRET_KEY: secret },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  let output = '', errors = '';
  fixture.stderr.on('data', data => { errors += data; });
  config = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Django startup timeout: '+errors)), 30000);
    fixture.once('exit', code => { clearTimeout(timeout); reject(new Error('Django exited '+code+': '+errors)); });
    fixture.stdout.on('data', data => {
      output += data;
      for (const line of output.split('\n')) {
        if (line.startsWith('{')) { clearTimeout(timeout); resolve(JSON.parse(line)); return; }
      }
    });
  });
  api = `http://127.0.0.1:${config.port}`;
  process.env.DJANGO_API_URL = api; process.env.JWT_SECRET_KEY = secret;
  const { authenticateSocket } = await import('../src/auth/middleware.js');
  const { registerSocketHandlers } = await import('../src/websocket/handler.js');
  http = createServer(); io = new Server(http, { transports: ['websocket'] });
  io.use(authenticateSocket); registerSocketHandlers(io);
  await new Promise(resolve => http.listen(0, '127.0.0.1', resolve));
  url = `http://127.0.0.1:${http.address().port}`;
});
after(async () => {
  for (const socket of clients) socket.disconnect();
  if (io) await new Promise(resolve => io.close(resolve));
  if (fixture && fixture.exitCode === null) {
    const exited = new Promise(resolve => fixture.once('exit', resolve)); fixture.kill(); await exited;
  }
  if (directory) await rm(directory, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
});

test('rejects anonymous, malformed, expired, refresh and missing-type tokens', async () => {
  for (const token of ['', 'malformed', config.refresh,
    jwt.sign({ user_id: config.patientId, token_type: 'access' }, secret, { expiresIn: -1 }),
    jwt.sign({ user_id: config.patientId }, secret, { expiresIn: '1h' })]) {
    const socket = client(url, { transports: ['websocket'], auth: { token }, reconnection: false, autoConnect: false });
    clients.push(socket); const denied = once(socket, 'connect_error'); socket.connect();
    assert.match((await denied).message, /Authentication required/); socket.disconnect();
  }
});

test('real Django membership blocks join, history, messages and signaling for outsiders', async () => {
  const attacker = await connect(config.tokens.attacker);
  for (const [event, channel, payload] of [
    ['consultation:join', 'error', { roomId: config.roomId }],
    ['chat:history', 'chat:error', { roomId: config.roomId }],
    ['chat:message', 'chat:error', { roomId: config.roomId, message: 'attack' }],
    ['webrtc:offer', 'error', { roomId: config.roomId, offer: { sdp: 'attack' } }],
  ]) {
    const denied = once(attacker, channel); attacker.emit(event, payload); assert.equal((await denied).code, 'UNAUTHORIZED');
  }
  assert.equal((await state()).count, 0); attacker.disconnect();
});

test('persists before delivery, acknowledges and retries without duplicate database rows', async () => {
  const patient = await connect(config.tokens.patient), doctor = await connect(config.tokens.doctor);
  await join(patient); await join(doctor);
  const payload = { roomId: config.roomId, message: 'Persisted hello', clientMsgId: 'first-retry-key' };
  const receive = once(doctor, 'chat:message'), acknowledged = once(patient, 'chat:ack');
  patient.emit('chat:message', payload);
  const message = await receive, ack = await acknowledged;
  assert.equal(message.id, ack.messageId); assert.equal(message.sender.id, config.patientId);
  assert.equal((await history()).results[0].id, message.id);
  // Concurrent retries use the same canonical record.
  const retry = once(patient, 'chat:ack'); patient.emit('chat:message', payload); patient.emit('chat:message', payload);
  assert.equal((await retry).messageId, message.id); await wait(150);
  assert.equal((await state()).count, 1);
  patient.disconnect(); doctor.disconnect();
});

test('rejects malformed event bodies and message types without disconnecting or persisting', async () => {
  const patient = await connect(config.tokens.patient); const beforeCount = (await state()).count;
  for (const [event, channel] of [['consultation:join','error'], ['chat:message','chat:error'], ['chat:history','chat:error'],
    ['presence:update','error'], ['webrtc:offer','error'], ['webrtc:answer','error'], ['webrtc:ice-candidate','error'], ['consultation:end-call','error']]) {
    for (const payload of [null, [], '', 42, false]) {
      const denied = once(patient, channel); patient.emit(event, payload); assert.equal((await denied).code, 'INVALID_PAYLOAD');
    }
  }
  for (const value of [null, 42, true, {}, [], ' ', 'x'.repeat(2001)]) {
    const denied = once(patient, 'chat:error'); patient.emit('chat:message', { roomId: config.roomId, message: value });
    assert.equal((await denied).code, 'INVALID_PAYLOAD');
  }
  assert.equal(patient.connected, true); assert.equal((await state()).count, beforeCount); patient.disconnect();
});

test('signaling and presence are scoped to joined members and rechecked after revocation', async () => {
  const patient = await connect(config.tokens.patient), doctor = await connect(config.tokens.doctor), attacker = await connect(config.tokens.attacker);
  await join(patient); await join(doctor);
  let leaked = 0; attacker.on('presence:update', () => leaked++); attacker.on('webrtc:offer', () => leaked++);
  const presence = once(doctor, 'presence:update'); patient.emit('presence:update', { status: 'online' });
  assert.equal((await presence).user.id, config.patientId);
  const signal = once(doctor, 'webrtc:offer'); patient.emit('webrtc:offer', { roomId: config.roomId, offer: { type: 'offer', sdp: 'example' } });
  assert.equal((await signal).from.id, config.patientId);
  let revokedReceived = 0; patient.on('chat:message', () => revokedReceived++);
  await state({ active: false });
  const denied = once(patient, 'error'); patient.emit('webrtc:offer', { roomId: config.roomId, offer: {} });
  assert.equal((await denied).code, 'UNAUTHORIZED');
  const ack = once(doctor, 'chat:ack'); doctor.emit('chat:message', { roomId: config.roomId, message: 'After revocation', clientMsgId: 'revoked-receive' });
  await ack; await wait(150);
  assert.equal(revokedReceived, 0); assert.equal(leaked, 0);
  const inactive = client(url, { auth: { token: config.tokens.patient }, transports: ['websocket'], reconnection: false, autoConnect: false });
  clients.push(inactive); const rejected = once(inactive, 'connect_error'); inactive.connect(); await rejected;
  await state({ active: true }); patient.disconnect(); doctor.disconnect(); attacker.disconnect(); inactive.disconnect();
});

test('reconnect history recovers missed persisted messages and same-key retries', async () => {
  let patient = await connect(config.tokens.patient); await join(patient); patient.disconnect();
  const doctor = await connect(config.tokens.doctor); await join(doctor);
  const ack = once(doctor, 'chat:ack'); doctor.emit('chat:message', { roomId: config.roomId, message: 'While disconnected', clientMsgId: 'reconnect' });
  const receipt = await ack;
  patient = await connect(config.tokens.patient); await join(patient);
  const recovered = once(patient, 'chat:history'); patient.emit('chat:history', { roomId: config.roomId });
  assert.ok((await recovered).results.some(message => message.id === receipt.messageId));
  patient.disconnect(); doctor.disconnect();
});

test('fails closed on Django outage without broadcasting or saving', async () => {
  const patient = await connect(config.tokens.patient); await join(patient);
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => { throw new Error('offline'); };
    const denied = once(patient, 'chat:error'); patient.emit('chat:message', { roomId: config.roomId, message: 'not saved', clientMsgId: 'outage' });
    assert.equal((await denied).code, 'UNAUTHORIZED');
  } finally { globalThis.fetch = original; patient.disconnect(); }
});


test('membership changes invalidate previous joins for all message and signaling actions', async () => {
  const patient = await connect(config.tokens.patient); await join(patient);
  await state({ patient: 'attacker' });
  try {
    for (const [event, channel, payload] of [
      ['chat:history', 'chat:error', { roomId: config.roomId }],
      ['chat:message', 'chat:error', { roomId: config.roomId, message: 'Former participant' }],
      ...['webrtc:offer', 'webrtc:answer', 'webrtc:ice-candidate', 'consultation:end-call'].map(event => [event, 'error', { roomId: config.roomId, offer: {}, answer: {}, candidate: {} }]),
    ]) {
      const denied = once(patient, channel); patient.emit(event, payload); assert.equal((await denied).code, 'UNAUTHORIZED');
    }
  } finally { await state({ patient: 'patient' }); patient.disconnect(); }
});

test('an access token expiring during an established session disconnects the socket', async () => {
  const claims = jwt.decode(config.tokens.patient); delete claims.exp; delete claims.iat;
  const token = jwt.sign(claims, secret, { expiresIn: 2 });
  const patient = await connect(token); const disconnected = once(patient, 'disconnect');
  await disconnected; assert.equal(patient.connected, false);
});
