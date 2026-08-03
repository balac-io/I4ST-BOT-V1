import discord
from datetime import datetime

BRAND_COLOR  = discord.Color.from_str("#7289DA")
SUCCESS      = discord.Color.green()
ERROR        = discord.Color.red()
WARNING      = discord.Color.orange()
INFO         = discord.Color.blue()
GOLD         = discord.Color.gold()

BOT_ICON = None   # Sera défini au runtime par main.py

def base(title: str, desc: str = "", color: discord.Color = BRAND_COLOR) -> discord.Embed:
    e = discord.Embed(title=title, description=desc, color=color)
    e.timestamp = datetime.now()
    e.set_footer(text="Kryvoox", icon_url=BOT_ICON)
    return e

def success(desc: str, title: str = "✅ Succès") -> discord.Embed:
    return base(title, desc, SUCCESS)

def error(desc: str, title: str = "❌ Erreur") -> discord.Embed:
    return base(title, desc, ERROR)

def warn(desc: str, title: str = "⚠️ Avertissement") -> discord.Embed:
    return base(title, desc, WARNING)

def info(desc: str, title: str = "ℹ️ Info") -> discord.Embed:
    return base(title, desc, INFO)
