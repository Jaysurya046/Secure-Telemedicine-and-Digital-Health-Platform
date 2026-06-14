import { useEffect, useState } from 'react';
import type { Socket } from 'socket.io-client';
import { MessageSquare, Send } from 'lucide-react';
import { VideoCall } from '../components/VideoCall';
import { createSocket } from '../services/websocket';

export function Consultation({ roomId }: { roomId: string }) {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<any[]>([]);

  useEffect(() => {
    const connection = createSocket();
    connection.emit('consultation:join', { roomId });
    connection.on('chat:message', (message) => setMessages((current) => [...current, message]));
    setSocket(connection);
    return () => connection.disconnect();
  }, [roomId]);

  function send() {
    socket?.emit('chat:message', { roomId, message: draft });
    setDraft('');
  }

  return (
    <section className="consult-grid">
      <VideoCall roomId={roomId} connected={Boolean(socket?.connected)} />
      <div className="panel chat">
        <div className="panel-title"><MessageSquare size={18} />Chat</div>
        <div className="messages">
          {messages.map((message) => <p key={message.id}><strong>{message.sender?.email || 'Patient'}:</strong> {message.message}</p>)}
        </div>
        <div className="composer">
          <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Message patient" />
          <button className="primary icon-only" onClick={send} aria-label="Send message"><Send size={16} /></button>
        </div>
      </div>
    </section>
  );
}
