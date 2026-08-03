import discord
from discord import app_commands
from discord.ext import commands
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /stats server ─────────────────────────────────────────────────────────

    stats_group = app_commands.Group(name="stats", description="Statistiques")

    @stats_group.command(name="server", description="Stats détaillées du serveur")
    async def stats_server(self, i: discord.Interaction):
        g = i.guild
        bots    = sum(1 for m in g.members if m.bot)
        humans  = g.member_count - bots
        online  = sum(1 for m in g.members if m.status != discord.Status.offline and not m.bot)
        text_ch = len(g.text_channels)
        voice_ch = len(g.voice_channels)
        cats    = len(g.categories)

        e = E.base(f"📊 Stats — {g.name}")
        if g.icon: e.set_thumbnail(url=g.icon.url)
        e.add_field(name="👥 Membres",    value=f"`{g.member_count}`")
        e.add_field(name="🧑 Humains",    value=f"`{humans}`")
        e.add_field(name="🤖 Bots",       value=f"`{bots}`")
        e.add_field(name="🟢 En ligne",   value=f"`{online}`")
        e.add_field(name="💬 Salons text",  value=f"`{text_ch}`")
        e.add_field(name="🔊 Salons vocal", value=f"`{voice_ch}`")
        e.add_field(name="📂 Catégories", value=f"`{cats}`")
        e.add_field(name="🎭 Rôles",      value=f"`{len(g.roles)}`")
        e.add_field(name="😀 Emojis",     value=f"`{len(g.emojis)}/{g.emoji_limit}`")
        e.add_field(name="✨ Boosts",     value=f"`{g.premium_subscription_count}` (Tier {g.premium_tier})")
        e.add_field(name="📅 Créé",       value=f"<t:{int(g.created_at.timestamp())}:R>")
        e.add_field(name="🔒 Vérif",      value=str(g.verification_level).capitalize())
        await i.response.send_message(embed=e)

    @stats_group.command(name="member", description="Stats d'un membre")
    async def stats_member(self, i: discord.Interaction, member: discord.Member = None):
        m = member or i.user
        u = db.get_user(m.id)
        roles = [r.mention for r in m.roles if r.name != "@everyone"]

        e = E.base(f"📊 Stats — {m.display_name}")
        e.set_thumbnail(url=m.display_avatar.url)
        e.add_field(name="🆔 ID",           value=f"`{m.id}`")
        e.add_field(name="📅 Compte créé",  value=f"<t:{int(m.created_at.timestamp())}:R>")
        e.add_field(name="📥 A rejoint",    value=f"<t:{int(m.joined_at.timestamp())}:R>")
        e.add_field(name="⭐ Niveau",       value=f"`{u.get('level', 1)}`")
        e.add_field(name="✨ XP",           value=f"`{u.get('xp', 0)}`")
        e.add_field(name="💰 Coins",        value=f"`{u.get('coins', 0)}`")
        e.add_field(name="💬 Messages",     value=f"`{u.get('total_msgs', 0)}`")
        e.add_field(name="🎭 Rôles",        value=f"`{len(roles)}`")
        e.add_field(name="🤖 Bot",          value="Oui" if m.bot else "Non")
        await i.response.send_message(embed=e)

    @stats_group.command(name="role", description="Stats d'un rôle")
    async def stats_role(self, i: discord.Interaction, role: discord.Role):
        bots   = sum(1 for m in role.members if m.bot)
        humans = len(role.members) - bots

        e = E.base(f"📊 Stats — @{role.name}")
        e.color = role.color
        e.add_field(name="👥 Membres",   value=f"`{len(role.members)}`")
        e.add_field(name="🧑 Humains",   value=f"`{humans}`")
        e.add_field(name="🤖 Bots",      value=f"`{bots}`")
        e.add_field(name="🎨 Couleur",   value=f"`{role.color}`")
        e.add_field(name="📌 Position",  value=f"`{role.position}`")
        e.add_field(name="📅 Créé",      value=f"<t:{int(role.created_at.timestamp())}:R>")
        e.add_field(name="✨ Mentionnable", value="Oui" if role.mentionable else "Non")
        e.add_field(name="🤖 Géré bot", value="Oui" if role.is_bot_managed() else "Non")
        await i.response.send_message(embed=e)

    # ── /counter ──────────────────────────────────────────────────────────────

    counter_group = app_commands.Group(name="counter", description="Compteurs automatiques")

    @counter_group.command(name="create", description="Crée un compteur automatique")
    @app_commands.describe(type="Type : members | bots | channels | roles")
    @app_commands.choices(type=[
        app_commands.Choice(name="Membres",  value="members"),
        app_commands.Choice(name="Bots",     value="bots"),
        app_commands.Choice(name="Salons",   value="channels"),
        app_commands.Choice(name="Rôles",    value="roles"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def counter_create(self, i: discord.Interaction, type: str):
        g = i.guild
        labels = {
            "members":  f"👥 Membres : {g.member_count}",
            "bots":     f"🤖 Bots : {sum(1 for m in g.members if m.bot)}",
            "channels": f"💬 Salons : {len(g.channels)}",
            "roles":    f"🎭 Rôles : {len(g.roles)}",
        }
        name = labels[type]
        ch = await g.create_voice_channel(name=name)
        await ch.set_permissions(g.default_role, connect=False)

        cfg = db.get_guild(g.id)
        cfg.setdefault("counters", {})[type] = ch.id
        db.save_guild(g.id, cfg)

        await i.response.send_message(embed=E.success(f"Compteur **{type}** créé : {ch.mention}"))

    @counter_group.command(name="delete", description="Supprime un compteur")
    @app_commands.choices(type=[
        app_commands.Choice(name="Membres",  value="members"),
        app_commands.Choice(name="Bots",     value="bots"),
        app_commands.Choice(name="Salons",   value="channels"),
        app_commands.Choice(name="Rôles",    value="roles"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def counter_delete(self, i: discord.Interaction, type: str):
        cfg = db.get_guild(i.guild.id)
        ch_id = cfg.get("counters", {}).pop(type, None)
        db.save_guild(i.guild.id, cfg)
        if ch_id:
            ch = i.guild.get_channel(ch_id)
            if ch: await ch.delete()
        await i.response.send_message(embed=E.success(f"Compteur **{type}** supprimé."))

    @counter_group.command(name="list", description="Liste les compteurs actifs")
    async def counter_list(self, i: discord.Interaction):
        cfg = db.get_guild(i.guild.id)
        counters = cfg.get("counters", {})
        if not counters:
            await i.response.send_message(embed=E.info("Aucun compteur actif.")); return
        lines = [f"**{t}** → <#{cid}>" for t, cid in counters.items()]
        await i.response.send_message(embed=E.info("\n".join(lines), "📊 Compteurs actifs"))

    # ── Mise à jour auto des compteurs ────────────────────────────────────────

    async def _update_counters(self, guild: discord.Guild):
        cfg = db.get_guild(guild.id)
        counters = cfg.get("counters", {})
        if not counters: return
        updates = {
            "members":  f"👥 Membres : {guild.member_count}",
            "bots":     f"🤖 Bots : {sum(1 for m in guild.members if m.bot)}",
            "channels": f"💬 Salons : {len(guild.channels)}",
            "roles":    f"🎭 Rôles : {len(guild.roles)}",
        }
        for type, ch_id in counters.items():
            ch = guild.get_channel(ch_id)
            if ch and ch.name != updates[type]:
                try: await ch.edit(name=updates[type])
                except: pass

    @commands.Cog.listener()
    async def on_member_join(self, member): await self._update_counters(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member): await self._update_counters(member.guild)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, ch): await self._update_counters(ch.guild)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, ch): await self._update_counters(ch.guild)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role): await self._update_counters(role.guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role): await self._update_counters(role.guild)


async def setup(bot):
    await bot.add_cog(Stats(bot))
