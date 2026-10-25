import './setup_dom.mjs';
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import type { Socket } from 'socket.io-client';
import { Chat } from '../src/components/Chat';
import { clearTokens, setTokens } from '../src/services/api';
import { Consultation } from '../src/pages/Consultation';

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

test('doctor starts consultation, submits clinical completion and sees persisted summary', async () => {
  const fake = fakeSocket(); const requests: { path: string; data: any }[] = [];
  let consultation = { id: 'c1', room_id: 'r1', status: 'scheduled', diagnosis: '', clinical_notes: '', follow_up_required: false, follow_up_notes: '', patient_detail: { email: 'patient@test.com' } };
  globalThis.fetch = async (input, options) => {
    const path = String(input);
    if (path.includes('/messages/')) return response({ results: [], next: null });
    if (options?.method === 'POST') {
      const data = JSON.parse(String(options.body)); requests.push({ path, data });
      consultation = { ...consultation, ...data, status: path.includes('/start/') ? 'in_progress' : 'completed' };
    }
    return response(consultation);
  };
  let completed = 0;
  render(<Consultation consultationId="c1" socketFactory={fake.factory} onCompleted={() => completed++} />);
  await waitFor(() => assert.ok(screen.getByText('Start Consultation')));
  fireEvent.click(screen.getByText('Start Consultation'));
  await waitFor(() => assert.ok(screen.getByText('End Consultation')));
  fireEvent.click(screen.getByText('End Consultation'));
  fireEvent.change(screen.getByLabelText('Diagnosis'), { target: { value: 'Documented diagnosis' } });
  fireEvent.change(screen.getByLabelText('Clinical Notes'), { target: { value: 'Clinical findings' } });
  fireEvent.click(screen.getByLabelText('Follow-up Required'));
  fireEvent.click(screen.getByText('Confirm End'));
  await waitFor(() => assert.ok(screen.getByText('Clinical Summary')));
  assert.equal(requests[1].data.diagnosis, 'Documented diagnosis');
  assert.equal(requests[1].data.follow_up_required, true); assert.equal(completed, 1);
  assert.equal(screen.queryByText('Start Consultation'), null);
});
