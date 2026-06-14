import { Mic, PhoneOff, Video } from 'lucide-react';

export function VideoCall({ roomId, connected }: { roomId: string; connected: boolean }) {
  return (
    <section className="panel video-panel">
      <div className="video-surface">
        <Video size={58} />
        <strong>Consultation room</strong>
        <span>{roomId}</span>
      </div>
      <div className="toolbar">
        <span className="muted">{connected ? 'Realtime connected' : 'Connecting'}</span>
        <button className="icon-button" aria-label="Toggle microphone"><Mic size={18} /></button>
        <button className="danger" aria-label="End call"><PhoneOff size={18} /></button>
      </div>
    </section>
  );
}
