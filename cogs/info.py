import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
import platform
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E

class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /help ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="help", description="Affiche toutes les commandes de Kryvoox")
    async def help_cmd(self, interaction: discord.Interaction):
        e = E.base("📖 Kryvoox — Aide",
            "Voici toutes les catégories de commandes disponibles.")
        e.add_field(name="ℹ️ Info", value="`/botinfo` `/userinfo` `/serverinfo` `/avatar` `/banner` `/ping` `/uptime` `/stats` `/channelinfo` `/roleinfo` `/emojiinfo` `/invite`", inline=False)
        e.add_field(name="👤 Profil", value="`/profile` `/bio` `/level` `/rank`", inline=False)
        e.add_field(name="🔨 Modération", value="`/ban` `/unban` `/kick` `/mute` `/unmute` `/timeout` `/untimeout` `/warn` `/warnings` `/clearwarns` `/clear` `/slowmode` `/lock` `/unlock` `/nick` `/role` `/unrole` `/purgebots`", inline=False)
        e.add_field(name="⚙️ Administration", value="`/setup` `/config` `/logs` `/autorole` `/welcome` `/goodbye` `/verify` `/antiinvite` `/antilink` `/antispam` `/antibot` `/backup` `/restore` `/serverlock` `/serverunlock` `/setprefix` `/embed` `/poll` `/announcement` `/reactionrole`", inline=False)
        e.add_field(name="💰 Économie", value="`/balance` `/daily` `/work` `/shop` `/buy` `/sell` `/inventory` `/pay` `/deposit` `/withdraw` `/rob` `/leaderboard` `/give`", inline=False)
        e.add_field(name="🎫 Tickets", value="`/ticket create/close/claim/add/remove/rename/transcript/reopen/delete`", inline=False)
        e.add_field(name="🤖 IA", value="`/ai` `/summarize` `/translate` `/code` `/explain` `/rewrite`", inline=False)
        e.add_field(name="🔊 Vocal", value="`/voice lock/unlock/rename/limit/bitrate`", inline=False)
        e.add_field(name="🔒 Sécurité", value="`/antinuke` `/lockdown` `/whitelist` `/blacklist` `/audit` `/security`", inline=False)
        e.add_field(name="🌍 Utilitaires", value="`/weather` `/translate` `/calculator` `/reminder` `/timer` `/timestamp` `/qrcode` `/shorturl`", inline=False)
        e.add_field(name="📊 Stats", value="`/counter` `/stats server/member/role`", inline=False)
        await interaction.response.send_message(embed=e)

    # ── /ping ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="ping", description="Latence du bot")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        color = discord.Color.green() if latency < 100 else discord.Color.orange() if latency < 200 else discord.Color.red()
        e = discord.Embed(title="🏓 Pong !", color=color)
        e.add_field(name="Latence API", value=f"`{latency}ms`")
        await interaction.response.send_message(embed=e)

    # ── /botinfo ──────────────────────────────────────────────────────────────

    @app_commands.command(name="botinfo", description="Infos sur Kryvoox")
    async def botinfo(self, interaction: discord.Interaction):
        bot = self.bot
        uptime = discord.utils.utcnow() - bot.start_time
        h, rem = divmod(int(uptime.total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        e = E.base(f"🤖 {bot.user.name}", f"Bot SaaS Discord polyvalent")
        e.set_thumbnail(url=bot.user.display_avatar.url)
        e.add_field(name="📊 Serveurs",   value=f"`{len(bot.guilds)}`")
        e.add_field(name="👥 Utilisateurs", value=f"`{sum(g.member_count for g in bot.guilds)}`")
        e.add_field(name="⏱️ Uptime",     value=f"`{h}h {m}m {s}s`")
        e.add_field(name="🐍 Python",     value=f"`{platform.python_version()}`")
        e.add_field(name="📦 discord.py", value=f"`{discord.__version__}`")
        e.add_field(name="🏓 Latence",    value=f"`{round(bot.latency*1000)}ms`")
        await interaction.response.send_message(embed=e)

    # ── /uptime ───────────────────────────────────────────────────────────────

    @app_commands.command(name="uptime", description="Temps en ligne du bot")
    async def uptime(self, interaction: discord.Interaction):
        uptime = discord.utils.utcnow() - self.bot.start_time
        h, rem = divmod(int(uptime.total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        await interaction.response.send_message(
            embed=E.info(f"⏱️ En ligne depuis **{h}h {m}m {s}s**", "Uptime")
        )

    # ── /avatar ───────────────────────────────────────────────────────────────

    @app_commands.command(name="avatar", description="Affiche l'avatar d'un membre")
    @app_commands.describe(member="Le membre (laisse vide pour toi-même)")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        e = E.base(f"🖼️ Avatar — {target.display_name}")
        e.set_image(url=target.display_avatar.url)
        e.add_field(name="Liens", value=f"[PNG]({target.display_avatar.with_format('png').url}) | [JPG]({target.display_avatar.with_format('jpg').url}) | [WEBP]({target.display_avatar.with_format('webp').url})")
        await interaction.response.send_message(embed=e)

    # ── /banner ───────────────────────────────────────────────────────────────

    @app_commands.command(name="banner", description="Affiche la bannière d'un membre")
    @app_commands.describe(member="Le membre")
    async def banner(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        fetched = await self.bot.fetch_user(target.id)
        if not fetched.banner:
            await interaction.response.send_message(embed=E.error(f"**{target.display_name}** n'a pas de bannière."))
            return
        e = E.base(f"🖼️ Bannière — {target.display_name}")
        e.set_image(url=fetched.banner.url)
        await interaction.response.send_message(embed=e)

    # ── /userinfo ─────────────────────────────────────────────────────────────

    @app_commands.command(name="userinfo", description="Infos sur un membre")
    @app_commands.describe(member="Le membre")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        m = member or interaction.user
        roles = [r.mention for r in m.roles if r.name != "@everyone"]
        e = E.base(f"👤 {m.display_name}")
        e.set_thumbnail(url=m.display_avatar.url)
        e.add_field(name="🆔 ID",          value=f"`{m.id}`")
        e.add_field(name="🏷️ Tag",          value=f"`{m}`")
        e.add_field(name="📅 Compte créé", value=f"<t:{int(m.created_at.timestamp())}:R>")
        e.add_field(name="📥 A rejoint",   value=f"<t:{int(m.joined_at.timestamp())}:R>")
        e.add_field(name="🤖 Bot",         value="Oui" if m.bot else "Non")
        e.add_field(name="🔝 Rôle top",    value=m.top_role.mention)
        if roles:
            e.add_field(name=f"🎭 Rôles ({len(roles)})", value=" ".join(roles[-10:]), inline=False)
        await interaction.response.send_message(embed=e)

    # ── /serverinfo ───────────────────────────────────────────────────────────

    @app_commands.command(name="serverinfo", description="Infos sur le serveur")
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        e = E.base(f"🏠 {g.name}")
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        e.add_field(name="🆔 ID",          value=f"`{g.id}`")
        e.add_field(name="👑 Propriétaire", value=f"{g.owner.mention}")
        e.add_field(name="👥 Membres",     value=f"`{g.member_count}`")
        e.add_field(name="📅 Créé",        value=f"<t:{int(g.created_at.timestamp())}:R>")
        e.add_field(name="💬 Salons",      value=f"`{len(g.channels)}`")
        e.add_field(name="🎭 Rôles",       value=f"`{len(g.roles)}`")
        e.add_field(name="😀 Emojis",      value=f"`{len(g.emojis)}`")
        e.add_field(name="✨ Boosts",      value=f"`{g.premium_subscription_count}` (Niveau {g.premium_tier})")
        e.add_field(name="🔒 Vérification", value=str(g.verification_level).capitalize())
        await interaction.response.send_message(embed=e)

    # ── /channelinfo ──────────────────────────────────────────────────────────

    @app_commands.command(name="channelinfo", description="Infos sur un salon")
    @app_commands.describe(channel="Le salon")
    async def channelinfo(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        ch = channel or interaction.channel
        e = E.base(f"📌 #{ch.name}")
        e.add_field(name="🆔 ID",      value=f"`{ch.id}`")
        e.add_field(name="📂 Catégorie", value=ch.category.name if ch.category else "Aucune")
        e.add_field(name="📅 Créé",    value=f"<t:{int(ch.created_at.timestamp())}:R>")
        e.add_field(name="🔒 NSFW",    value="Oui" if ch.is_nsfw() else "Non")
        e.add_field(name="🐢 Slowmode", value=f"`{ch.slowmode_delay}s`")
        if ch.topic:
            e.add_field(name="📝 Sujet", value=ch.topic, inline=False)
        await interaction.response.send_message(embed=e)

    # ── /roleinfo ─────────────────────────────────────────────────────────────

    @app_commands.command(name="roleinfo", description="Infos sur un rôle")
    @app_commands.describe(role="Le rôle")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        e = E.base(f"🎭 @{role.name}")
        e.color = role.color
        e.add_field(name="🆔 ID",       value=f"`{role.id}`")
        e.add_field(name="👥 Membres",  value=f"`{len(role.members)}`")
        e.add_field(name="🎨 Couleur",  value=f"`{role.color}`")
        e.add_field(name="📌 Position", value=f"`{role.position}`")
        e.add_field(name="🤖 Bot",      value="Oui" if role.is_bot_managed() else "Non")
        e.add_field(name="✨ Mentionnable", value="Oui" if role.mentionable else "Non")
        await interaction.response.send_message(embed=e)

    # ── /emojiinfo ────────────────────────────────────────────────────────────

    @app_commands.command(name="emojiinfo", description="Infos sur un emoji custom")
    @app_commands.describe(emoji="L'emoji (ex: <:name:id>)")
    async def emojiinfo(self, interaction: discord.Interaction, emoji: str):
        try:
            parts = emoji.strip("<>").split(":")
            animated = parts[0] == "a"
            name = parts[1]
            eid  = int(parts[2])
            url  = f"https://cdn.discordapp.com/emojis/{eid}.{'gif' if animated else 'png'}"
            e = E.base(f"😀 Emoji : {name}")
            e.add_field(name="🆔 ID", value=f"`{eid}`")
            e.add_field(name="🎞️ Animé", value="Oui" if animated else "Non")
            e.add_field(name="🔗 URL", value=f"[Voir]({url})")
            e.set_image(url=url)
            await interaction.response.send_message(embed=e)
        except:
            await interaction.response.send_message(embed=E.error("Emoji invalide — utilise un emoji custom du serveur."))

    # ── /invite ───────────────────────────────────────────────────────────────

    @app_commands.command(name="invite", description="Lien d'invitation de Kryvoox")
    async def invite(self, interaction: discord.Interaction):
        app_id = self.bot.application_id
        url = f"https://discord.com/oauth2/authorize?client_id={app_id}&permissions=8&scope=bot%20applications.commands"
        e = E.base("🔗 Inviter Kryvoox", f"[👉 Cliquez ici pour m'inviter sur votre serveur]({url})")
        await interaction.response.send_message(embed=e)

    # ── /stats ────────────────────────────────────────────────────────────────

    @app_commands.command(name="botstats", description="Statistiques globales du bot")
    async def botstats(self, interaction: discord.Interaction):
        total_users = sum(g.member_count for g in self.bot.guilds)
        total_channels = sum(len(g.channels) for g in self.bot.guilds)
        e = E.base("📊 Statistiques Kryvoox")
        e.add_field(name="🌐 Serveurs",   value=f"`{len(self.bot.guilds)}`")
        e.add_field(name="👥 Utilisateurs", value=f"`{total_users}`")
        e.add_field(name="💬 Salons",     value=f"`{total_channels}`")
        e.add_field(name="🏓 Ping",       value=f"`{round(self.bot.latency*1000)}ms`")
        await interaction.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(Info(bot))
