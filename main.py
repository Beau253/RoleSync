# main.py 
import os
import asyncio
import discord
import logging  # NEW: Import the logging module
import database as db
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from waitress import serve  # NEW: Import Waitress for production

# --- 1. Centralized Logging Setup ---
# This is the most important change. We set up logging right at the start.
# This will capture output from all modules and is more reliable than print().
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Get a logger for this specific file
logger = logging.getLogger(__name__)

# --- Initial Setup ---
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN or not DATABASE_URL:
    # Use the logger to report critical errors
    logger.critical("BOT_TOKEN and DATABASE_URL must be set in environment variables.")
    raise ValueError("BOT_TOKEN and DATABASE_URL must be set in environment variables.")

# --- Flask App Definition ---
app = Flask(__name__)

# --- Bot Definition ---
intents = discord.Intents.default()
intents.members = True

# --- MODIFIED: Pass the database pool to the bot ---
# We will create the pool first and then pass it to our Bot class.
# This is a cleaner pattern called Dependency Injection.
class RoleSyncBot(commands.Bot):
    def __init__(self, *args, db_pool, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_pool = db_pool
        logger.info("Bot class initialized with database pool.")

bot = RoleSyncBot(command_prefix="!", intents=intents, db_pool=None) # Pool will be added later

# --- Bot Events ---
@bot.event
async def on_ready():
    """Fires when the bot is ready."""
    logger.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    logger.info('------')
    logger.info("Startup nickname history sync has been disabled. Use /sync-nicknames to run manually.")
    
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}", exc_info=True)

async def load_cogs(bot_instance):
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('__'):
            try:
                await bot_instance.load_extension(f'cogs.{filename[:-3]}')
                logger.info(f"Loaded cog: {filename}")
            except Exception as e:
                logger.error(f"Failed to load cog {filename}: {e}", exc_info=True)

# --- Health Check Endpoint ---
@app.route('/health')
def health_check():
    return "OK", 200

# --- Function to run the Flask app ---
def run_flask_app():
    """Runs the Flask app using a production-grade server."""
    port = int(os.environ.get("API_SERVER_PORT", 8080))
    logger.info(f"Starting Flask server on port {port} using Waitress.")
    # MODIFIED: Use Waitress instead of Flask's dev server
    serve(app, host='0.0.0.0', port=port)

# --- Main Application Runner ---
async def main():
    """Main function to start both the bot and the web server."""
    logger.info("Starting Alfred application...")
    
    # Start the Flask app in a daemon thread.
    flask_thread = Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    
    # --- MODIFIED: More explicit database and bot startup ---
    try:
        # 1. Initialize the database pool first.
        #    If this fails, the bot will not even try to start.
        logger.info("Initializing database pool...")
        bot.db_pool = await db.init_db_pool() # Inject the pool into our bot instance
        logger.info("Database pool successfully initialized.")
        
        # 2. Load cogs after DB is ready.
        await load_cogs(bot)
        
        # 3. Start the bot.
        await bot.start(BOT_TOKEN)

    except Exception as e:
        # This will catch ANY error during startup, including DB connection errors.
        logger.critical(f"A critical error occurred during startup: {e}", exc_info=True)
    finally:
        logger.info("Shutdown sequence initiated.")
        if not bot.is_closed():
            await bot.close()
        
        if hasattr(bot, 'db_pool') and bot.db_pool:
            await bot.db_pool.close()
            logger.info("Database pool closed.")
        
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application shutdown initiated by user (Ctrl+C).")