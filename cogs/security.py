import discord
from discord import app_commands
from discord.ext import commands
from collections import defaultdict
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

# Anti-nuke : tracker d'actions rapides (bans/kicks/channel_delete)
_action_tracker: dict[int, list] = defaultdict(list)
NUKE_THRESHOLD = 5   # actions
NUKE_WINDOW    = 10  # secondes

class Security(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # whitelist/blacklist en mémoire par guild
        self._whitelist: dict[int, set] = defaultdict(set)
        self._blacklist: dict[int, set] = defaultdict(set)

    def _track(self, guild_id: int, user_id: int) -> int:
        now = datetime.now()
        key = f"{guild_id}:{user_id}"
        _action_tracker[key] = [t for t in _action_tracker[key] if (now-t).total_seconds() < NUKE_WINDOW]
        _action_tracker[key].append(now)
        return len(_action_tracker[key])

    # ── /antinuke ─────────────────────────────────────────────────────────────

    @app_commands.command(name="antinuke", description="Active/désactive l'anti-nuke")
    @app_commands.default_permissions(administrator=True)
    async def antinuke(self, i: discord.Interaction, enabled: bool):
        cfg = db.get_guild(i.guild.id)
        cfg["antinuke"] = enabled
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(
            f"Anti-nuke {'✅ activé' if enabled else '❌ désactivé'}.\n"
            f"Seuil : **{NUKE_THRESHOLD} actions** en **{NUKE_WINDOW}s** → ban automatique."
        ))

    # ── /lockdown / /unlockdown ───────────────────────────────────────────────

    @app_commands.command(name="lockdown", description="Lockdown d'urgence du serveur")
    @app_commands.default_permissions(administrator=True)
    async def lockdown(self, i: discord.Interaction, reason: str = "Urgence sécurité"):
        await i.response.defer()
        locked = 0
        for ch in i.guild.text_channels:
            try:
                await ch.set_permissions(i.guild.default_role, send_messages=False, add_reactions=False)
                locked += 1
            except: pass
        e = E.base("🔒 LOCKDOWN ACTIVÉ", f"**{locked} salons** verrouillés.\nRaison : {reason}\nMod : {i.user.mention}", discord.Color.red())
        await i.followup.send(embed=e)
        cfg = db.get_guild(i.guild.id)
        if cfg.get("log_channel"):
            log_ch = i.guild.get_channel(cfg["log_channel"])
            if log_ch: await log_ch.send(embed=e)

    @app_commands.command(name="unlockdown", description="Retire le lockdown du serveur")
    @app_commands.default_permissions(administrator=True)
    async def unlockdown(self, i: discord.Interaction):
        await i.response.defer()
        unlocked = 0
        for ch in i.guild.text_channels:
            try:
                await ch.set_permissions(i.guild.default_role, send_messages=None, add_reactions=None)
                unlocked += 1
            except: pass
        await i.followup.send(embed=E.success(f"🔓 Lockdown levé. **{unlocked} salons** restaurés."))

    # ── /whitelist ────────────────────────────────────────────────────────────

    whitelist_group = app_commands.Group(name="whitelist", description="Gestion de la whitelist anti-nuke")

    @whitelist_group.command(name="add", description="Ajoute un membre à la whitelist")
    @app_commands.default_permissions(administrator=True)
    async def wl_add(self, i: discord.Interaction, member: discord.Member):
        self._whitelist[i.guild.id].add(member.id)
        await i.response.send_message(embed=E.success(f"{member.mention} ajouté à la whitelist anti-nuke."))

    @whitelist_group.command(name="remove", description="Retire un membre de la whitelist")
    @app_commands.default_permissions(administrator=True)
    async def wl_remove(self, i: discord.Interaction, member: discord.Member):
        self._whitelist[i.guild.id].discard(member.id)
        await i.response.send_message(embed=E.success(f"{member.mention} retiré de la whitelist."))

    @whitelist_group.command(name="list", description="Voir la whitelist")
    @app_commands.default_permissions(administrator=True)
    async def wl_list(self, i: discord.Interaction):
        wl = self._whitelist[i.guild.id]
        if not wl:
            await i.response.send_message(embed=E.info("Whitelist vide.")); return
        members = [f"<@{uid}>" for uid in wl]
        await i.response.send_message(embed=E.info("\n".join(members), "✅ Whitelist"))

    # ── /blacklist ────────────────────────────────────────────────────────────

    blacklist_group = app_commands.Group(name="blacklist", description="Gestion de la blacklist")

    @blacklist_group.command(name="add", description="Blacklist un utilisateur (ban auto si rejoint)")
    @app_commands.default_permissions(administrator=True)
    async def bl_add(self, i: discord.Interaction, user_id: str, reason: str = "Blacklisté"):
        self._blacklist[i.guild.id].add(int(user_id))
        await i.response.send_message(embed=E.success(f"User `{user_id}` blacklisté. Il sera banni s'il rejoint."))

    @blacklist_group.command(name="remove", description="Retire un utilisateur de la blacklist")
    @app_commands.default_permissions(administrator=True)
    async def bl_remove(self, i: discord.Interaction, user_id: str):
        self._blacklist[i.guild.id].discard(int(user_id))
        await i.response.send_message(embed=E.success(f"User `{user_id}` retiré de la blacklist."))

    # ── /audit ────────────────────────────────────────────────────────────────

    @app_commands.command(name="audit", description="Affiche les dernières entrées d'audit log")
    @app_commands.default_permissions(view_audit_log=True)
    async def audit(self, i: discord.Interaction, limit: int = 10):
        await i.response.defer()
        entries = []
        async for entry in i.guild.audit_logs(limit=min(limit, 25)):
            action = str(entry.action).replace("AuditLogAction.", "")
            entries.append(f"`{action}` — **{entry.user}** → {entry.target} — <t:{int(entry.created_at.timestamp())}:R>")
        if not entries:
            await i.followup.send(embed=E.info("Aucune entrée d'audit.")); return
        await i.followup.send(embed=E.base(f"🔍 Audit Log ({len(entries)})", "\n".join(entries)))

    # ── /security ─────────────────────────────────────────────────────────────

    @app_commands.command(name="security", description="Tableau de bord sécurité du serveur")
    @app_commands.default_permissions(manage_guild=True)
    async def security(self, i: discord.Interaction):
        cfg = db.get_guild(i.guild.id)
        g = i.guild
        wl_count = len(self._whitelist[g.id])
        bl_count = len(self._blacklist[g.id])
        e = E.base("🔒 Tableau de bord Sécurité")
        e.add_field(name="🛡️ Anti-nuke",    value="✅" if cfg.get("antinuke") else "❌")
        e.add_field(name="🚨 Anti-spam",    value="✅" if cfg.get("antispam") else "❌")
        e.add_field(name="🔗 Anti-invite",  value="✅" if cfg.get("antiinvite") else "❌")
        e.add_field(name="🌐 Anti-lien",    value="✅" if cfg.get("antilink") else "❌")
        e.add_field(name="🤖 Anti-bot",     value="✅" if cfg.get("antibot") else "❌")
        e.add_field(name="✅ Whitelist",    value=f"{wl_count} membres")
        e.add_field(name="❌ Blacklist",    value=f"{bl_count} utilisateurs")
        e.add_field(name="🔒 Vérification", value=str(g.verification_level).capitalize())
        e.add_field(name="📋 2FA Modération", value="✅" if g.mfa_level else "❌")
        await i.response.send_message(embed=e)

    # ── Listeners anti-nuke et blacklist ──────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        cfg = db.get_guild(guild.id)
        if not cfg.get("antinuke"): return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.user.id in self._whitelist[guild.id]: return
            if entry.user.id == self.bot.user.id: return
            count = self._track(guild.id, entry.user.id)
            if count >= NUKE_THRESHOLD:
                try:
                    await entry.user.ban(reason=f"[Kryvoox Anti-Nuke] {count} bans en {NUKE_WINDOW}s")
                    await self._notify(guild, cfg, f"🚨 Anti-nuke déclenché : **{entry.user}** banni ({count} bans rapides).")
                except: pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        cfg = db.get_guild(guild.id)
        if not cfg.get("antinuke"): return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            if entry.user.id in self._whitelist[guild.id]: return
            if entry.user.id == self.bot.user.id: return
            count = self._track(guild.id, entry.user.id)
            if count >= NUKE_THRESHOLD:
                try:
                    await entry.user.ban(reason=f"[Kryvoox Anti-Nuke] {count} suppressions de salons rapides")
                    await self._notify(guild, cfg, f"🚨 Anti-nuke déclenché : **{entry.user}** banni ({count} salons supprimés).")
                except: pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.id in self._blacklist[member.guild.id]:
            await member.ban(reason="[Kryvoox] Utilisateur blacklisté")

    async def _notify(self, guild: discord.Guild, cfg: dict, msg: str):
        if cfg.get("log_channel"):
            ch = guild.get_channel(cfg["log_channel"])
            if ch: await ch.send(embed=E.base("🚨 Anti-Nuke", msg, discord.Color.red()))


async def setup(bot):
    await bot.add_cog(Security(bot))
