# main.py 
import os
import asyncio
import discord
import database as db
import logging
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread # Import the Thread class

# --- Initial Setup ---
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN or not DATABASE_URL:
    raise ValueError("BOT_TOKEN and DATABASE_URL must be set in environment variables.")

# --- Flask App Definition ---
app = Flask(__name__)

# --- Bot Definition ---
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Bot Events ---

logger = logging.getLogger('discord')


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
        logger.info(f"Failed to sync commands: {e}")

async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('__'):
            await bot.load_extension(f'cogs.{filename[:-3]}')
            logger.info(f"Loaded cog: {filename}")

# --- Health Check Endpoint ---
@app.route('/health')
def health_check():
    return "OK", 200

# --- Function to run the Flask app ---
def run_flask_app():
    """Runs the Flask app in a separate thread."""
    port = int(os.environ.get("PORT", 8080)) # Render uses PORT env var
    app.run(host='0.0.0.0', port=port)

# --- Main Application Runner ---
async def main():
    """Main function to start both the bot and the web server."""
    # Start the Flask app in a daemon thread.
    # Daemon threads exit when the main program exits.
    flask_thread = Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    logger.info("Flask keep-alive server started in a background thread.")
    
    # Initialize database and load cogs
    await db.init_db_pool()
    await load_cogs()

    # Start the bot. This will block until the bot is closed.
    try:
        await bot.start(BOT_TOKEN, log_handler=None)
    finally:
        # This block will run when KeyboardInterrupt is received.
        logger.info("\nShutting down bot...")
        if not bot.is_closed():
            await bot.close()
        
        logger.info("Closing database pool...")
        if db.db_pool:
            await db.db_pool.close()
        
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown initiated by user.")