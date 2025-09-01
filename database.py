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

            # Create the delegated_role_permissions table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS delegated_role_permissions (
                    guild_id BIGINT NOT NULL,
                    manager_role_id BIGINT NOT NULL,
                    managed_role_id BIGINT NOT NULL,
                    PRIMARY KEY (guild_id, manager_role_id, managed_role_id)
                );
            """)

            # Create the role_exclusivity_groups table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS role_exclusivity_groups (
                    guild_id BIGINT NOT NULL,
                    group_name TEXT NOT NULL,
                    role_id BIGINT NOT NULL,
                    PRIMARY KEY (guild_id, role_id),
                    UNIQUE (guild_id, group_name, role_id)
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
        await conn.execute(sql, guild_id, role_id, nickname_format)

async def remove_rule(guild_id: int, role_id: int) -> bool:
    """Removes a nickname rule using asyncpg."""
    sql = "DELETE FROM nickname_configs WHERE guild_id = $1 AND role_id = $2;"
    async with db_pool.acquire() as conn:
        # execute() returns a status string like 'DELETE 1'
        status = await conn.execute(sql, guild_id, role_id)
        return 'DELETE 1' in status

async def get_rule(guild_id: int, role_id: int) -> Optional[asyncpg.Record]:
    """Retrieves a single nickname rule using asyncpg."""
    sql = "SELECT nickname_format FROM nickname_configs WHERE guild_id = $1 AND role_id = $2;"
    async with db_pool.acquire() as conn:
        # fetchrow returns a single Record or None
        return await conn.fetchrow(sql, guild_id, role_id)

async def get_all_rules(guild_id: int) -> List[asyncpg.Record]:
    """Retrieves all nickname rules for a guild using asyncpg."""
    sql = "SELECT role_id, nickname_format FROM nickname_configs WHERE guild_id = $1;"
    async with db_pool.acquire() as conn:
        # fetch returns a list of Records
        return await conn.fetch(sql, guild_id)

async def save_nickname_history(user_id: int, guild_id: int, role_id: int, previous_nickname: Optional[str]) -> None:
    """Saves or updates the user's previous nickname."""
    sql = """
        INSERT INTO nickname_history (user_id, guild_id, role_id, previous_nickname)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, guild_id, role_id)
        DO UPDATE SET previous_nickname = $4, timestamp = NOW();
    """
    async with db_pool.acquire() as conn:
        await conn.execute(sql, user_id, guild_id, role_id, previous_nickname)

async def get_nickname_history(user_id: int, guild_id: int, role_id: int) -> Optional[asyncpg.Record]:
    """Retrieves a user's saved nickname for a specific role event."""
    sql = "SELECT previous_nickname FROM nickname_history WHERE user_id = $1 AND guild_id = $2 AND role_id = $3;"
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(sql, user_id, guild_id, role_id)

async def delete_nickname_history(user_id: int, guild_id: int, role_id: int) -> None:
    """Deletes a history record after it has been used."""
    sql = "DELETE FROM nickname_history WHERE user_id = $1 AND guild_id = $2 AND role_id = $3;"
    async with db_pool.acquire() as conn:
        await conn.execute(sql, user_id, guild_id, role_id)

# --- Delegated Permissions Functions ---

async def add_delegated_permission(guild_id: int, manager_role_id: int, managed_role_id: int) -> None:
    """Adds a new delegated permission rule."""
    sql = "INSERT INTO delegated_role_permissions (guild_id, manager_role_id, managed_role_id) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING;"
    async with db_pool.acquire() as conn:
        await conn.execute(sql, guild_id, manager_role_id, managed_role_id)

async def remove_delegated_permission(guild_id: int, manager_role_id: int, managed_role_id: int) -> None:
    """Removes a delegated permission rule."""
    sql = "DELETE FROM delegated_role_permissions WHERE guild_id = $1 AND manager_role_id = $2 AND managed_role_id = $3;"
    async with db_pool.acquire() as conn:
        await conn.execute(sql, guild_id, manager_role_id, managed_role_id)

async def get_all_delegated_permissions(guild_id: int) -> List[asyncpg.Record]:
    """Gets all delegated permissions for a guild."""
    sql = "SELECT manager_role_id, managed_role_id FROM delegated_role_permissions WHERE guild_id = $1;"
    async with db_pool.acquire() as conn:
        return await conn.fetch(sql, guild_id)

async def get_manageable_roles_for_user(guild_id: int, user_role_ids: List[int]) -> List[int]:
    """Fetches a list of role IDs that a user is allowed to manage based on the roles they have."""
    if not user_role_ids:
        return []
    placeholders = ', '.join([f'${i+2}' for i in range(len(user_role_ids))])
    sql = f"SELECT DISTINCT managed_role_id FROM delegated_role_permissions WHERE guild_id = $1 AND manager_role_id IN ({placeholders});"
    async with db_pool.acquire() as conn:
        records = await conn.fetch(sql, guild_id, *user_role_ids)
        return [record['managed_role_id'] for record in records]

# --- Role Exclusivity Group Functions ---

async def add_role_to_exclusive_group(guild_id: int, group_name: str, role_id: int) -> None:
    """Adds a role to a mutual exclusivity group."""
    sql = "INSERT INTO role_exclusivity_groups (guild_id, group_name, role_id) VALUES ($1, $2, $3) ON CONFLICT (guild_id, role_id) DO UPDATE SET group_name = $2;"
    async with db_pool.acquire() as conn:
        await conn.execute(sql, guild_id, group_name.lower(), role_id)

async def remove_role_from_exclusive_group(guild_id: int, role_id: int) -> None:
    """Removes a role from any mutual exclusivity group."""
    sql = "DELETE FROM role_exclusivity_groups WHERE guild_id = $1 AND role_id = $2;"
    async with db_pool.acquire() as conn:
        await conn.execute(sql, guild_id, role_id)

async def get_all_exclusive_groups(guild_id: int) -> List[asyncpg.Record]:
    """Gets all roles organized by their exclusivity group for a guild."""
    sql = "SELECT group_name, role_id FROM role_exclusivity_groups WHERE guild_id = $1 ORDER BY group_name;"
    async with db_pool.acquire() as conn:
        return await conn.fetch(sql, guild_id)

async def get_conflicting_role(guild_id: int, user_roles: List[discord.Role], new_role_id: int) -> Optional[discord.Role]:
    """
    Checks if a user has a role that is in the same exclusivity group as the new role.
    Returns the conflicting role object if found, otherwise None.
    """
    user_role_ids = {role.id for role in user_roles}
    sql = """
        SELECT role_id FROM role_exclusivity_groups
        WHERE guild_id = $1 AND group_name = (
            SELECT group_name FROM role_exclusivity_groups WHERE guild_id = $1 AND role_id = $2
        )
    """
    async with db_pool.acquire() as conn:
        records = await conn.fetch(sql, guild_id, new_role_id)
        if not records:
            return None # The new role isn't in an exclusive group
        
        exclusive_role_ids = {record['role_id'] for record in records}
        
        # Find the intersection of roles the user has and roles in the exclusive group
        conflicting_ids = user_role_ids.intersection(exclusive_role_ids)
        
        if conflicting_ids:
            # Find the first conflicting role object from the user's roles
            conflicting_id = conflicting_ids.pop()
            for role in user_roles:
                if role.id == conflicting_id:
                    return role
    return None