import { io } from 'socket.io-client';
import { getToken } from './api';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:3002';

export function createSocket() {
  return io(WS_URL, {
    transports: ['websocket'],
    auth: { token: getToken() }
  });
}
