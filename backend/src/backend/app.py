import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.config import settings
from backend.corpus import get_corpus
from backend.database import Base, engine
from backend.errors import register_exception_handlers
from backend.guards import BodyLimit, SecurityHeaders
from backend.routers import auth, chats, users


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(engine)
    if engine.url.get_backend_name() == "sqlite" and engine.url.database and os.path.exists(engine.url.database):
        os.chmod(engine.url.database, 0o600)  # it holds names, addresses and social security numbers
    get_corpus()  # a broken corpus fails at startup, not mid-chat
    yield


# No /docs or /openapi.json: they map the whole API for anyone who can reach the server.
app = FastAPI(title="Zetta", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(BodyLimit)
app.add_middleware(SecurityHeaders)
# Outermost: a page on another host name that resolves to this server (DNS rebinding) gets nothing.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chats.router)
