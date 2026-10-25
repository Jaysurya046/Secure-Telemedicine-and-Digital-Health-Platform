import { fetchIdentity, verifyConsultationMembership } from './django_client.js';

export const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
export const validRoom = (room) => typeof room === 'string' && room.length > 0 && room.length <= 64;

// Never cache authorization: account state, membership and tokens can change.
export async function authorize(socket, roomId) {
  if (!validRoom(roomId)) return null;
  const user = await fetchIdentity(socket.accessToken);
  if (!user || String(user.id) !== String(socket.user.id)) { await socket.leave(roomId); return null; }
  socket.user = user;
  const room = await verifyConsultationMembership(socket.accessToken, roomId);
  if (!room) await socket.leave(roomId);
  return room;
}

// Recheck recipients too, so a revoked participant cannot keep receiving broadcasts.
export async function deliver(io, roomId, event, data, excludeId) {
  const recipients = await io.in(roomId).fetchSockets();
  await Promise.all(recipients.map(async (peer) => {
    if (peer.id === excludeId) return;
    if (await authorize(peer, roomId)) peer.emit(event, data);
  }));
}

export function handle(socket, event, channel, fn) {
  socket.on(event, async (payload, ack) => {
    const reject = (code, message) => {
      const error = { code, message, clientMsgId: payload?.clientMsgId };
      socket.emit(channel, error);
      if (typeof ack === 'function') ack({ error });
    };
    if (!isObject(payload)) return reject('INVALID_PAYLOAD', 'Expected an object.');
    try { await fn(payload, reject, ack); }
    catch { reject('UNAVAILABLE', 'The service could not verify or complete this request.'); }
  });
}
