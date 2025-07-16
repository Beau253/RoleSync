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
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)



@bot.event
async def on_ready():
    """Fires when the bot is ready."""
    logging.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    logging.info('------')
    logging.info("Startup nickname history sync has been disabled. Use /sync-nicknames to run manually.")
    
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logging.info(f"Failed to sync commands: {e}")

async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('__'):
            await bot.load_extension(f'cogs.{filename[:-3]}')
            logging.info(f"Loaded cog: {filename}")

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
    logging.info("Flask keep-alive server started in a background thread.")
    

    log_formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-15s: %(message)s')
    
    # File Handler
    file_handler = logging.FileHandler(filename='bot.log', encoding='utf-8', mode='w')
    file_handler.setFormatter(log_formatter)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
 
    # Initialize database and load cogs
    await db.init_db_pool()
    await load_cogs()

    # Start the bot. This will block until the bot is closed.
    try:
        await bot.start(BOT_TOKEN)
    finally:
        # This block will run when KeyboardInterrupt is received.
        logging.info("\nShutting down bot...")
        if not bot.is_closed():
            await bot.close()
        
        logging.info("Closing database pool...")
        if db.db_pool:
            await db.db_pool.close()
        
        logging.info("Shutdown complete.")

if __name__ == "__main__":
    # === THE NEW LOGGING SETUP (SIMPLE & EFFECTIVE) ===
    log_formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-20s: %(message)s')
    
    # File Handler
    file_handler = logging.FileHandler(filename='bot.log', encoding='utf-8', mode='w')
    file_handler.setFormatter(log_formatter)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)

    # Configure the root logger
    logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
    # === END OF LOGGING SETUP ===

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot shutdown initiated by user.")