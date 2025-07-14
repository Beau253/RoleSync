# main.py 
import os
import asyncio
import discord
import database as db
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from waitress import serve  # <-- The only new import

# --- Initial Setup ---
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN or not DATABASE_URL:
    raise ValueError("BOT_TOKEN and DATABASE_URL must be set in environment variables.")

# ... (Flask App Definition and Bot Definition are unchanged) ...
app = Flask(__name__)
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ... (on_ready, load_cogs, and health_check are unchanged) ...
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')
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

@app.route('/health')
def health_check():
    return "OK", 200

# --- MODIFIED FUNCTION ---
def run_flask_app():
    """Runs the Flask app using a production server."""
    port = int(os.getenv("API_SERVER_PORT", 8080))
    print(f"Starting production web server on port {port}...")
    serve(app, host='0.0.0.0', port=port) # Use serve() instead of app.run()

# --- Main Application Runner ---
# ... (This section is unchanged) ...
async def main():
    flask_thread = Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    print("Flask keep-alive server started in a background thread.")
    
    await db.init_db_pool()
    await load_cogs()

    try:
        await bot.start(BOT_TOKEN)
    finally:
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