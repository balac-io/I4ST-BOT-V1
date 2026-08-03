import discord
from discord import app_commands
from discord.ext import commands
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /setup ────────────────────────────────────────────────────────────────

    @app_commands.command(name="setup", description="Assistant de configuration Kryvoox")
    @app_commands.default_permissions(administrator=True)
    async def setup(self, i: discord.Interaction):
        cfg = db.get_guild(i.guild.id)
        e = E.base("⚙️ Configuration actuelle — Kryvoox")
        e.add_field(name="📋 Logs",    value=f"<#{cfg['log_channel']}>" if cfg.get("log_channel") else "❌ Non défini")
        e.add_field(name="👋 Welcome", value=f"<#{cfg['welcome_channel']}>" if cfg.get("welcome_channel") else "❌ Non défini")
        e.add_field(name="👋 Goodbye", value=f"<#{cfg.get('goodbye_channel')}>" if cfg.get("goodbye_channel") else "❌ Non défini")
        e.add_field(name="🎭 Autorole", value=f"<@&{cfg['autorole']}>" if cfg.get("autorole") else "❌ Non défini")
        e.add_field(name="✅ Verify",  value=f"<@&{cfg.get('verify_role')}>" if cfg.get("verify_role") else "❌ Non défini")
        e.add_field(name="🛡️ Anti-spam",   value="✅" if cfg.get("antispam") else "❌")
        e.add_field(name="🔗 Anti-invite", value="✅" if cfg.get("antiinvite") else "❌")
        e.add_field(name="🤖 Anti-bot",    value="✅" if cfg.get("antibot") else "❌")
        e.description = "Utilisez les commandes `/config` pour modifier ces paramètres."
        await i.response.send_message(embed=e)

    # ── /config ───────────────────────────────────────────────────────────────

    config_group = app_commands.Group(name="config", description="Configuration du serveur")

    @config_group.command(name="logs", description="Définit le salon de logs")
    @app_commands.default_permissions(administrator=True)
    async def config_logs(self, i: discord.Interaction, channel: discord.TextChannel):
        cfg = db.get_guild(i.guild.id)
        cfg["log_channel"] = channel.id
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Salon de logs défini : {channel.mention}"))

    @config_group.command(name="welcome", description="Définit le salon de bienvenue")
    @app_commands.default_permissions(administrator=True)
    async def config_welcome(self, i: discord.Interaction, channel: discord.TextChannel, message: str = "Bienvenue {user} sur {server} !"):
        cfg = db.get_guild(i.guild.id)
        cfg["welcome_channel"] = channel.id
        cfg["welcome_msg"] = message
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Welcome configuré dans {channel.mention}\nMessage : `{message}`"))

    @config_group.command(name="goodbye", description="Définit le salon d'aurevoir")
    @app_commands.default_permissions(administrator=True)
    async def config_goodbye(self, i: discord.Interaction, channel: discord.TextChannel, message: str = "Au revoir {user}."):
        cfg = db.get_guild(i.guild.id)
        cfg["goodbye_channel"] = channel.id
        cfg["goodbye_msg"] = message
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Goodbye configuré dans {channel.mention}"))

    @config_group.command(name="autorole", description="Rôle donné automatiquement aux nouveaux membres")
    @app_commands.default_permissions(administrator=True)
    async def config_autorole(self, i: discord.Interaction, role: discord.Role = None):
        cfg = db.get_guild(i.guild.id)
        cfg["autorole"] = role.id if role else None
        db.save_guild(i.guild.id, cfg)
        msg = f"Autorole défini : {role.mention}" if role else "Autorole désactivé."
        await i.response.send_message(embed=E.success(msg))

    @config_group.command(name="antispam", description="Active/désactive l'anti-spam")
    @app_commands.default_permissions(administrator=True)
    async def config_antispam(self, i: discord.Interaction, enabled: bool):
        cfg = db.get_guild(i.guild.id)
        cfg["antispam"] = enabled
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Anti-spam {'activé ✅' if enabled else 'désactivé ❌'}."))

    @config_group.command(name="antiinvite", description="Bloque les invitations Discord")
    @app_commands.default_permissions(administrator=True)
    async def config_antiinvite(self, i: discord.Interaction, enabled: bool):
        cfg = db.get_guild(i.guild.id)
        cfg["antiinvite"] = enabled
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Anti-invite {'activé ✅' if enabled else 'désactivé ❌'}."))

    @config_group.command(name="antibot", description="Empêche les bots de rejoindre")
    @app_commands.default_permissions(administrator=True)
    async def config_antibot(self, i: discord.Interaction, enabled: bool):
        cfg = db.get_guild(i.guild.id)
        cfg["antibot"] = enabled
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Anti-bot {'activé ✅' if enabled else 'désactivé ❌'}."))

    @config_group.command(name="addshopitem", description="Ajoute un item à la boutique")
    @app_commands.default_permissions(administrator=True)
    async def config_addshopitem(self, i: discord.Interaction, item_id: str, name: str, price: int, role: discord.Role = None, description: str = "Item spécial"):
        cfg = db.get_guild(i.guild.id)
        cfg.setdefault("shop", {})[item_id] = {
            "name": name, "price": price,
            "role_id": role.id if role else None,
            "desc": description
        }
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Item **{name}** ajouté à la boutique pour **{price} coins**."))

    # ── /logs ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="logs", description="Définit ou affiche le salon de logs")
    @app_commands.default_permissions(manage_guild=True)
    async def logs(self, i: discord.Interaction, channel: discord.TextChannel = None):
        cfg = db.get_guild(i.guild.id)
        if channel:
            cfg["log_channel"] = channel.id
            db.save_guild(i.guild.id, cfg)
            await i.response.send_message(embed=E.success(f"Logs → {channel.mention}"))
        else:
            ch = i.guild.get_channel(cfg.get("log_channel", 0))
            await i.response.send_message(embed=E.info(f"Salon de logs actuel : {ch.mention if ch else '❌ Non défini'}"))

    # ── /autorole ─────────────────────────────────────────────────────────────

    @app_commands.command(name="autorole", description="Rôle automatique pour les nouveaux membres")
    @app_commands.default_permissions(manage_roles=True)
    async def autorole(self, i: discord.Interaction, role: discord.Role = None):
        cfg = db.get_guild(i.guild.id)
        cfg["autorole"] = role.id if role else None
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Autorole → {role.mention if role else 'désactivé'}"))

    # ── /welcome ──────────────────────────────────────────────────────────────

    @app_commands.command(name="welcome", description="Configure le message de bienvenue")
    @app_commands.default_permissions(manage_guild=True)
    async def welcome(self, i: discord.Interaction, channel: discord.TextChannel, message: str = "Bienvenue {user} sur {server} !"):
        cfg = db.get_guild(i.guild.id)
        cfg["welcome_channel"] = channel.id
        cfg["welcome_msg"] = message
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Welcome → {channel.mention}\nMessage : `{message}`\nVariables : `{{user}}`, `{{server}}`, `{{count}}`"))

    # ── /goodbye ──────────────────────────────────────────────────────────────

    @app_commands.command(name="goodbye", description="Configure le message d'au revoir")
    @app_commands.default_permissions(manage_guild=True)
    async def goodbye(self, i: discord.Interaction, channel: discord.TextChannel, message: str = "Au revoir {user}."):
        cfg = db.get_guild(i.guild.id)
        cfg["goodbye_channel"] = channel.id
        cfg["goodbye_msg"] = message
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Goodbye → {channel.mention}"))

    # ── /embed ────────────────────────────────────────────────────────────────

    @app_commands.command(name="embed", description="Envoie un embed personnalisé")
    @app_commands.default_permissions(manage_messages=True)
    async def embed_cmd(self, i: discord.Interaction, title: str, description: str, color: str = "blue", channel: discord.TextChannel = None):
        colors = {"red": discord.Color.red(), "green": discord.Color.green(), "blue": discord.Color.blue(),
                  "gold": discord.Color.gold(), "purple": discord.Color.purple(), "orange": discord.Color.orange()}
        c = colors.get(color.lower(), discord.Color.blue())
        e = discord.Embed(title=title, description=description, color=c)
        ch = channel or i.channel
        await ch.send(embed=e)
        await i.response.send_message(embed=E.success(f"Embed envoyé dans {ch.mention}."), ephemeral=True)

    # ── /poll ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="poll", description="Crée un sondage")
    @app_commands.describe(question="La question", options="Options séparées par | (max 5)")
    async def poll(self, i: discord.Interaction, question: str, options: str = "Oui|Non"):
        opts = [o.strip() for o in options.split("|")][:5]
        emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]
        desc = "\n".join(f"{emojis[idx]} {opt}" for idx, opt in enumerate(opts))
        e = E.base(f"📊 {question}", desc)
        e.set_footer(text=f"Sondage créé par {i.user.display_name}")
        msg = await i.channel.send(embed=e)
        for idx in range(len(opts)):
            await msg.add_reaction(emojis[idx])
        await i.response.send_message(embed=E.success("Sondage créé !"), ephemeral=True)

    # ── /announcement ─────────────────────────────────────────────────────────

    @app_commands.command(name="announcement", description="Envoie une annonce")
    @app_commands.default_permissions(manage_messages=True)
    async def announcement(self, i: discord.Interaction, title: str, message: str, channel: discord.TextChannel = None, ping: str = ""):
        ch = channel or i.channel
        e = E.base(f"📢 {title}", message)
        e.set_footer(text=f"Annonce par {i.user.display_name}")
        content = f"@everyone {ping}" if ping == "everyone" else f"<@&{ping}>" if ping.isdigit() else ""
        await ch.send(content=content, embed=e)
        await i.response.send_message(embed=E.success(f"Annonce envoyée dans {ch.mention}."), ephemeral=True)

    # ── /serverlock / /serverunlock ───────────────────────────────────────────

    @app_commands.command(name="serverlock", description="Verrouille tous les salons")
    @app_commands.default_permissions(administrator=True)
    async def serverlock(self, i: discord.Interaction, reason: str = "Maintenance"):
        await i.response.defer()
        for ch in i.guild.text_channels:
            await ch.set_permissions(i.guild.default_role, send_messages=False)
        await i.followup.send(embed=E.warn(f"🔒 Serveur verrouillé. Raison : {reason}"))

    @app_commands.command(name="serverunlock", description="Déverrouille tous les salons")
    @app_commands.default_permissions(administrator=True)
    async def serverunlock(self, i: discord.Interaction):
        await i.response.defer()
        for ch in i.guild.text_channels:
            await ch.set_permissions(i.guild.default_role, send_messages=None)
        await i.followup.send(embed=E.success("🔓 Serveur déverrouillé."))

    # ── /verify ───────────────────────────────────────────────────────────────

    @app_commands.command(name="verify", description="Configure le rôle de vérification")
    @app_commands.default_permissions(administrator=True)
    async def verify(self, i: discord.Interaction, role: discord.Role):
        cfg = db.get_guild(i.guild.id)
        cfg["verify_role"] = role.id
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Rôle de vérification → {role.mention}"))

    # ── /backup ───────────────────────────────────────────────────────────────

    @app_commands.command(name="backup", description="Sauvegarde la configuration du serveur")
    @app_commands.default_permissions(administrator=True)
    async def backup(self, i: discord.Interaction):
        import json, io
        cfg = db.get_guild(i.guild.id)
        data = json.dumps(cfg, indent=2, ensure_ascii=False)
        f = discord.File(fp=io.StringIO(data), filename=f"backup-{i.guild.id}.json")
        await i.response.send_message(embed=E.success("Backup généré."), file=f)

    # ── /antiinvite / /antilink ───────────────────────────────────────────────

    @app_commands.command(name="antiinvite", description="Active/désactive le filtre d'invitations Discord")
    @app_commands.default_permissions(manage_guild=True)
    async def antiinvite(self, i: discord.Interaction, enabled: bool):
        cfg = db.get_guild(i.guild.id)
        cfg["antiinvite"] = enabled
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Anti-invite {'activé ✅' if enabled else 'désactivé ❌'}."))

    @app_commands.command(name="antilink", description="Active/désactive le filtre de liens externes")
    @app_commands.default_permissions(manage_guild=True)
    async def antilink(self, i: discord.Interaction, enabled: bool):
        cfg = db.get_guild(i.guild.id)
        cfg["antilink"] = enabled
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Anti-lien {'activé ✅' if enabled else 'désactivé ❌'}."))

    @app_commands.command(name="antispam", description="Active/désactive l'anti-spam")
    @app_commands.default_permissions(manage_guild=True)
    async def antispam(self, i: discord.Interaction, enabled: bool):
        cfg = db.get_guild(i.guild.id)
        cfg["antispam"] = enabled
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Anti-spam {'activé ✅' if enabled else 'désactivé ❌'}."))

    @app_commands.command(name="antibot", description="Empêche les bots de rejoindre automatiquement")
    @app_commands.default_permissions(manage_guild=True)
    async def antibot(self, i: discord.Interaction, enabled: bool):
        cfg = db.get_guild(i.guild.id)
        cfg["antibot"] = enabled
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Anti-bot {'activé ✅' if enabled else 'désactivé ❌'}."))

    # ── Events welcome/goodbye/autorole ───────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = db.get_guild(member.guild.id)
        if cfg.get("antibot") and member.bot:
            await member.kick(reason="Anti-bot activé")
            return
        if cfg.get("autorole"):
            role = member.guild.get_role(cfg["autorole"])
            if role:
                await member.add_roles(role)
        if cfg.get("welcome_channel"):
            ch = member.guild.get_channel(cfg["welcome_channel"])
            if ch:
                msg = cfg.get("welcome_msg","Bienvenue {user} !").format(
                    user=member.mention, server=member.guild.name,
                    count=member.guild.member_count
                )
                e = E.base("👋 Bienvenue !", msg, discord.Color.green())
                e.set_thumbnail(url=member.display_avatar.url)
                await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = db.get_guild(member.guild.id)
        if cfg.get("goodbye_channel"):
            ch = member.guild.get_channel(cfg["goodbye_channel"])
            if ch:
                msg = cfg.get("goodbye_msg","Au revoir {user}.").format(
                    user=str(member), server=member.guild.name
                )
                e = E.base("👋 Au revoir", msg, discord.Color.red())
                await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        cfg = db.get_guild(message.guild.id)
        import re
        if cfg.get("antiinvite") and re.search(r"discord\.gg/\S+", message.content, re.IGNORECASE):
            await message.delete()
            await message.channel.send(embed=E.error(f"{message.author.mention} les invitations Discord sont interdites."), delete_after=5)
        if cfg.get("antilink") and re.search(r"https?://(?!discord)", message.content, re.IGNORECASE):
            await message.delete()
            await message.channel.send(embed=E.error(f"{message.author.mention} les liens externes sont interdits."), delete_after=5)


async def setup(bot):
    await bot.add_cog(Admin(bot))
