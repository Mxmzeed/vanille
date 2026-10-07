# vanille repository guidance

Read `bootstrap.md` before changing the architecture or product behavior. The project is currently in its bootstrap stage. Keep scaffolding minimal. Product implementation requires an explicit request from the user.

## service boundaries

- `frontmatter/` is the main application shell, using Next.js, React, TypeScript, Tailwind, Motion, GSAP, and Three.js.
- `frontpage/` is the landing page shell, using Vite, React, TypeScript, Tailwind, and Motion.
- `backend/` is the TypeScript intelligence API and future orchestration boundary.
- `db/` is the Python memory service and home for the copied human memory module. Neo4j runs as a separate Compose service.
- `notes/` contains existing brainstorming material. Preserve it unless a request specifically concerns those notes.

The JavaScript services are independent packages with their own lockfiles. The root package provides orchestration commands. Python dependencies are declared in `db/pyproject.toml` and locked in `db/uv.lock`.

## bootstrap scope

Keep the web apps as static placeholders and the APIs as health endpoints until product work is requested. Do not add modes, agent prompts, speech routes, concept editing, memory extraction, retrieval, or demos during bootstrap. Copying an existing memory module does not authorize integrating or modifying its behavior.

Do not guess a Sage package or add provider credentials. Keep copied source separate from the memory service scaffold and record its provenance. Dependency and source integration can be decided when that work is requested.

## product constraints

User-facing text uses lowercase and simple punctuation. The palette is beige, brown, white, and onyx. Stored concepts are managed through the eventual normal and conversational modes rather than manual editing. Vanille may support planning and architecture discussions, but code task execution is outside its product scope.

## working conventions

Never commit `.env`, provider credentials, runtime databases, dependency directories, or generated output. Keep `.env.example` synchronized with documented configuration. Preserve the existing AGPLv3 license and trademark notice.

Run the relevant service typecheck, lint, and build commands for scaffold changes. `npm run check` checks the new scaffold; inherited memory source should be validated separately once its dependencies and integration are in scope. Use smoke checks for startup and health endpoints. Avoid tests that merely duplicate placeholder text or configuration.

Docker Compose binds host ports to loopback. Check occupied ports before starting services, and do not stop or change unrelated projects.
