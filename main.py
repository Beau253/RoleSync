# main.py 
import os
import asyncio
import discord
import database as db
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from waitress import serve

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

@bot.event
async def on_ready():
    """Fires when the bot is ready."""
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')

    # The automatic startup sync has been removed to prevent rate-limiting on startup.
    # The sync should now only be triggered manually via the /sync-nicknames command.
    print("Startup nickname history sync has been disabled. Use /sync-nicknames to run manually.")
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('__'):
            await bot.load_extension(f'cogs.{filename[:-3]}')
            print(f"Loaded cog: {filename}")

# --- Health Check Endpoint ---
@app.route('/health')
def health_check():
    return "OK", 200

# --- Function to run the Flask app ---
def run_flask_app():
    port = int(os.getenv("API_SERVER_PORT", 8080))
    print(f"Starting production web server on port {port}...")
    serve(app, host='0.0.0.0', port=port)

# --- Main Application Runner ---
async def main():
    """Main function to start both the bot and the web server."""
    # Start the Flask app in a daemon thread.
    # Daemon threads exit when the main program exits.
    flask_thread = Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    print("Flask keep-alive server started in a background thread.")
    
    # Initialize database and load cogs
    await db.init_db_pool()
    await load_cogs()

    # Start the bot. This will block until the bot is closed.
    try:
        await bot.start(BOT_TOKEN)
    finally:
        # This block will run when KeyboardInterrupt is received.
        print("\nShutting down bot...")
        if not bot.is_closed():
            await bot.close()
        
        print("Closing database pool...")
        if db.db_pool:
            await db.db_pool.close()
        
        print("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot shutdown initiated by user.")