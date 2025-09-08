import os
from sqlalchemy import (MetaData, Table, Column, Integer, String, Text, DateTime, Boolean, Index, func)
from sqlalchemy.ext.asyncio import create_async_engine
from databases import Database
#from sqlalchemy.sql import text

DB_PATH = os.getenv("DATABASE_PATH")
if not DB_PATH:
    # default to ./pastes/pastes.db
    DB_PATH = os.path.abspath(os.path.join(os.getcwd(), "pastes", "pastes.db"))
# ensure folder exists before any DB IO
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DB_URL = os.getenv("DB_URL", f"sqlite+aiosqlite:///{DB_PATH}")

metadata = MetaData()

pastes = Table(
    "pastes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
    Column("deleted_at", DateTime, nullable=True),
    Column("title", String(4), unique=True, index=True),
    Column("content", Text),
    Column("visibility", String),
    Column("expiration", DateTime, index=True, nullable=True),
    Column("is_encrypted", Boolean),
    Column("user_id", Integer),
    Column("is_user_paste", Boolean),
    Index("vis_enc", "visibility", "is_encrypted"),
    Index("user_paste", "user_id", "is_user_paste"),
)

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("created_at", DateTime, server_default=func.now()),
    Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
    Column("deleted_at", DateTime, nullable=True),
    Column("username", String, unique=True, index=True),
    Column("password", String),
)

# Use 'databases' for async query execution
database = Database(DB_URL)


#async def create_index_if_not_exists(conn, index_name, table, *columns):
    # Check if index exists in SQLite
#    result = await conn.execute(
#        text(f"SELECT name FROM sqlite_master WHERE type='index' AND name=:name"),
#        {"name": index_name}
#    )
#    row = result.fetchone()
#    if not row:
#        await conn.run_sync(lambda c: Index(index_name, *columns).create(c))

async def init_db():
    """Create tables using SQLAlchemy async engine. Call this at application startup."""
    async_engine = create_async_engine(DB_URL, echo=False)
    async with async_engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        # Ensure indexes exist
#        await create_index_if_not_exists(conn, "vis_enc", pastes, pastes.c.visibility, pastes.c.is_encrypted)
#        await create_index_if_not_exists(conn, "user_paste", pastes, pastes.c.user_id, pastes.c.is_user_paste)
    await async_engine.dispose()
