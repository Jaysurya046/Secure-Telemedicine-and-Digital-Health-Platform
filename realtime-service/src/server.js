import 'dotenv/config';
import express from 'express';
import http from 'http';
import cors from 'cors';
import helmet from 'helmet';
import { Server } from 'socket.io';

import { authenticateSocket } from './auth/middleware.js';
import { createRedisClients } from './utils/redis.js';
import { registerSocketHandlers } from './websocket/handler.js';

const port = Number(process.env.PORT || 3002);
const origins = (process.env.CLIENT_ORIGINS || 'http://localhost:3000,http://localhost:3001')
  .split(',')
  .map((origin) => origin.trim());

const app = express();
app.use(helmet());
app.use(cors({ origin: origins, credentials: true }));
app.use(express.json());

app.get('/health', (_req, res) => {
  res.json({ status: 'healthy', service: 'telemedicine-realtime' });
});

app.get('/ready', async (_req, res) => {
  res.json({ status: 'ready', redis: Boolean(globalThis.redisPublisher) });
});

const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: origins, credentials: true },
  path: '/socket.io',
});

const redis = await createRedisClients();
globalThis.redisPublisher = redis.publisher;
globalThis.redisSubscriber = redis.subscriber;

io.use(authenticateSocket);
registerSocketHandlers(io);

server.listen(port, () => {
  console.log(`Realtime service listening on ${port}`);
});
