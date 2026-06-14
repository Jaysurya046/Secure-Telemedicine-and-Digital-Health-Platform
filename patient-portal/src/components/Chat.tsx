'use client';

import { useEffect, useState } from 'react';
import type { Socket } from 'socket.io-client';
import { Send } from 'lucide-react';

type ChatMessage = {
  id: string;
  message: string;
  sender?: { email?: string };
  sentAt: string;
};

export function Chat({ socket, roomId }: { socket: Socket | null; roomId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');

  useEffect(() => {
    if (!socket) return;
    const onMessage = (message: ChatMessage) => setMessages((current) => [...current, message]);
    const onHistory = (history: ChatMessage[]) => setMessages(history);
    socket.on('chat:message', onMessage);
    socket.on('chat:history', onHistory);
    socket.emit('chat:history', { roomId });
    return () => {
      socket.off('chat:message', onMessage);
      socket.off('chat:history', onHistory);
    };
  }, [socket, roomId]);

  function sendMessage() {
    if (!socket || !draft.trim()) return;
    socket.emit('chat:message', { roomId, message: draft });
    setDraft('');
  }

  return (
    <section className="panel flex h-full min-h-[28rem] flex-col">
      <div className="border-b border-slate-200 px-4 py-3 font-bold">Consultation chat</div>
      <div className="flex-1 space-y-3 overflow-auto p-4">
        {messages.map((message) => (
          <div key={message.id} className="rounded-md bg-slate-100 p-3 text-sm">
            <div className="font-bold text-ink">{message.sender?.email || 'Participant'}</div>
            <p className="mt-1 text-slate-700">{message.message}</p>
          </div>
        ))}
      </div>
      <div className="flex gap-2 border-t border-slate-200 p-3">
        <input className="w-full rounded-md border border-slate-300 px-3 py-2" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Type a message" />
        <button className="btn btn-primary" onClick={sendMessage} aria-label="Send message"><Send className="h-4 w-4" aria-hidden /></button>
      </div>
    </section>
  );
}
