# API types

Karya's frontend does not hand-write API request/response types. They are
generated from the backend's actual OpenAPI schema, so the frontend cannot
quietly drift from what the backend really returns.

## The pipeline

```
backend/app/main.py (FastAPI app)
   │  app.openapi() — no server/DB required, pure schema introspection
   ▼
frontend/openapi/karya.openapi.json   (checked into the repo — see below)
   │  openapi-typescript
   ▼
frontend/src/types/api.generated.ts   (checked into the repo, never hand-edited)
   │  thin, readable aliases
   ▼
frontend/src/lib/api/types.ts          (LoginRequest, UserResponse, ... )
```

## Regenerating

**1. Regenerate the OpenAPI spec from the live backend source** (from
`backend/`, with its virtualenv active — this does not need PostgreSQL
running; building the FastAPI app object and calling `.openapi()` never
touches the database):

```bash
.venv/Scripts/python.exe -c "
import json
from app.main import app
with open('../frontend/openapi/karya.openapi.json', 'w', encoding='utf-8') as f:
    json.dump(app.openapi(), f, indent=2)
"
```

**2. Regenerate the TypeScript types** (from `frontend/`):

```bash
npm run generate:api-types
```

Both steps are deterministic — the same backend code produces byte-identical
output every time, which is what makes it safe to check the generated
`.openapi.json` and `.generated.ts` into git rather than regenerating them on
every install: a diff in either file is a real, reviewable signal that the
backend's contract changed.

## Why generated, not hand-written

The alternative — hand-maintaining a `UserResponse` interface next to the
backend's `UserResponse` Pydantic model — has one predictable failure mode:
the backend adds or renames a field, and the frontend's copy is wrong until
someone notices at runtime. Generating from the actual schema makes that
class of bug a compile-time error instead: rename a field on the backend,
regenerate, and every call site that referenced the old name fails
`tsc -b` immediately.

## What's *not* generated

`src/lib/api/types.ts` re-exports a curated subset with short names
(`LoginRequest` instead of `components['schemas']['LoginRequest']`), plus a
couple of small runtime helpers (`isUserRole`, `ASSIGNABLE_ROLES`) that exist
*because* the backend's `UserResponse.role` is typed as a plain `string`
rather than the `UserRole` enum (see `app/schemas/user.py` — a deliberate
backend choice, not an oversight) — those helpers are what let the frontend
narrow that string back to a real enum safely, and they're hand-written
because they encode a policy decision, not a schema fact.

## Secrets

Neither generated file has ever contained one and structurally cannot: an
OpenAPI schema describes shapes, not runtime values, and FastAPI's own
schema builder never embeds a `SecretStr`'s value, a `.env` value, or a
database credential into the document it produces.
