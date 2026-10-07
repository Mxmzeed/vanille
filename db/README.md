vanille db.

Python and FastAPI memory service bootstrap. Its only route is `GET /health`,
returning `{"status":"ok","service":"db"}`. This reports process health;
it does not connect to Neo4j.

Use Python 3.13 and uv. From this directory:

```sh
uv sync --locked
uv run --env-file ../.env uvicorn vanille_db.main:app --host 127.0.0.1 --port 9003 --reload
uv run --locked ruff check src
uv run --locked python -m compileall -q src
```

The root `.env` supplies these reserved graph settings for future integration:

| variable | local development value | purpose |
| --- | --- | --- |
| `NEO4J_URI` | `bolt://localhost:9005` | graph connection URI |
| `NEO4J_USERNAME` | `neo4j` | graph username |
| `NEO4J_PASSWORD` | set in the root `.env` | graph password |

The official `neo4j` driver is installed, but no connection, queries, intake,
extraction, retrieval, or memory agents are implemented. The Docker image runs
the bootstrap API on `0.0.0.0:9003`.

Source copied from Sage lives under `human_memory/` and `sage/` as a separate reference. It is not
installed, imported, linted, or included in the bootstrap image. Its dependencies
and integration remain outside this scaffold.
