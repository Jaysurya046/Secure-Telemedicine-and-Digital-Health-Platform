import { io } from 'socket.io-client';
import { getAccessToken } from './api';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:3002';

export function createSocket() {
  return io(WS_URL, {
    transports: ['websocket'],
    auth: { token: getAccessToken() }
  });
}
