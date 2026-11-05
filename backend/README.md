# Backend

FastAPI app with a SQLite database.

## Run

```sh
uv run scripts/generate_env.py    # creates .env with a random JWT_SECRET
uv run backend
```

The API runs on http://localhost:8000, with interactive docs at `/docs`. Tables are created on startup.

## Test

```sh
uv run pytest
```

## Layout

- `src/backend/routers/` - one module per API area, registered in `app.py`
- `src/backend/models.py` - database tables
- `src/backend/schemas.py` - request and response bodies
- `src/backend/dependencies.py` - shared dependencies: `DbSession`, `CurrentUser`
- `src/backend/errors.py` - error handlers, all errors use `{"status": ..., "detail": ...}`

To protect an endpoint, add a `user: CurrentUser` parameter.
