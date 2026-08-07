import discord
from discord import app_commands
from discord.ext import commands, tasks
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

# ─── Formules XP ──────────────────────────────────────────────────────────────

def xp_for_level(level: int) -> int:
    """XP nécessaire pour passer du niveau `level` au niveau suivant."""
    return int(100 * (level ** 1.5))

def total_xp_for_level(level: int) -> int:
    """XP total nécessaire pour atteindre exactement ce niveau."""
    total = 0
    for lvl in range(1, level):
        total += xp_for_level(lvl)
    return total

def xp_to_level(xp: int) -> int:
    """Calcule le niveau à partir de l'XP total."""
    level = 1
    remaining = xp
    while remaining >= xp_for_level(level):
        remaining -= xp_for_level(level)
        level += 1
    return level

def progress_in_level(xp: int, level: int) -> tuple[int, int]:
    """Retourne (xp actuel dans le niveau, xp nécessaire pour le suivant)."""
    needed = xp_for_level(level)
    base = total_xp_for_level(level)
    current = max(0, xp - base)
    return current, needed

# ─── Constantes ───────────────────────────────────────────────────────────────

XP_PER_MSG     = 5
XP_COOLDOWN    = 60          # secondes entre deux gains d'XP message
XP_PER_VOICE_MIN = 2         # XP gagné par minute en vocal
VOICE_CHECK_INTERVAL = 60    # vérifie toutes les 60 secondes

LEVEL_REWARD_COINS = 50      # coins de base par level up (multiplié par le niveau)

_xp_cooldown: dict[int, float] = {}
_voice_joined: dict[int, float] = {}   # user_id → timestamp d'entrée en vocal


