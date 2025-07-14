# file: database.py
import os
import asyncpg
from typing import List, Dict, Optional

# The database connection pool will be initialized later.
db_pool = None

async def init_db_pool():
    """
    Initializes the database connection pool and ensures necessary tables exist.
    This function should be called once when the bot starts up.
    """
    global db_pool
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in environment variables.")
    
    try:
        db_pool = await asyncpg.create_pool(dsn=DATABASE_URL)
        print("Database connection pool initialized.")

        # Acquire a connection to create tables if they don't exist
        async with db_pool.acquire() as conn:
            # Create the nickname_configs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS nickname_configs (
                    guild_id BIGINT NOT NULL,
                    role_id BIGINT NOT NULL,
                    nickname_format TEXT NOT NULL,
                    PRIMARY KEY (guild_id, role_id)
                );
            """)

            # Create the nickname_history table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS nickname_history (
                    user_id BIGINT NOT NULL,
                    guild_id BIGINT NOT NULL,
                    role_id BIGINT NOT NULL,
                    previous_nickname TEXT,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    PRIMARY KEY (user_id, guild_id, role_id)
                );
            """)
        
        print("Database tables verified/created successfully.")

    except Exception as e:
        print(f"Error during database initialization: {e}")
        # Depending on your needs, you might want to exit the application if the DB can't be set up.
        # import sys
        # sys.exit("Could not initialize database. Exiting.")

# --- Database Interface Functions ---

async def set_rule(guild_id: int, role_id: int, nickname_format: str) -> None:
    """Adds a new rule or updates an existing one using asyncpg."""
    # Note: asyncpg uses $1, $2, etc. for parameters instead of %s
    sql = """
        INSERT INTO nickname_configs (guild_id, role_id, nickname_format)
        VALUES ($1, $2, $3)
        ON CONFLICT (guild_id, role_id)
        DO UPDATE SET nickname_format = $3;
    """
    async with db_pool.acquire() as conn:
        await conn.execute(sql, str(guild_id), str(role_id), nickname_format)

async def remove_rule(guild_id: int, role_id: int) -> bool:
    """Removes a nickname rule using asyncpg."""
    sql = "DELETE FROM nickname_configs WHERE guild_id = $1 AND role_id = $2;"
    async with db_pool.acquire() as conn:
        # execute() returns a status string like 'DELETE 1'
        status = await conn.execute(sql, str(guild_id), str(role_id))
        return 'DELETE 1' in status

async def get_rule(guild_id: int, role_id: int) -> Optional[asyncpg.Record]:
    """Retrieves a single nickname rule using asyncpg."""
    sql = "SELECT nickname_format FROM nickname_configs WHERE guild_id = $1 AND role_id = $2;"
    async with db_pool.acquire() as conn:
        # fetchrow returns a single Record or None
        return await conn.fetchrow(sql, str(guild_id), str(role_id))

async def get_all_rules(guild_id: int) -> List[asyncpg.Record]:
    """Retrieves all nickname rules for a guild using asyncpg."""
    sql = "SELECT role_id, nickname_format FROM nickname_configs WHERE guild_id = $1;"
    async with db_pool.acquire() as conn:
        # fetch returns a list of Records
        return await conn.fetch(sql, str(guild_id))

async def save_nickname_history(user_id: int, guild_id: int, role_id: int, previous_nickname: Optional[str]) -> None:
    """Saves or updates the user's previous nickname."""
    sql = """
        INSERT INTO nickname_history (user_id, guild_id, role_id, previous_nickname)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, guild_id, role_id)
        DO UPDATE SET previous_nickname = $4, timestamp = NOW();
    """
    async with db_pool.acquire() as conn:
        await conn.execute(sql, str(user_id), str(guild_id), str(role_id), previous_nickname)

async def get_nickname_history(user_id: int, guild_id: int, role_id: int) -> Optional[asyncpg.Record]:
    """Retrieves a user's saved nickname for a specific role event."""
    sql = "SELECT previous_nickname FROM nickname_history WHERE user_id = $1 AND guild_id = $2 AND role_id = $3;"
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(sql, str(user_id), str(guild_id), str(role_id))

async def delete_nickname_history(user_id: int, guild_id: int, role_id: int) -> None:
    """Deletes a history record after it has been used."""
    sql = "DELETE FROM nickname_history WHERE user_id = $1 AND guild_id = $2 AND role_id = $3;"
    async with db_pool.acquire() as conn:
        await conn.execute(sql, str(user_id), str(guild_id), str(role_id))