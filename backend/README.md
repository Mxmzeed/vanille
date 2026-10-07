vanille backend.

TypeScript and Fastify service bootstrap. The only application route is
`GET /health`, returning `{"status":"ok","service":"backend"}`. CORS preflight
handling is provided by `@fastify/cors`.

Use Node.js 22.13 or newer. The production image uses Node.js 24. From this directory:

```sh
npm ci
npm run dev
npm run lint
npm run typecheck
npm run build
npm start
```

The local `dev` and `start` scripts load `../.env` when present. Existing shell
environment variables take precedence. The Docker image receives configuration
from its runtime environment.

| variable | default | purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | API bind address |
| `PORT` | `9000` | API bind port |
| `CORS_ORIGINS` | `http://localhost:9101,http://localhost:9100` | comma-separated browser origins |
| `MEMORY_SERVICE_URL` | `http://localhost:9003` | reserved memory service address |

The memory service address is configuration only. Agents, orchestration,
conversation, speech, and memory calls have no implementation yet.
