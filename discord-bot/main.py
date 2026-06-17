import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(__file__))

from src.bot import bot, TOKEN
from src.keep_alive import start_keep_alive

async def run():
    if not TOKEN:
        print("❌ DISCORD_BOT_TOKEN secret'ı ayarlanmamış! Replit Secrets'a ekleyin.")
        raise SystemExit(1)

    await start_keep_alive()
    await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
