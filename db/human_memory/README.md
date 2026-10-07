# inherited human memory source

This is an unchanged source snapshot from `/home/mamz/projects/SageV3`, copied
on 2026-10-06 for Vanille's bootstrap. The upstream checkout was at commit
`03d66b8cca11b088df9d4446567311688289f8e7`, with no local changes in these source
paths when copied.

| upstream source | vanille destination |
| --- | --- |
| `backend/src/human_memory/` | `db/human_memory/` |
| `backend/src/sage/modules/memory/human_memory/` | `db/sage/modules/memory/human_memory/` |

The snapshot includes seven core Python files plus the original provider's two
Python files and `module.yaml`. All ten inherited files are byte-for-byte
copies. `SOURCE_SHA256SUMS` records their hashes relative to `db/`.

The core contains evidence-backed belief, event, episode, prospective-memory,
temporal, extraction, storage, and retrieval source. The companion Sage provider
and manifest retain their original module identity and entrypoint. Neither is
registered, imported, or started by the Vanille memory service scaffold.

## dependencies left for future integration

The inherited source is not a standalone runnable package. Its original imports
are preserved, and the following upstream source dependencies were deliberately
not copied:

- `backend/src/memory/actions.py` for the Neo4j session helper.
- `backend/src/memory/agents.py` for candidate contracts and model agents.
- `backend/src/memory/contracts.py` for intake and retrieval contracts.
- `backend/src/memory/pipeline.py` for intake gating and verification helpers.
- `backend/src/memory/validation.py` for evidence validation.
- `backend/src/memory/helpers/openai_embed.py` for embeddings.
- `backend/src/sage/settings.py` for Sage runtime settings.

These dependencies have their own model, embedding, graph, configuration, and
runtime dependencies. The copied files directly import `pydantic`,
`langchain_core`, and `redis.asyncio`; no Sage dependency was added to Vanille's
Python environment. Sage's `backend/requirements.txt` is the upstream dependency
reference, rather than an installation manifest for this scaffold.

The retained module manifest names `NEO4J_URI`, `NEO4J_USER`, and
`NEO4J_PASSWORD`. It contains environment-variable names only. Selecting a
configuration contract, copying companion packages, and adapting imports remain
future integration work.

No credentials, `.env` files, bytecode caches, virtual environments, runtime
databases, retained memory data, tests, or unrelated Sage modules were copied.
No upstream repository-level license file or license notice specific to these
module files was found in the source checkout. Vanille's existing root license
and trademark files are unchanged.
