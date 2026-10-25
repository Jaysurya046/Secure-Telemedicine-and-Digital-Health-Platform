import { authorize, deliver, handle, isObject, validRoom } from '../auth/rooms.js';

// Media capture is separate; every existing signaling event is membership checked.
export function registerWebRtcSignaling(socket, io) {
  for (const [event, field] of [['webrtc:offer', 'offer'], ['webrtc:answer', 'answer'], ['webrtc:ice-candidate', 'candidate'], ['consultation:end-call', null]]) {
    handle(socket, event, 'error', async (payload, reject) => {
      const { roomId } = payload;
      if (!validRoom(roomId) || (field && (!isObject(payload[field]) || JSON.stringify(payload[field]).length > 64000)))
        return reject('INVALID_PAYLOAD', 'Invalid signaling payload.');
      const room = await authorize(socket, roomId);
      if (!room || !socket.rooms.has(roomId)) return reject('UNAUTHORIZED', 'Join an authorized room first.');
      if (room.status !== 'in_progress') return reject('INVALID_STATE', 'The consultation is not in progress.');
      await deliver(io, roomId, field ? event : 'consultation:call-ended',
        field ? { [field]: payload[field], from: socket.user } : { endedBy: socket.user }, socket.id);
    });
  }
}