class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_xp_loop.start()

    def cog_unload(self):
        self.voice_xp_loop.cancel()

    # ── Helper level-up ───────────────────────────────────────────────────────

    async def _handle_level_up(self, member: discord.Member, old_level: int, new_level: int, channel: discord.abc.Messageable = None):
        """Gère les récompenses et la notification de level up."""
        u = db.get_user(member.id)

        # Récompense en coins
        reward = LEVEL_REWARD_COINS * new_level
        u["coins"] = u.get("coins", 0) + reward
        db.save_user(member.id, u)

        # Rôle de récompense (si configuré dans le serveur)
        cfg = db.get_guild(member.guild.id)
        level_roles = cfg.get("level_roles", {})  # {"5": role_id, "10": role_id, ...}
        role_given = None
        for lvl_str, role_id in level_roles.items():
            try:
                if int(lvl_str) == new_level:
                    role = member.guild.get_role(int(role_id))
                    if role and role not in member.roles:
                        await member.add_roles(role, reason=f"Level {new_level} reward")
                        role_given = role
            except Exception:
                pass

        # Notification
        desc = (
            f"{member.mention} est passé au niveau **{new_level}** !\n"
            f"🎁 Récompense : **+{reward} coins** 🪙"
        )
        if role_given:
            desc += f"\n🎭 Rôle obtenu : {role_given.mention}"

        e = E.base("🎉 Level Up !", desc, discord.Color.gold())

        if channel:
            try:
                await channel.send(embed=e, delete_after=15)
            except Exception:
                pass
        else:
            # Essaye le salon de logs ou le premier salon texte
            log_ch = member.guild.get_channel(cfg.get("log_channel") or 0)
            if log_ch:
                try:
                    await log_ch.send(embed=e)
                except Exception:
                    pass

    # ── /level ────────────────────────────────────────────────────────────────

    @app_commands.command(name="level", description="Affiche ton niveau ou celui d'un membre")
    async def level_cmd(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        u = db.get_user(t.id)
        xp    = u.get("xp", 0)
        level = u.get("level", 1)

        current, needed = progress_in_level(xp, level)
        pct = int((current / needed) * 20) if needed else 20
        bar = "█" * pct + "░" * (20 - pct)

        e = E.base(f"⭐ Niveau — {t.display_name}")
        e.set_thumbnail(url=t.display_avatar.url)
        e.add_field(name="🏆 Niveau",   value=f"`{level}`")
        e.add_field(name="✨ XP total", value=f"`{xp}`")
        e.add_field(name="📈 Progrès",  value=f"`{current}/{needed}` XP\n`[{bar}] {int(current/needed*100) if needed else 100}%`", inline=False)
        await i.response.send_message(embed=e)

    # ── /rank ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="rank", description="Classement XP du serveur")
    async def rank_cmd(self, i: discord.Interaction):
        top = db.get_leaderboard_xp(10)
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for idx, (uid, data) in enumerate(top):
            try:
                u = await self.bot.fetch_user(int(uid))
                name = u.display_name
            except Exception:
                name = f"User#{str(uid)[:4]}"
            medal = medals[idx] if idx < 3 else f"`{idx+1}.`"
            lines.append(f"{medal} **{name}** — Niveau `{data.get('level',1)}` · `{data.get('xp',0)}` XP")
        await i.response.send_message(
            embed=E.base("🏆 Classement XP", "\n".join(lines) or "Aucune donnée.", discord.Color.gold())
        )

    # ── /profile ──────────────────────────────────────────────────────────────

    @app_commands.command(name="profile", description="Voir le profil d'un membre")
    async def profile_cmd(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        u = db.get_user(t.id)

        e = E.base(f"👤 Profil — {t.display_name}")
        e.set_thumbnail(url=t.display_avatar.url)
        if u.get("bio"):
            e.description = f"*{u['bio']}*"
        e.add_field(name="🏆 Niveau",   value=f"`{u.get('level', 1)}`")
        e.add_field(name="✨ XP",       value=f"`{u.get('xp', 0)}`")
        e.add_field(name="💰 Coins",    value=f"`{u.get('coins', 0)}` 🪙")
        e.add_field(name="💬 Messages", value=f"`{u.get('total_msgs', 0)}`")
        e.add_field(name="📅 A rejoint", value=f"<t:{int(t.joined_at.timestamp())}:R>")
        e.add_field(name="🎭 Rôle top", value=t.top_role.mention)
        await i.response.send_message(embed=e)

    # ── /bio ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="bio", description="Définit ta bio de profil")
    @app_commands.describe(text="Ta bio (max 200 caractères)")
    async def bio_cmd(self, i: discord.Interaction, text: str):
        if len(text) > 200:
            await i.response.send_message(embed=E.error("Bio trop longue (max 200 caractères)."), ephemeral=True)
            return
        u = db.get_user(i.user.id)
        u["bio"] = text
        db.save_user(i.user.id, u)
        await i.response.send_message(embed=E.success(f"Bio mise à jour :\n*{text}*"))

    # ── /setlevelrole (admin) ─────────────────────────────────────────────────

    @app_commands.command(name="setlevelrole", description="[Admin] Associe un rôle à un niveau")
    @app_commands.describe(level="Le niveau", role="Le rôle à donner")
    @app_commands.default_permissions(administrator=True)
    async def setlevelrole(self, i: discord.Interaction, level: app_commands.Range[int, 1, 100], role: discord.Role):
        cfg = db.get_guild(i.guild.id)
        level_roles = cfg.get("level_roles", {})
        level_roles[str(level)] = role.id
        cfg["level_roles"] = level_roles
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(
            embed=E.success(f"Au niveau **{level}**, le rôle {role.mention} sera donné automatiquement.")
        )

    @app_commands.command(name="removelevelrole", description="[Admin] Retire le rôle d'un niveau")
    @app_commands.default_permissions(administrator=True)
    async def removelevelrole(self, i: discord.Interaction, level: app_commands.Range[int, 1, 100]):
        cfg = db.get_guild(i.guild.id)
        level_roles = cfg.get("level_roles", {})
        if str(level) in level_roles:
            del level_roles[str(level)]
            cfg["level_roles"] = level_roles
            db.save_guild(i.guild.id, cfg)
            await i.response.send_message(embed=E.success(f"Rôle du niveau **{level}** retiré."))
        else:
            await i.response.send_message(embed=E.error(f"Aucun rôle configuré pour le niveau {level}."), ephemeral=True)

    # ── XP par message ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        now = time.time()
        last = _xp_cooldown.get(message.author.id, 0)
        if now - last < XP_COOLDOWN:
            return
        _xp_cooldown[message.author.id] = now

        u = db.get_user(message.author.id)
        u["xp"] = u.get("xp", 0) + XP_PER_MSG
        u["total_msgs"] = u.get("total_msgs", 0) + 1

        old_level = u.get("level", 1)
        new_level = xp_to_level(u["xp"])
        u["level"] = new_level
        db.save_user(message.author.id, u)

        if new_level > old_level:
            await self._handle_level_up(message.author, old_level, new_level, message.channel)

    # ── XP Vocal ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        # Entre dans un salon vocal
        if before.channel is None and after.channel is not None:
            _voice_joined[member.id] = time.time()

        # Quitte un salon vocal
        elif before.channel is not None and after.channel is None:
            join_time = _voice_joined.pop(member.id, None)
            if join_time:
                minutes = (time.time() - join_time) / 60
                if minutes >= 1:
                    await self._give_voice_xp(member, minutes)

        # Change de salon (on garde le timer)
        elif before.channel is not None and after.channel is not None:
            if member.id not in _voice_joined:
                _voice_joined[member.id] = time.time()

    async def _give_voice_xp(self, member: discord.Member, minutes: float):
        xp_gain = int(minutes * XP_PER_VOICE_MIN)
        if xp_gain <= 0:
            return

        u = db.get_user(member.id)
        u["xp"] = u.get("xp", 0) + xp_gain

        old_level = u.get("level", 1)
        new_level = xp_to_level(u["xp"])
        u["level"] = new_level
        db.save_user(member.id, u)

        if new_level > old_level:
            await self._handle_level_up(member, old_level, new_level)

    @tasks.loop(seconds=VOICE_CHECK_INTERVAL)
    async def voice_xp_loop(self):
        """Donne de l'XP périodiquement aux gens déjà en vocal (toutes les minutes)."""
        now = time.time()
        to_update = []

        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot:
                        continue
                    if member.id not in _voice_joined:
                        _voice_joined[member.id] = now
                        continue

                    # On donne l'XP pour la dernière minute et on reset le timer
                    elapsed = now - _voice_joined[member.id]
                    if elapsed >= 55:  # ~1 minute
                        minutes = elapsed / 60
                        to_update.append((member, minutes))
                        _voice_joined[member.id] = now

        for member, minutes in to_update:
            try:
                await self._give_voice_xp(member, minutes)
            except Exception:
                pass

    @voice_xp_loop.before_loop
    async def before_voice_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Levels(bot))
