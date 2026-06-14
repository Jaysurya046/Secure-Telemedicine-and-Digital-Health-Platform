'use client';

import { useEffect, useState } from 'react';
import type { Socket } from 'socket.io-client';
import { AppNav } from '@/components/AppNav';
import { Chat } from '@/components/Chat';
import { VideoCall } from '@/components/VideoCall';
import { createSocket } from '@/lib/websocket';

export default function ConsultationPage({ params }: { params: { id: string } }) {
  const [socket, setSocket] = useState<Socket | null>(null);

  useEffect(() => {
    const connection = createSocket();
    connection.emit('consultation:join', { roomId: params.id });
    setSocket(connection);
    return () => {
      connection.emit('consultation:leave', { roomId: params.id });
      connection.disconnect();
    };
  }, [params.id]);

  return (
    <main className="app-shell">
      <AppNav />
      <section className="mx-auto grid max-w-6xl gap-5 px-5 py-8 lg:grid-cols-[1.4fr_0.8fr]">
        <VideoCall roomId={params.id} socket={socket} />
        <Chat roomId={params.id} socket={socket} />
      </section>
    </main>
  );
}
