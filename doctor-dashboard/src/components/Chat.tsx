'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { Socket } from 'socket.io-client';
import { apiFetch } from '../services/api';
import { createSocket } from '../services/websocket';

type Message = { id: string; message: string; sender: string; sender_email: string; sent_at: string; client_msg_id: string; pending?: boolean; failed?: boolean };
type History = { results: Message[]; next: string | null };
type LiveMessage = { id: string; message: string; sender: { id: string; email: string }; sentAt: string; clientMsgId: string; roomId: string };
type Pending = { key: string; text: string };

export function Chat({ consultationId, roomId, closed = false, socketFactory = createSocket }: {
  consultationId: string; roomId: string; closed?: boolean; socketFactory?: () => Socket;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [online, setOnline] = useState(false);
  const [page, setPage] = useState(1);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const pending = useRef(new Map<string, Pending>());
  const socket = useRef<Socket | null>(null);
  const ownId = useRef('');
  const generation = useRef(0);
  const everJoined = useRef(false);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const merge = useCallback((incoming: Message[]) => {
    setMessages(previous => {
      const map = new Map(previous.map(m => [m.id, m]));
      for (const message of incoming) {
        // Only our optimistic messages can be replaced by a retry key.
        for (const [id, old] of map) {
          if (old.pending && ownId.current && message.sender === ownId.current && old.client_msg_id === message.client_msg_id) map.delete(id);
        }
        map.set(message.id, message);
      }
      return [...map.values()].sort((a, b) => a.sent_at.localeCompare(b.sent_at) || a.id.localeCompare(b.id));
    });
  }, []);

  const load = useCallback(async (targetPage: number, recoverAll = false) => {
    const current = generation.current;
    setLoading(true);
    try {
      let next = true;
      let p = targetPage;
      while (next) {
        const data = await apiFetch<History>(`/api/consultations/${consultationId}/messages/?page=${p}&page_size=50`);
        if (current !== generation.current) return;
        merge(data.results);
        next = Boolean(data.next);
        setPage(p); setMore(next);
        if (!recoverAll) break;
        p += 1;
      }
    } catch (err) {
      if (current === generation.current) setError(err instanceof Error ? err.message : 'Could not load history.');
    } finally { if (current === generation.current) setLoading(false); }
  }, [consultationId, merge]);

  function transmit(item: Pending) {
    const connection = socket.current;
    if (!connection?.connected) return;
    setMessages(list => list.map(m => m.client_msg_id === item.key && m.pending ? { ...m, failed: false } : m));
    const current = generation.current;
    const oldTimer = timers.current.get(item.key);
    if (oldTimer) clearTimeout(oldTimer);
    timers.current.set(item.key, setTimeout(() => {
      if (current !== generation.current) return;
      setMessages(list => list.map(m => m.client_msg_id === item.key && m.pending ? { ...m, failed: true } : m));
      setError('Message acknowledgement timed out. Retry uses the same message key.');
    }, 8000));
    connection.emit('chat:message', { roomId, message: item.text, clientMsgId: item.key });
  }

  useEffect(() => {
    let active = true;
    generation.current += 1;
    everJoined.current = false;
    setMessages([]); setDraft(''); setError(''); setOnline(false); setPage(1); setMore(false);
    const connection = socketFactory();
    socket.current = connection;
    const join = () => { connection.emit('consultation:join', { roomId }); };
    connection.on('connect', join);
    connection.on('connected', (data: { user: { id: string } }) => { ownId.current = data.user.id; });
    connection.on('consultation:joined', (data: { roomId: string }) => {
      if (!active || data.roomId !== roomId) return;
      setOnline(true); setError('');
      const recover = everJoined.current;
      everJoined.current = true;
      void load(1, recover); // Initial page stays bounded; reconnect recovers every missed page.
      for (const item of pending.current.values()) transmit(item);
    });
    connection.on('chat:message', (data: LiveMessage) => {
      if (!active || data.roomId !== roomId) return;
      merge([{ id: data.id, message: data.message, sender: data.sender.id, sender_email: data.sender.email,
        sent_at: data.sentAt, client_msg_id: data.clientMsgId }]);
    });
    connection.on('chat:ack', (data: { clientMsgId: string; messageId: string; sentAt: string }) => {
      if (!active) return;
      pending.current.delete(data.clientMsgId);
      clearTimeout(timers.current.get(data.clientMsgId)); timers.current.delete(data.clientMsgId);
      setMessages(list => {
        const saved = list.find(m => m.id === data.messageId && !m.pending);
        return list.flatMap(m => {
          if (m.client_msg_id !== data.clientMsgId || !m.pending) return [m];
          return saved ? [] : [{ ...m, id: data.messageId, sent_at: data.sentAt, pending: false, failed: false }];
        });
      });
    });
    const onError = (data: { message?: string; clientMsgId?: string }) => {
      if (!active) return;
      setError(data.message || 'Connection failed. Please sign in again or retry.');
      if (data.clientMsgId) {
        clearTimeout(timers.current.get(data.clientMsgId));
        setMessages(list => list.map(m => m.client_msg_id === data.clientMsgId && m.pending ? { ...m, failed: true } : m));
      }
    };
    connection.on('chat:error', onError); connection.on('error', onError); connection.on('connect_error', onError);
    connection.on('disconnect', () => { if (active) setOnline(false); });
    if (connection.connected) join();
    void load(1);
    return () => {
      active = false; generation.current += 1;
      connection.emit('consultation:leave', { roomId }); connection.disconnect();
      socket.current = null; pending.current.clear();
      for (const timer of timers.current.values()) clearTimeout(timer);
      timers.current.clear();
    };
  }, [consultationId, roomId, socketFactory, load, merge]);

  function send(event: React.FormEvent) {
    event.preventDefault();
    if (!online || closed || !draft.trim()) return;
    const item = { key: crypto.randomUUID(), text: draft.trim() };
    pending.current.set(item.key, item);
    merge([{ id: item.key, message: item.text, sender: '', sender_email: 'You', sent_at: new Date().toISOString(), client_msg_id: item.key, pending: true }]);
    setDraft(''); setError(''); transmit(item);
  }

  return <section className="panel" aria-label="Consultation chat">
    <h2>Secure chat</h2><p role="status">{online ? 'Connected' : 'Disconnected — reconnecting when available'}</p>
    {error && <p role="alert">{error}</p>}
    <button type="button" disabled={loading} onClick={() => { setError(''); void load(1, true); }}>Refresh history</button>
    {more && <button type="button" disabled={loading} onClick={() => void load(page + 1)}>Load earlier messages</button>}
    {loading && <p>Loading messages…</p>}
    <div aria-label="Messages">{messages.map(m => <article key={m.id}>
      <strong>{m.sender_email}</strong><p>{m.message}</p><time>{new Date(m.sent_at).toLocaleString()}</time>
      {m.pending && <span>{m.failed ? ' Not delivered' : ' Sending…'}</span>}
      {m.pending && m.failed && <button type="button" disabled={!online} onClick={() => {
        const item = pending.current.get(m.client_msg_id); if (item) transmit(item);
      }}>Retry message</button>}
    </article>)}</div>
    <form onSubmit={send}><label>Message<input aria-label="Message" maxLength={2000} value={draft}
      disabled={!online || closed} onChange={event => setDraft(event.target.value)} /></label>
      <button type="submit" disabled={!online || closed || !draft.trim()}>Send message</button>
    </form>
    {closed && <p>This consultation is closed for new messages.</p>}
  </section>;
}
