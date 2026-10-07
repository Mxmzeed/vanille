# vanille.

note taking at its purest form. turn messy thoughts into searchable, organized information.

This repository is at the bootstrap stage described in [bootstrap.md](bootstrap.md). The stack contains runnable service shells, a placeholder main application, an editorial landing page with illustrative examples, and health endpoints. Normal mode, conversational mode, agents, speech processing, and memory intake or retrieval have not been implemented.

## structure

| directory | role | stack |
| --- | --- | --- |
| `frontmatter/` | main application shell | Next.js, React, TypeScript, Tailwind, Motion, GSAP, Three.js |
| `frontpage/` | landing page preview with illustrative examples | Vite, React, TypeScript, Tailwind, Motion |
| `backend/` | intelligence API shell | TypeScript, Fastify |
| `db/` | memory service shell and copied human memory source | Python, FastAPI, Neo4j driver |
| `notes/` | original brainstorming notes | Markdown |

Neo4j runs as a separate database container. Each JavaScript service has its own package manifest and lockfile. The root `package.json` provides commands for working across the services.

The human memory module copied from `~/projects/SageV3` lives in `db/human_memory/`, with its Sage registration wrapper in `db/sage/modules/memory/human_memory/`. These are source copies awaiting integration. The memory service does not import or run them, and their Sage dependencies are not installed by the bootstrap setup. See [the provenance and dependency notes](db/human_memory/README.md) for details.

## run with docker

Install Docker with Compose, then run from the repository root:

```sh
cp -n .env.example .env
docker compose up --build -d --wait
```

The first run builds the images and initializes Neo4j. Allow several minutes, especially on a busy development machine.

The local `.env` is ignored by Git. The example uses local development credentials and the service ports requested for Vanille. Compose publishes ports on `127.0.0.1`.

| service | default local address |
| --- | --- |
| main application | [http://localhost:9101](http://localhost:9101) |
| landing page | [http://localhost:9100](http://localhost:9100) |
| backend health | [http://localhost:9000/health](http://localhost:9000/health) |
| memory service health | [http://localhost:9003/health](http://localhost:9003/health) |
| Neo4j browser | [http://localhost:9004](http://localhost:9004) |
| Neo4j Bolt | `bolt://localhost:9005` |

Neo4j's username is `neo4j`; its initial password comes from `NEO4J_PASSWORD` in `.env`. Named volumes preserve its data and logs. Changing that variable does not reset credentials in an existing database, as described in the [Neo4j Docker documentation](https://neo4j.com/docs/operations-manual/current/docker/introduction/#docker-auth).

```sh
docker compose ps
docker compose logs --follow
docker compose down
```

`docker compose down` stops this stack and keeps the database volumes. The API health endpoints report process availability only; they do not verify memory functionality or a connection to Neo4j.

## local development

Use Node.js 24 (`.nvmrc`), npm 10 or later, Python 3.13 (`.python-version`), and [uv](https://docs.astral.sh/uv/). The JavaScript packages also support Node.js 22.13 or later. uv can provision Python 3.13 when it is not already installed.

```sh
cp -n .env.example .env
npm run setup
docker compose up -d --wait neo4j
```

Run each service in its own terminal:

```sh
npm run dev:frontmatter
npm run dev:frontpage
npm run dev:backend
npm run dev:db
```

The backend and memory service load the root `.env` for local development. Compose uses service hostnames for internal URLs. The main application placeholder and landing page examples do not call either API yet. Compose runs built containers; use the local commands above for live reload, and stop corresponding containers before starting local services on the same ports.

The `*_PORT` variables in `.env` configure Docker's published ports. If you change them, update local development commands, `CORS_ORIGINS`, and local service URLs as appropriate.

## validation

```sh
npm run check
npm run build
docker compose config --quiet
```

The checks cover TypeScript, ESLint, and the new Python service scaffold. They exclude the copied Sage source, whose dependencies and integration remain outside bootstrap scope. Production Dockerfiles and locked dependency installs are supplied for all four service shells.

The initial dependency audit found an upstream [`braces` advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) in Next.js's development lint dependencies, with no patched version available. Both frontend production dependency audits are clean; the landing page and backend full dependency audits are also clean. Lint dependencies remain within the framework's supported version ranges.

Read [AGENTS.md](AGENTS.md) for repository conventions. Source is licensed under [AGPLv3](LICENSE); branding is covered by [TRADEMARK.md](TRADEMARK.md).
