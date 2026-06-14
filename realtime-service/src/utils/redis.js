import Redis from 'ioredis';

export async function createRedisClients() {
  const url = process.env.REDIS_URL;
  if (!url) {
    return { publisher: null, subscriber: null };
  }

  try {
    const publisher = new Redis(url, { lazyConnect: true, maxRetriesPerRequest: 2 });
    const subscriber = new Redis(url, { lazyConnect: true, maxRetriesPerRequest: 2 });
    await Promise.all([publisher.connect(), subscriber.connect()]);
    return { publisher, subscriber };
  } catch (error) {
    console.warn('Redis unavailable, realtime service will run in single-node mode:', error.message);
    return { publisher: null, subscriber: null };
  }
}
