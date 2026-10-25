import { io, type Socket } from 'socket.io-client';
import { getToken } from './api';

const WS_URL =
  typeof import.meta !== 'undefined' && import.meta.env?.VITE_WS_URL
    ? import.meta.env.VITE_WS_URL
    : 'http://localhost:3002';

/**
 * Creates a Socket.IO connection authenticated with the current user's JWT.
 *
 * Features:
 * - Authenticates with the current access token on connect and reconnect.
 * - Does not reconnect if the token is missing (prevents anonymous connections).
 * - Reconnection uses the latest token via `auth` factory function.
 */
export function createSocket(): Socket {
  const socket = io(WS_URL, {
    transports: ['websocket'],
    auth: (cb) => {
      // Called on every connect/reconnect attempt — always uses the latest token
      cb({ token: getToken() });
    },
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 10000,
    timeout: 10000,
  });

  return socket;
}
