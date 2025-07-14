import os
import asyncio
import asyncpg
import logging
from urllib.parse import urlparse, urlunparse

def setup_logging():
    """Configures detailed logging to the console."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)-8s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def redact_password(url: str) -> str:
    """Replaces the password in a database URL with '********' for safe logging."""
    if not url:
        return "URL is empty or None"
    try:
        parsed = urlparse(url)
        # Rebuild the netloc part without the password if it exists
        netloc_parts = parsed.netloc.split('@')
        if len(netloc_parts) > 1:
            # Contains user/pass info
            host_info = netloc_parts[-1]
            user_info = netloc_parts[0].split(':')
            user = user_info[0]
            # Create a new netloc with a redacted password
            new_netloc = f"{user}:********@{host_info}"
        else:
            # No user/pass info
            new_netloc = parsed.netloc

        # Reconstruct the URL
        redacted_parts = parsed._replace(netloc=new_netloc)
        return urlunparse(redacted_parts)
    except Exception as e:
        return f"[Could not parse URL for redaction: {e}]"


async def read_table(conn, table_name, sql_query):
    """A generic function to read and log the contents of a table."""
    logging.info(f"--- Querying table: {table_name} ---")
    logging.info(f"Executing SQL: {sql_query}")
    try:
        # fetch() returns a list of Record objects
        rows = await conn.fetch(sql_query)
        
        if not rows:
            logging.warning(f"SUCCESS: Query executed, but the '{table_name}' table is empty.")
            return

        logging.info(f"SUCCESS: Found {len(rows)} row(s) in '{table_name}':")
        # Log each row
        for i, row in enumerate(rows):
            # A Record object can be treated like a dictionary
            row_dict = dict(row)
            logging.info(f"  Row {i+1}: {row_dict}")

    except asyncpg.exceptions.UndefinedTableError:
        logging.critical(
            f"FATAL ERROR: The database connection was successful, but the table '{table_name}' does not exist. "
            f"This confirms the issue is with the database schema (table missing) or permissions (table not visible to user)."
        )
    except Exception as e:
        logging.error(f"An unexpected error occurred while querying '{table_name}': {e}", exc_info=True)


async def main():
    """Main diagnostic function."""
    setup_logging()
    logging.info("Starting database diagnostic reader.")

    logging.info("Attempting to read DATABASE_URL from environment variables.")
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        logging.critical("FATAL ERROR: The 'DATABASE_URL' environment variable was not found. The script cannot continue.")
        return

    logging.info(f"Found DATABASE_URL. Connecting to: {redact_password(db_url)}")
    
    conn = None
    try:
        # Establish a connection to the database
        conn = await asyncpg.connect(dsn=db_url)
        logging.info("--> Database connection successful! <--")

        # Now, attempt to read the tables
        await read_table(conn, "nickname_configs", "SELECT * FROM nickname_configs;")
        await read_table(conn, "nickname_history", "SELECT * FROM nickname_history;")

    except asyncpg.exceptions.InvalidPasswordError:
         logging.critical("FATAL ERROR: Connection failed due to an invalid password. Please check your DATABASE_URL.")
    except ConnectionRefusedError:
         logging.critical("FATAL ERROR: Connection refused. Is the database server running at the specified IP/port? Is a firewall blocking the connection?")
    except Exception as e:
        # Catch any other connection errors
        logging.critical(f"A fatal error occurred during database connection: {e}", exc_info=True)
    
    finally:
        if conn:
            await conn.close()
            logging.info("Database connection has been closed.")
        logging.info("Diagnostic script finished.")


if __name__ == "__main__":
    asyncio.run(main())