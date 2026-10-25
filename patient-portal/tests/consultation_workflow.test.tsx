import './setup_dom.mjs';
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import type { Socket } from 'socket.io-client';
import { Chat } from '../src/components/Chat';
import { clearTokens, setTokens } from '../src/lib/api';
import { OpenConsultationButton } from '../src/components/OpenConsultationButton';
import { PatientConsultation } from '../src/components/PatientConsultation';

const original = globalThis.fetch;
afterEach(() => { cleanup(); globalThis.fetch = original; clearTokens(); });
const response = (body: unknown, status=200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
function fakeSocket() {
  const listeners = new Map<string, ((data?: unknown) => void)[]>();
  const sent: { event: string; data: any }[] = [];
  const fake = {
    connected: true,
    on(event: string, listener: (data?: unknown) => void) { listeners.set(event, [...(listeners.get(event)||[]), listener]); return fake; },
    off() { return fake; },
    emit(event: string, data: any) {
      sent.push({ event, data });
      if (event === 'consultation:join') queueMicrotask(() => trigger('consultation:joined', data));
      return fake;
    },
    disconnect() { fake.connected = false; return fake; },
  };
  const trigger = (event: string, data?: unknown) => { for (const fn of listeners.get(event)||[]) fn(data); };
  return { socket: fake as unknown as Socket, fake, sent, trigger, factory: () => fake as unknown as Socket };
}

test('rendered chat sends a stable retry key, acknowledges, deduplicates and disconnects', async () => {
  globalThis.fetch = async () => response({ results: [], next: null });
  const fake = fakeSocket();
  const view = render(<Chat consultationId="consultation-real" roomId="room-real" socketFactory={fake.factory} />);
  await waitFor(() => assert.equal(screen.getByRole('button', { name: 'Send message' }).hasAttribute('disabled'), true));
  await waitFor(() => assert.ok(screen.getByText('Connected')));
  fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Hello from screen' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
  const sent = fake.sent.find(item => item.event === 'chat:message')!.data;
  assert.equal(sent.roomId, 'room-real'); assert.equal(sent.message, 'Hello from screen'); assert.ok(sent.clientMsgId);
  await act(async () => fake.trigger('chat:error', { message: 'Temporary failure', clientMsgId: sent.clientMsgId }));
  fireEvent.click(screen.getByRole('button', { name: 'Retry message' }));
  const retry = fake.sent.filter(item => item.event === 'chat:message')[1].data;
  assert.equal(retry.clientMsgId, sent.clientMsgId);
  await act(async () => {
    fake.trigger('chat:ack', { clientMsgId: sent.clientMsgId, messageId: 'server-id', sentAt: '2026-10-25T10:00:00Z' });
    const live = { id: 'server-id', roomId: 'room-real', message: sent.message, sender: { id: 'p1', email: 'p@test.com' }, sentAt: '2026-10-25T10:00:00Z', clientMsgId: sent.clientMsgId };
    fake.trigger('chat:message', live); fake.trigger('chat:message', live);
  });
  assert.equal(screen.getAllByText('Hello from screen').length, 1);
  assert.equal(screen.queryByText('Sending…'), null);
  view.unmount(); assert.equal(fake.fake.connected, false);
});

test('reconnect merges multiple history pages without losing live messages', async () => {
  const requests: string[] = [];
  const message = (id: string) => ({ id, message: 'History '+id, sender: 'p1', sender_email: 'p@test.com', sent_at: '2026-10-25T10:00:00Z', client_msg_id: '' });
  globalThis.fetch = async input => {
    const url = String(input); requests.push(url);
    return response({ results: [message(url.includes('page=2') ? 'older' : 'latest')], next: url.includes('page=2') ? null : '/?page=2' });
  };
  const fake = fakeSocket(); render(<Chat consultationId="c1" roomId="r1" socketFactory={fake.factory} />);
  await waitFor(() => assert.ok(screen.getByRole('button', { name: 'Load earlier messages' })));
  fireEvent.click(screen.getByRole('button', { name: 'Load earlier messages' }));
  await waitFor(() => assert.ok(screen.getByText('History older')));
  await act(async () => { fake.trigger('disconnect'); fake.trigger('connect'); });
  await waitFor(() => assert.ok(requests.filter(url => url.includes('page=2')).length >= 2));
  assert.equal(screen.getAllByText('History latest').length, 1);
  assert.equal(screen.getAllByText('History older').length, 1);
});

test('closed consultation disables sending and history errors are visible', async () => {
  globalThis.fetch = async () => response({ detail: 'History unavailable' }, 503);
  const fake = fakeSocket(); render(<Chat consultationId="c1" roomId="r1" closed socketFactory={fake.factory} />);
  await waitFor(() => assert.ok(screen.getByRole('alert')));
  assert.equal(screen.getByLabelText('Message').hasAttribute('disabled'), true);
  assert.ok(screen.getByText('This consultation is closed for new messages.'));
});

test('patient opens real consultation room, has read-only clinical information and logout unmounts chat', async () => {
  setTokens({ access: 'patient-access', refresh: 'patient-refresh' });
  const fake = fakeSocket();
  globalThis.fetch = async input => String(input).includes('/messages/') ? response({ results: [], next: null }) :
    response({ id: 'c-real', room_id: 'r-real', status: 'in_progress', diagnosis: 'Recorded diagnosis', clinical_notes: 'Recorded notes', follow_up_required: true, follow_up_notes: 'Next week', doctor_detail: { email: 'doctor@test.com' } });
  render(<PatientConsultation id="c-real" socketFactory={fake.factory} />);
  await waitFor(() => assert.ok(screen.getByText('Diagnosis: Recorded diagnosis')));
  assert.equal(screen.queryByText('Start Consultation'), null); assert.equal(screen.queryByText('End Consultation'), null);
  await waitFor(() => assert.ok(fake.sent.some(item => item.event === 'consultation:join' && item.data.roomId === 'r-real')));
  await act(async () => clearTokens());
  await waitFor(() => assert.equal(fake.fake.connected, false));
  assert.equal(screen.queryByText('Diagnosis: Recorded diagnosis'), null);
});

test('rendered appointment entry opens existing, creates missing and recovers a creation race using real consultation IDs', async () => {
  for (const mode of ['existing', 'create', 'race']) {
    setTokens({ access: 'access', refresh: 'refresh' });
    let lookups = 0; const posted: unknown[] = []; const navigation: string[] = [];
    globalThis.fetch = async (input, init) => {
      if (init?.method === 'POST') {
        posted.push(JSON.parse(String(init.body)));
        return mode === 'race' ? response({ detail: 'Already created' }, 400) : response({ id: 'created-consultation' }, 201);
      }
      lookups++;
      return response({ results: mode === 'existing' || lookups > 1 ? [{ id: 'existing-consultation' }] : [] });
    };
    const view = render(<OpenConsultationButton appointmentId="appointment-123" navigate={url => navigation.push(url)} />);
    fireEvent.click(screen.getByText('Open Consultation'));
    await waitFor(() => assert.equal(navigation.length, 1));
    assert.equal(navigation[0], '/consultation/'+(mode === 'create' ? 'created-consultation' : 'existing-consultation'));
    if (mode !== 'existing') assert.deepEqual(posted, [{ appointment: 'appointment-123' }]);
    view.unmount();
  }
});
