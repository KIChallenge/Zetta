from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings

# FastAPI runs sync handlers and dependencies in a thread pool, so one session
# can be used from several threads.
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _overwrite_deleted(connection, _) -> None:
    # Deleted rows are zeroed in the file, so a deleted account's data cannot be read back from it.
    connection.execute("PRAGMA secure_delete = ON")


SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
