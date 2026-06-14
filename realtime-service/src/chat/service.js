import { randomUUID } from 'crypto';

const recentMessages = new Map();

export function registerChatHandlers(socket, io) {
  socket.on('chat:history', ({ roomId }) => {
    socket.emit('chat:history', recentMessages.get(roomId) || []);
  });

  socket.on('chat:message', ({ roomId, message }) => {
    if (!roomId || !message?.trim()) {
      return;
    }

    const payload = {
      id: randomUUID(),
      roomId,
      message: message.trim(),
      sender: socket.user,
      sentAt: new Date().toISOString(),
    };

    const history = recentMessages.get(roomId) || [];
    history.push(payload);
    recentMessages.set(roomId, history.slice(-100));

    io.to(roomId).emit('chat:message', payload);
    globalThis.redisPublisher?.publish('telemedicine:chat', JSON.stringify(payload)).catch(() => {});
  });
}
