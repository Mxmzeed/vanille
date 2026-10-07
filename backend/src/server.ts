import cors from '@fastify/cors';
import Fastify from 'fastify';

import { config } from './config.js';

const app = Fastify({ logger: true });

await app.register(cors, { origin: config.corsOrigins });

app.get('/health', async () => ({ status: 'ok', service: 'backend' }));

for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.once(signal, () => {
    void app.close().catch((error: unknown) => {
      app.log.error(error);
      process.exitCode = 1;
    });
  });
}

try {
  await app.listen({ host: config.host, port: config.port });
} catch (error) {
  app.log.error(error);
  process.exitCode = 1;
}
