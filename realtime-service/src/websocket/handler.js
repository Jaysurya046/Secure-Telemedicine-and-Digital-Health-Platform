import { registerChatHandlers } from '../chat/service.js';
import { registerWebRtcSignaling } from '../webrtc/signaling.js';

export function registerSocketHandlers(io) {
  io.on('connection', (socket) => {
    socket.emit('connected', {
      socketId: socket.id,
      user: socket.user,
      connectedAt: new Date().toISOString(),
    });

    socket.on('consultation:join', ({ roomId }) => {
      if (!roomId) {
        socket.emit('error', { message: 'roomId is required' });
        return;
      }
      socket.join(roomId);
      socket.to(roomId).emit('consultation:participant-joined', { user: socket.user });
      socket.emit('consultation:joined', { roomId });
    });

    socket.on('consultation:leave', ({ roomId }) => {
      socket.leave(roomId);
      socket.to(roomId).emit('consultation:participant-left', { user: socket.user });
    });

    socket.on('presence:update', ({ status }) => {
      socket.broadcast.emit('presence:update', { user: socket.user, status, at: new Date().toISOString() });
    });

    registerChatHandlers(socket, io);
    registerWebRtcSignaling(socket, io);
  });
}
