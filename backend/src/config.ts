const port = Number(process.env.PORT ?? 9000);

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error('PORT must be an integer between 1 and 65535.');
}

export const config = {
  host: process.env.HOST ?? '0.0.0.0',
  port,
  corsOrigins: (
    process.env.CORS_ORIGINS ?? 'http://localhost:9101,http://localhost:9100'
  )
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean),
  memoryServiceUrl: process.env.MEMORY_SERVICE_URL ?? 'http://localhost:9003',
};
