import { registerChatHandlers } from '../chat/service.js';
import { registerWebRtcSignaling } from '../webrtc/signaling.js';
import { authorize, deliver, handle, validRoom } from '../auth/rooms.js';

export function registerSocketHandlers(io) {
  io.on('connection', (socket) => {
    socket.emit('connected', { socketId: socket.id, user: socket.user });
    handle(socket, 'consultation:join', 'error', async ({ roomId }, reject) => {
      if (!validRoom(roomId)) return reject('INVALID_PAYLOAD', 'roomId is required.');
      const room = await authorize(socket, roomId);
      if (!room) return reject('UNAUTHORIZED', 'Not authorized for this room.');
      if (!socket.connected) return;
      await socket.join(roomId);
      socket.emit('consultation:joined', { roomId, consultationId: room.consultationId, status: room.status });
      await deliver(io, roomId, 'consultation:participant-joined', { user: socket.user }, socket.id);
    });
    handle(socket, 'consultation:leave', 'error', async ({ roomId }, reject) => {
      if (!validRoom(roomId)) return reject('INVALID_PAYLOAD', 'roomId is required.');
      if (!socket.rooms.has(roomId)) return;
      if (await authorize(socket, roomId)) await deliver(io, roomId, 'consultation:participant-left', { user: socket.user }, socket.id);
      await socket.leave(roomId);
    });
    handle(socket, 'presence:update', 'error', async ({ status }, reject) => {
      if (!['online', 'away', 'busy'].includes(status)) return reject('INVALID_PAYLOAD', 'Invalid presence status.');
      for (const roomId of socket.rooms) {
        if (roomId !== socket.id && await authorize(socket, roomId))
          await deliver(io, roomId, 'presence:update', { user: socket.user, status, at: new Date().toISOString() }, socket.id);
      }
    });
    socket.on('disconnecting', () => {
      for (const roomId of socket.rooms) {
        if (roomId !== socket.id) deliver(io, roomId, 'consultation:participant-left', { user: socket.user }, socket.id).catch(() => {});
      }
    });
    registerChatHandlers(socket, io);
    registerWebRtcSignaling(socket, io);
  });
}
