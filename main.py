"""
KRYVOOX — Bot SaaS
discord.py · Slash Commands · Groq
"""

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


class Kryvoox(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            application_id=int(os.getenv("APP_ID", "0"))
        )
        self.start_time = discord.utils.utcnow()

    async def setup_hook(self):
        cogs = [
            "cogs.info",
            "cogs.moderation",
            "cogs.economy",
            "cogs.tickets",
            "cogs.admin",
            "cogs.ai",
            "cogs.voice",
            "cogs.security",
            "cogs.utils",
            "cogs.stats",
            "cogs.levels",
            "cogs.premium",
            "cogs.giveaways",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"  ✅ {cog}")
            except Exception as e:
                print(f"  ❌ {cog} : {e}")

        synced = await self.tree.sync()
        print(f"\n🌐 {len(synced)} slash commands synchronisées")

    async def on_ready(self):
        print(f"\n{'='*45}")
        print(f"  KRYVOOX en ligne — {self.user}")
        print(f"  Serveurs : {len(self.guilds)}")
        print(f"{'='*45}\n")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"/help | {len(self.guilds)} serveurs"
            )
        )


bot = Kryvoox()

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN manquant dans .env")
    elif not GROQ_API_KEY:
        print("❌ GROQ_API_KEY manquant dans .env")
    else:
        bot.run(TOKEN)
