import discord
from discord import app_commands
from discord.ext import commands
import math, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

def xp_for_level(level: int) -> int:
    """XP nécessaire pour passer au niveau suivant."""
    return int(100 * (level ** 1.5))

def xp_to_level(xp: int) -> int:
    level = 1
    while xp >= xp_for_level(level):
        xp -= xp_for_level(level)
        level += 1
    return level

XP_PER_MSG = 5
XP_COOLDOWN = 60  # secondes entre deux gains d'XP

_xp_cooldown: dict[int, float] = {}

class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /level ────────────────────────────────────────────────────────────────

    @app_commands.command(name="level", description="Affiche ton niveau ou celui d'un membre")
    async def level_cmd(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        u = db.get_user(t.id)
        xp    = u.get("xp", 0)
        level = u.get("level", 1)
        needed = xp_for_level(level)
        current_xp = xp % needed if needed else 0
        pct   = int((current_xp / needed) * 20) if needed else 20
        bar   = "█" * pct + "░" * (20 - pct)

        e = E.base(f"⭐ Niveau — {t.display_name}")
        e.set_thumbnail(url=t.display_avatar.url)
        e.add_field(name="🏆 Niveau",    value=f"`{level}`")
        e.add_field(name="✨ XP total",  value=f"`{xp}`")
        e.add_field(name="📈 Progrès",   value=f"`{current_xp}/{needed}` XP\n`[{bar}]`", inline=False)
        await i.response.send_message(embed=e)

    # ── /rank ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="rank", description="Classement XP du serveur")
    async def rank_cmd(self, i: discord.Interaction):
        top = db.get_leaderboard_xp(10)
        medals = ["🥇","🥈","🥉"]
        lines = []
        for idx, (uid, data) in enumerate(top):
            try:
                u = await self.bot.fetch_user(int(uid))
                name = u.display_name
            except:
                name = f"User#{uid[:4]}"
            medal = medals[idx] if idx < 3 else f"`{idx+1}.`"
            lines.append(f"{medal} **{name}** — Niveau `{data.get('level',1)}` · {data.get('xp',0)} XP")
        await i.response.send_message(embed=E.base("🏆 Classement XP", "\n".join(lines) or "Aucune donnée.", discord.Color.gold()))

    # ── /profile ──────────────────────────────────────────────────────────────

    @app_commands.command(name="profile", description="Voir le profil d'un membre")
    async def profile_cmd(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        u = db.get_user(t.id)
        roles = [r.mention for r in t.roles if r.name != "@everyone"]

        e = E.base(f"👤 Profil — {t.display_name}")
        e.set_thumbnail(url=t.display_avatar.url)
        if u.get("bio"):
            e.description = f"*{u['bio']}*"
        e.add_field(name="🏆 Niveau",    value=f"`{u.get('level', 1)}`")
        e.add_field(name="✨ XP",        value=f"`{u.get('xp', 0)}`")
        e.add_field(name="💰 Coins",     value=f"`{u.get('coins', 0)}` 🪙")
        e.add_field(name="💬 Messages",  value=f"`{u.get('total_msgs', 0)}`")
        e.add_field(name="📅 A rejoint", value=f"<t:{int(t.joined_at.timestamp())}:R>")
        e.add_field(name="🎭 Rôle top",  value=t.top_role.mention)
        await i.response.send_message(embed=e)

    # ── /bio ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="bio", description="Définit ta bio de profil")
    @app_commands.describe(text="Ta bio (max 200 caractères)")
    async def bio_cmd(self, i: discord.Interaction, text: str):
        if len(text) > 200:
            await i.response.send_message(embed=E.error("Bio trop longue (max 200 caractères)."), ephemeral=True); return
        u = db.get_user(i.user.id)
        u["bio"] = text
        db.save_user(i.user.id, u)
        await i.response.send_message(embed=E.success(f"Bio mise à jour :\n*{text}*"))

    # ── XP par message ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return

        import time
        now = time.time()
        last = _xp_cooldown.get(message.author.id, 0)
        if now - last < XP_COOLDOWN: return
        _xp_cooldown[message.author.id] = now

        u = db.get_user(message.author.id)
        u["xp"] = u.get("xp", 0) + XP_PER_MSG
        u["total_msgs"] = u.get("total_msgs", 0) + 1

        old_level = u.get("level", 1)
        new_level = xp_to_level(u["xp"])
        u["level"] = new_level
        db.save_user(message.author.id, u)

        # Notif level up
        if new_level > old_level:
            e = E.base("🎉 Level Up !",
                f"{message.author.mention} est passé au niveau **{new_level}** !\n"
                f"XP total : **{u['xp']}**",
                discord.Color.gold())
            await message.channel.send(embed=e, delete_after=10)


async def setup(bot):
    await bot.add_cog(Levels(bot))
