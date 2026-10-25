import { randomUUID } from 'crypto';
import { persistMessage, fetchMessageHistory } from '../auth/django_client.js';
import { authorize, deliver, handle, validRoom } from '../auth/rooms.js';

export function registerChatHandlers(socket, io) {
  handle(socket, 'chat:history', 'chat:error', async ({ roomId, page = 1, pageSize = 50 }, reject) => {
    if (!validRoom(roomId) || !Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1 || pageSize > 200)
      return reject('INVALID_PAYLOAD', 'Invalid room or pagination.');
    const room = await authorize(socket, roomId);
    if (!room) return reject('UNAUTHORIZED', 'Not authorized for this room.');
    const history = await fetchMessageHistory({ consultationId: room.consultationId, userToken: socket.accessToken, page, pageSize });
    if (!history) return reject('HISTORY_UNAVAILABLE', 'Could not retrieve history.');
    socket.emit('chat:history', { roomId, ...history });
  });

  handle(socket, 'chat:message', 'chat:error', async ({ roomId, message, clientMsgId }, reject, ack) => {
    if (!validRoom(roomId) || typeof message !== 'string' || !message.trim() || message.length > 2000 ||
        (clientMsgId !== undefined && (typeof clientMsgId !== 'string' || !clientMsgId || clientMsgId.length > 64)))
      return reject('INVALID_PAYLOAD', 'A message of 1–2000 characters and a valid retry key are required.');
    const room = await authorize(socket, roomId);
    if (!room) return reject('UNAUTHORIZED', 'Not authorized for this room.');
    const key = clientMsgId || randomUUID();
    const persisted = await persistMessage({ consultationId: room.consultationId, userToken: socket.accessToken, message: message.trim(), clientMsgId: key });
    if (!persisted) return reject('PERSIST_FAILED', 'Message could not be saved. Retry with the same key.');
    const receipt = { clientMsgId: key, messageId: persisted.id, sentAt: persisted.sent_at };
    socket.emit('chat:ack', receipt);
    if (typeof ack === 'function') ack(receipt);
    await deliver(io, roomId, 'chat:message', {
      id: persisted.id, roomId, consultationId: room.consultationId, message: persisted.message,
      sender: { id: String(persisted.sender), email: persisted.sender_email, role: socket.user.role },
      sentAt: persisted.sent_at, clientMsgId: key,
    });
  });
}
