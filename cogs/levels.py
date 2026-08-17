import discord
from discord import app_commands
from discord.ext import commands, tasks
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db
from utils.rankcard import generate_rank_card

def xp_for_level(level: int) -> int:
    return int(100 * (level ** 1.5))

def total_xp_for_level(level: int) -> int:
    total = 0
    for lvl in range(1, level):
        total += xp_for_level(lvl)
    return total

def xp_to_level(xp: int) -> int:
    level = 1
    remaining = xp
    while remaining >= xp_for_level(level):
        remaining -= xp_for_level(level)
        level += 1
    return level

def progress_in_level(xp: int, level: int) -> tuple[int, int]:
    needed = xp_for_level(level)
    base = total_xp_for_level(level)
    current = max(0, xp - base)
    return current, needed

XP_PER_MSG = 5
XP_COOLDOWN = 60
XP_PER_VOICE_MIN = 2
VOICE_CHECK_INTERVAL = 60
LEVEL_REWARD_COINS = 50
PREMIUM_XP_MULT = 1.20  # +20%

_xp_cooldown: dict[int, float] = {}
_voice_joined: dict[int, float] = {}


class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_xp_loop.start()

    def cog_unload(self):
        self.voice_xp_loop.cancel()

    def _get_rank(self, user_id: int) -> int:
        top = db.get_leaderboard_xp(1000)
        for idx, (uid, _) in enumerate(top, start=1):
            if str(uid) == str(user_id):
                return idx
        return 0

    async def _handle_level_up(self, member: discord.Member, old_level: int, new_level: int, channel: discord.abc.Messageable = None):
        u = db.get_user(member.id)
        reward = LEVEL_REWARD_COINS * new_level
        u["coins"] = u.get("coins", 0) + reward
        db.save_user(member.id, u)

        cfg = db.get_guild(member.guild.id)
        level_roles = cfg.get("level_roles", {})
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

        desc = f"{member.mention} est passé au niveau **{new_level}** !\n🎁 Récompense : **+{reward} coins** 🪙"
        if role_given:
            desc += f"\n🎭 Rôle obtenu : {role_given.mention}"

        e = E.base("🎉 Level Up !", desc, discord.Color.gold())
        if channel:
            try:
                await channel.send(embed=e, delete_after=15)
            except Exception:
                pass
        else:
            log_ch = member.guild.get_channel(cfg.get("log_channel") or 0)
            if log_ch:
                try:
                    await log_ch.send(embed=e)
                except Exception:
                    pass

    @app_commands.command(name="level", description="Affiche ta rank card (ou celle d'un membre)")
    async def level_cmd(self, i: discord.Interaction, member: discord.Member = None):
        await i.response.defer()
        t = member or i.user
        u = db.get_user(t.id)
        xp = u.get("xp", 0)
        level = u.get("level", 1)
        current, needed = progress_in_level(xp, level)
        rank = self._get_rank(t.id)

        try:
            buffer = await generate_rank_card(
                username=t.display_name,
                avatar_url=t.display_avatar.replace(size=256, format="png").url,
                level=level,
                xp=xp,
                current_xp=current,
                needed_xp=needed,
                rank=rank,
                total_msgs=u.get("total_msgs", 0),
            )
            file = discord.File(fp=buffer, filename=f"rank-{t.id}.png")
            await i.followup.send(file=file)
        except Exception as ex:
            pct = int((current / needed) * 20) if needed else 20
            bar = "█" * pct + "░" * (20 - pct)
            e = E.base(f"⭐ Niveau — {t.display_name}")
            e.set_thumbnail(url=t.display_avatar.url)
            e.add_field(name="🏆 Niveau", value=f"`{level}`")
            e.add_field(name="✨ XP total", value=f"`{xp}`")
            e.add_field(name="📈 Progrès", value=f"`{current}/{needed}` XP\n`[{bar}]`", inline=False)
            e.set_footer(text=f"Erreur rank card : {ex}")
            await i.followup.send(embed=e)

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
            star = " ⭐" if data.get("premium") else ""
            lines.append(f"{medal} **{name}**{star} — Niveau `{data.get('level',1)}` · `{data.get('xp',0)}` XP")
        await i.response.send_message(
            embed=E.base("🏆 Classement XP", "\n".join(lines) or "Aucune donnée.", discord.Color.gold())
        )

    @app_commands.command(name="profile", description="Voir le profil d'un membre")
    async def profile_cmd(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        u = db.get_user(t.id)
        e = E.base(f"👤 Profil — {t.display_name}")
        e.set_thumbnail(url=t.display_avatar.url)
        if u.get("bio"):
            e.description = f"*{u['bio']}*"
        e.add_field(name="🏆 Niveau", value=f"`{u.get('level', 1)}`")
        e.add_field(name="✨ XP", value=f"`{u.get('xp', 0)}`")
        e.add_field(name="💰 Coins", value=f"`{u.get('coins', 0)}` 🪙")
        e.add_field(name="💬 Messages", value=f"`{u.get('total_msgs', 0)}`")
        e.add_field(name="📅 A rejoint", value=f"<t:{int(t.joined_at.timestamp())}:R>")
        e.add_field(name="🎭 Rôle top", value=t.top_role.mention)
        if db.is_premium(t.id):
            e.set_footer(text="⭐ Premium")
        await i.response.send_message(embed=e)

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

    @app_commands.command(name="setlevelrole", description="[Admin] Associe un rôle à un niveau")
    @app_commands.describe(level="Le niveau", role="Le rôle à donner")
    @app_commands.default_permissions(administrator=True)
    async def setlevelrole(self, i: discord.Interaction, level: app_commands.Range[int, 1, 100], role: discord.Role):
        cfg = db.get_guild(i.guild.id)
        level_roles = cfg.get("level_roles", {})
        level_roles[str(level)] = role.id
        cfg["level_roles"] = level_roles
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Au niveau **{level}**, le rôle {role.mention} sera donné automatiquement."))

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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        now = time.time()
        last = _xp_cooldown.get(message.author.id, 0)
        if now - last < XP_COOLDOWN:
            return
        _xp_cooldown[message.author.id] = now

        xp_gain = XP_PER_MSG
        if db.is_premium(message.author.id):
            xp_gain = int(XP_PER_MSG * PREMIUM_XP_MULT)

        u = db.get_user(message.author.id)
        u["xp"] = u.get("xp", 0) + xp_gain
        u["total_msgs"] = u.get("total_msgs", 0) + 1

        old_level = u.get("level", 1)
        new_level = xp_to_level(u["xp"])
        u["level"] = new_level
        db.save_user(message.author.id, u)

        if new_level > old_level:
            await self._handle_level_up(message.author, old_level, new_level, message.channel)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        if before.channel is None and after.channel is not None:
            _voice_joined[member.id] = time.time()
        elif before.channel is not None and after.channel is None:
            join_time = _voice_joined.pop(member.id, None)
            if join_time:
                minutes = (time.time() - join_time) / 60
                if minutes >= 1:
                    await self._give_voice_xp(member, minutes)
        elif before.channel is not None and after.channel is not None:
            if member.id not in _voice_joined:
                _voice_joined[member.id] = time.time()

    async def _give_voice_xp(self, member: discord.Member, minutes: float):
        xp_gain = int(minutes * XP_PER_VOICE_MIN)
        if db.is_premium(member.id):
            xp_gain = int(xp_gain * PREMIUM_XP_MULT)
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
                    elapsed = now - _voice_joined[member.id]
                    if elapsed >= 55:
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
