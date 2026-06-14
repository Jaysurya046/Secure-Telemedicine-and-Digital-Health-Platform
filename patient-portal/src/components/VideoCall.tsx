'use client';

import { Mic, PhoneOff, Video } from 'lucide-react';
import type { Socket } from 'socket.io-client';

export function VideoCall({ roomId, socket }: { roomId: string; socket: Socket | null }) {
  return (
    <section className="panel overflow-hidden">
      <div className="relative aspect-video bg-[linear-gradient(135deg,#172033,#2f9e8f_55%,#e46d5f)]">
        <div className="absolute inset-0 grid place-items-center text-center text-white">
          <div>
            <Video className="mx-auto h-14 w-14" aria-hidden />
            <h1 className="mt-4 text-2xl font-black">Secure video room</h1>
            <p className="mt-2 text-sm opacity-90">Room {roomId}</p>
          </div>
        </div>
        <div className="absolute bottom-4 right-4 h-28 w-40 rounded-md border border-white/50 bg-white/20 backdrop-blur" />
      </div>
      <div className="flex items-center justify-between p-4">
        <div className="text-sm font-semibold text-slate-600">{socket?.connected ? 'Connected to realtime service' : 'Waiting for connection'}</div>
        <div className="flex gap-2">
          <button className="btn btn-secondary" aria-label="Toggle microphone"><Mic className="h-4 w-4" aria-hidden /></button>
          <button className="btn bg-coral text-white" aria-label="End call"><PhoneOff className="h-4 w-4" aria-hidden /></button>
        </div>
      </div>
    </section>
  );
}
