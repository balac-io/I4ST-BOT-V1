import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Button, ChannelSelect, RoleSelect
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

# Image par défaut fiable (banner neutre CDN)
DEFAULT_WELCOME_IMAGE = "https://media.discordapp.net/attachments/000000000000000000/000000000000000000/welcome.png"  # sera ignorée si invalide
# On préfère ne PAS forcer une image cassée : si pas d'URL custom, pas d'image.
DEFAULT_WELCOME_IMAGE = None


def _status(val, yes="✅", no="❌"):
    return yes if val else no


def _is_valid_image_url(url: str | None) -> bool:
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return False
    # Refuse les liens Discord attachment (expirent souvent)
    if "cdn.discordapp.com/attachments" in url or "media.discordapp.net/attachments" in url:
        # On accepte quand même mais c'est fragile — Discord peut les expirer
        pass
    # Extensions / formats courants
    lower = url.lower().split("?")[0]
    if any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return True
    # Certains hébergeurs n'ont pas d'extension visible
    if any(host in lower for host in ("imgur.com", "i.imgur.com", "cdn.discordapp.com", "media.discordapp.net",
                                       "i.ibb.co", "imgbb.com", "catbox.moe", "tenor.com", "giphy.com",
                                       "raw.githubusercontent.com", "images-ext")):
        return True
    return False


def _apply_welcome_image(embed: discord.Embed, cfg: dict):
    """Ajoute l'image de bienvenue seulement si l'URL est valide."""
    img = cfg.get("welcome_image") or DEFAULT_WELCOME_IMAGE
    if img and _is_valid_image_url(img):
        embed.set_image(url=img.strip())


def _build_dashboard_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    e = discord.Embed(
        title="⚙️  Kryvoox — Dashboard Configuration",
        description=f"**Serveur :** {guild.name}\nSélectionne une catégorie ci-dessous pour configurer.",
        color=discord.Color.from_str("#5865F2")
    )
    if guild.icon:
        e.set_thumbnail(url=guild.icon.url)

    logs = f"<#{cfg['log_channel']}>" if cfg.get("log_channel") else "—"
    wel  = f"<#{cfg['welcome_channel']}>" if cfg.get("welcome_channel") else "—"
    bye  = f"<#{cfg.get('goodbye_channel')}>" if cfg.get("goodbye_channel") else "—"
    auto = f"<@&{cfg['autorole']}>" if cfg.get("autorole") else "—"
    ver  = f"<@&{cfg.get('verify_role')}>" if cfg.get("verify_role") else "—"

    e.add_field(name="📋 Salons", value=f"Logs · {logs}\nWelcome · {wel}\nGoodbye · {bye}", inline=True)
    e.add_field(name="🎭 Rôles", value=f"Autorole · {auto}\nVerify · {ver}", inline=True)
    e.add_field(
        name="🛡️ Sécurité",
        value=(
            f"Anti-spam {_status(cfg.get('antispam'))}\n"
            f"Anti-invite {_status(cfg.get('antiinvite'))}\n"
            f"Anti-bot {_status(cfg.get('antibot'))}\n"
            f"Anti-nuke {_status(cfg.get('antinuke'))}"
        ),
        inline=True
    )
    e.set_footer(text="Kryvoox Config • Clique sur le menu pour modifier")
    e.timestamp = discord.utils.utcnow()
    return e


class ConfigSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Salons (Logs / Welcome / Goodbye)", value="channels", emoji="📋"),
            discord.SelectOption(label="Rôles (Autorole / Verify)", value="roles", emoji="🎭"),
            discord.SelectOption(label="Sécurité", value="security", emoji="🛡️"),
            discord.SelectOption(label="Welcome personnalisé", value="welcome_custom", emoji="👋"),
            discord.SelectOption(label="Rafraîchir", value="refresh", emoji="🔄"),
        ]
        super().__init__(placeholder="Choisir une catégorie…", options=options, custom_id="config_main_select")

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        cfg = db.get_guild(interaction.guild.id)

        if value == "refresh":
            await interaction.response.edit_message(embed=_build_dashboard_embed(interaction.guild, cfg), view=ConfigDashboardView())
            return

        if value == "channels":
            embed = discord.Embed(title="📋 Configuration des Salons", description="Utilise les menus ci-dessous.", color=discord.Color.blurple())
            await interaction.response.edit_message(embed=embed, view=ChannelsConfigView())
            return

        if value == "roles":
            embed = discord.Embed(title="🎭 Configuration des Rôles", description="Choisis les rôles automatiques.", color=discord.Color.blurple())
            await interaction.response.edit_message(embed=embed, view=RolesConfigView())
            return

        if value == "security":
            embed = discord.Embed(title="🛡️ Configuration Sécurité", description="Active ou désactive les protections.", color=discord.Color.blurple())
            await interaction.response.edit_message(embed=embed, view=SecurityConfigView(cfg))
            return

        if value == "welcome_custom":
            img_status = cfg.get("welcome_image") or "*(aucune)*"
            embed = discord.Embed(
                title="👋 Welcome personnalisé",
                description=(
                    "Configure le message et l'image de bienvenue.\n\n"
                    "**Variables :** `{user}` `{server}` `{count}`\n\n"
                    f"**Message :** `{cfg.get('welcome_msg', 'Bienvenue {user} !')}`\n"
                    f"**Image :** `{img_status[:80]}`"
                ),
                color=discord.Color.green()
            )
            _apply_welcome_image(embed, cfg)
            await interaction.response.edit_message(embed=embed, view=WelcomeCustomView())
            return


class ConfigDashboardView(View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ConfigSelect())


class BackButton(Button):
    def __init__(self):
        super().__init__(label="← Retour", style=discord.ButtonStyle.secondary, custom_id="config_back")

    async def callback(self, interaction: discord.Interaction):
        cfg = db.get_guild(interaction.guild.id)
        await interaction.response.edit_message(embed=_build_dashboard_embed(interaction.guild, cfg), view=ConfigDashboardView())


class LogChannelSelect(ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Salon de logs…", channel_types=[discord.ChannelType.text], max_values=1)

    async def callback(self, interaction: discord.Interaction):
        ch = self.values[0]
        cfg = db.get_guild(interaction.guild.id)
        cfg["log_channel"] = ch.id
        db.save_guild(interaction.guild.id, cfg)
        await interaction.response.send_message(embed=E.success(f"Logs → {ch.mention}"), ephemeral=True)


class WelcomeChannelSelect(ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Salon de bienvenue…", channel_types=[discord.ChannelType.text], max_values=1)

    async def callback(self, interaction: discord.Interaction):
        ch = self.values[0]
        cfg = db.get_guild(interaction.guild.id)
        cfg["welcome_channel"] = ch.id
        db.save_guild(interaction.guild.id, cfg)
        await interaction.response.send_message(embed=E.success(f"Welcome → {ch.mention}"), ephemeral=True)


class GoodbyeChannelSelect(ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Salon d'au revoir…", channel_types=[discord.ChannelType.text], max_values=1)

    async def callback(self, interaction: discord.Interaction):
        ch = self.values[0]
        cfg = db.get_guild(interaction.guild.id)
        cfg["goodbye_channel"] = ch.id
        db.save_guild(interaction.guild.id, cfg)
        await interaction.response.send_message(embed=E.success(f"Goodbye → {ch.mention}"), ephemeral=True)


class ChannelsConfigView(View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(LogChannelSelect())
        self.add_item(WelcomeChannelSelect())
        self.add_item(GoodbyeChannelSelect())
        self.add_item(BackButton())


class AutoroleSelect(RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Rôle automatique…", max_values=1)

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        cfg = db.get_guild(interaction.guild.id)
        cfg["autorole"] = role.id
        db.save_guild(interaction.guild.id, cfg)
        await interaction.response.send_message(embed=E.success(f"Autorole → {role.mention}"), ephemeral=True)


class VerifyRoleSelect(RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Rôle de vérification…", max_values=1)

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        cfg = db.get_guild(interaction.guild.id)
        cfg["verify_role"] = role.id
        db.save_guild(interaction.guild.id, cfg)
        await interaction.response.send_message(embed=E.success(f"Verify → {role.mention}"), ephemeral=True)


class RolesConfigView(View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(AutoroleSelect())
        self.add_item(VerifyRoleSelect())
        self.add_item(BackButton())


class SecurityConfigView(View):
    def __init__(self, cfg: dict):
        super().__init__(timeout=180)
        self.cfg = cfg

        self.antispam_btn = Button(
            label=f"Anti-spam {'ON' if cfg.get('antispam') else 'OFF'}",
            style=discord.ButtonStyle.success if cfg.get("antispam") else discord.ButtonStyle.danger,
            custom_id="toggle_antispam"
        )
        self.antispam_btn.callback = self.toggle_antispam
        self.add_item(self.antispam_btn)

        self.antiinvite_btn = Button(
            label=f"Anti-invite {'ON' if cfg.get('antiinvite') else 'OFF'}",
            style=discord.ButtonStyle.success if cfg.get("antiinvite") else discord.ButtonStyle.danger,
            custom_id="toggle_antiinvite"
        )
        self.antiinvite_btn.callback = self.toggle_antiinvite
        self.add_item(self.antiinvite_btn)

        self.antibot_btn = Button(
            label=f"Anti-bot {'ON' if cfg.get('antibot') else 'OFF'}",
            style=discord.ButtonStyle.success if cfg.get("antibot") else discord.ButtonStyle.danger,
            custom_id="toggle_antibot"
        )
        self.antibot_btn.callback = self.toggle_antibot
        self.add_item(self.antibot_btn)

        self.antinuke_btn = Button(
            label=f"Anti-nuke {'ON' if cfg.get('antinuke') else 'OFF'}",
            style=discord.ButtonStyle.success if cfg.get("antinuke") else discord.ButtonStyle.danger,
            custom_id="toggle_antinuke"
        )
        self.antinuke_btn.callback = self.toggle_antinuke
        self.add_item(self.antinuke_btn)
        self.add_item(BackButton())

    async def _toggle(self, interaction: discord.Interaction, key: str, btn: Button):
        cfg = db.get_guild(interaction.guild.id)
        cfg[key] = not cfg.get(key, False)
        db.save_guild(interaction.guild.id, cfg)
        btn.label = f"{key.replace('anti', 'Anti-').title()} {'ON' if cfg[key] else 'OFF'}"
        btn.style = discord.ButtonStyle.success if cfg[key] else discord.ButtonStyle.danger
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(embed=E.success(f"**{key}** → {'activé' if cfg[key] else 'désactivé'}"), ephemeral=True)

    async def toggle_antispam(self, interaction: discord.Interaction):
        await self._toggle(interaction, "antispam", self.antispam_btn)

    async def toggle_antiinvite(self, interaction: discord.Interaction):
        await self._toggle(interaction, "antiinvite", self.antiinvite_btn)

    async def toggle_antibot(self, interaction: discord.Interaction):
        await self._toggle(interaction, "antibot", self.antibot_btn)

    async def toggle_antinuke(self, interaction: discord.Interaction):
        await self._toggle(interaction, "antinuke", self.antinuke_btn)


class WelcomeCustomView(View):
    def __init__(self):
        super().__init__(timeout=180)

        set_msg = Button(label="Modifier le message", style=discord.ButtonStyle.primary, emoji="✍️")
        set_msg.callback = self.set_message
        self.add_item(set_msg)

        set_img = Button(label="Définir l'image (URL)", style=discord.ButtonStyle.primary, emoji="🖼️")
        set_img.callback = self.set_image
        self.add_item(set_img)

        clear_img = Button(label="Retirer l'image", style=discord.ButtonStyle.danger, emoji="🗑️")
        clear_img.callback = self.clear_image
        self.add_item(clear_img)

        preview = Button(label="Aperçu", style=discord.ButtonStyle.success, emoji="👁️")
        preview.callback = self.preview
        self.add_item(preview)

        self.add_item(BackButton())

    async def set_message(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WelcomeMessageModal())

    async def set_image(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WelcomeImageModal())

    async def clear_image(self, interaction: discord.Interaction):
        cfg = db.get_guild(interaction.guild.id)
        cfg["welcome_image"] = None
        db.save_guild(interaction.guild.id, cfg)
        await interaction.response.send_message(embed=E.success("Image de bienvenue retirée."), ephemeral=True)

    async def preview(self, interaction: discord.Interaction):
        cfg = db.get_guild(interaction.guild.id)
        msg = cfg.get("welcome_msg", "Bienvenue {user} sur {server} !").format(
            user=interaction.user.mention,
            server=interaction.guild.name,
            count=interaction.guild.member_count
        )
        e = discord.Embed(title="👋 Bienvenue !", description=msg, color=discord.Color.from_str("#57F287"))
        e.set_thumbnail(url=interaction.user.display_avatar.url)
        _apply_welcome_image(e, cfg)
        e.set_footer(text=f"Tu es le {interaction.guild.member_count}ème membre • Kryvoox")
        await interaction.response.send_message(embed=e, ephemeral=True)


class WelcomeMessageModal(discord.ui.Modal, title="Message de bienvenue"):
    message = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.paragraph,
        placeholder="Bienvenue {user} sur {server} ! Tu es le {count}ème membre.",
        max_length=500,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        cfg = db.get_guild(interaction.guild.id)
        cfg["welcome_msg"] = self.message.value
        db.save_guild(interaction.guild.id, cfg)
        await interaction.response.send_message(embed=E.success("Message de bienvenue mis à jour !"), ephemeral=True)


class WelcomeImageModal(discord.ui.Modal, title="Image de bienvenue"):
    url = discord.ui.TextInput(
        label="URL directe de l'image (png/jpg/gif/webp)",
        placeholder="https://i.imgur.com/xxxx.png  (lien DIRECT, pas Discord)",
        max_length=400,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        url = self.url.value.strip()
        if not _is_valid_image_url(url):
            await interaction.response.send_message(
                embed=E.error(
                    "URL invalide.\n\n"
                    "Utilise un **lien direct** vers une image :\n"
                    "• se termine par `.png` `.jpg` `.gif` `.webp`\n"
                    "• hébergée sur **Imgur**, **ImgBB**, **Catbox**, etc.\n\n"
                    "⚠️ Les liens Discord (cdn.discordapp.com) expirent souvent."
                ),
                ephemeral=True
            )
            return

        cfg = db.get_guild(interaction.guild.id)
        cfg["welcome_image"] = url
        db.save_guild(interaction.guild.id, cfg)

        e = E.success("Image de bienvenue définie !")
        e.set_image(url=url)
        await interaction.response.send_message(embed=e, ephemeral=True)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="config", description="Ouvre le dashboard de configuration Kryvoox")
    @app_commands.default_permissions(administrator=True)
    async def config(self, i: discord.Interaction):
        cfg = db.get_guild(i.guild.id)
        await i.response.send_message(embed=_build_dashboard_embed(i.guild, cfg), view=ConfigDashboardView(), ephemeral=True)

    @app_commands.command(name="setup", description="Ouvre le dashboard de configuration")
    @app_commands.default_permissions(administrator=True)
    async def setup_cmd(self, i: discord.Interaction):
        await self.config(i)

    @app_commands.command(name="welcomeimage", description="Définit l'image de bienvenue via une pièce jointe")
    @app_commands.describe(image="Fichier image (png/jpg/gif/webp)")
    @app_commands.default_permissions(manage_guild=True)
    async def welcomeimage(self, i: discord.Interaction, image: discord.Attachment):
        if not image.content_type or not image.content_type.startswith("image/"):
            await i.response.send_message(embed=E.error("Le fichier doit être une image."), ephemeral=True)
            return
        if image.size > 8 * 1024 * 1024:
            await i.response.send_message(embed=E.error("Image trop lourde (max 8 Mo)."), ephemeral=True)
            return

        # Re-upload dans le salon pour obtenir une URL CDN (plus stable à court terme)
        # Note: les attachments Discord peuvent expirer — préférer Imgur pour du long terme
        await i.response.defer(ephemeral=True)
        try:
            file = await image.to_file()
            # Envoie en éphémère impossible avec file durable : on stocke l'URL originale de l'attachment
            url = image.url
            cfg = db.get_guild(i.guild.id)
            cfg["welcome_image"] = url
            db.save_guild(i.guild.id, cfg)

            e = E.success(
                "Image de bienvenue définie via pièce jointe.\n\n"
                "⚠️ Les liens Discord peuvent expirer. "
                "Pour une image **permanente**, héberge-la sur Imgur/ImgBB et utilise l'URL dans `/config`."
            )
            e.set_image(url=url)
            await i.followup.send(embed=e, ephemeral=True)
        except Exception as ex:
            await i.followup.send(embed=E.error(f"Erreur : {ex}"), ephemeral=True)

    @app_commands.command(name="logs", description="Définit ou affiche le salon de logs")
    @app_commands.default_permissions(manage_guild=True)
    async def logs(self, i: discord.Interaction, channel: discord.TextChannel = None):
        cfg = db.get_guild(i.guild.id)
        if channel:
            cfg["log_channel"] = channel.id
            db.save_guild(i.guild.id, cfg)
            await i.response.send_message(embed=E.success(f"Logs → {channel.mention}"))
        else:
            ch = i.guild.get_channel(cfg.get("log_channel") or 0)
            await i.response.send_message(embed=E.info(f"Salon de logs : {ch.mention if ch else '❌ Non défini'}"))

    @app_commands.command(name="autorole", description="Rôle automatique pour les nouveaux membres")
    @app_commands.default_permissions(manage_roles=True)
    async def autorole(self, i: discord.Interaction, role: discord.Role = None):
        cfg = db.get_guild(i.guild.id)
        cfg["autorole"] = role.id if role else None
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Autorole → {role.mention if role else 'désactivé'}"))

    @app_commands.command(name="welcome", description="Configure le message de bienvenue")
    @app_commands.default_permissions(manage_guild=True)
    async def welcome(self, i: discord.Interaction, channel: discord.TextChannel, message: str = "Bienvenue {user} sur {server} !"):
        cfg = db.get_guild(i.guild.id)
        cfg["welcome_channel"] = channel.id
        cfg["welcome_msg"] = message
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(
            f"Welcome → {channel.mention}\nMessage : `{message}`\nVariables : `{{user}}`, `{{server}}`, `{{count}}`"
        ))

    @app_commands.command(name="goodbye", description="Configure le message d'au revoir")
    @app_commands.default_permissions(manage_guild=True)
    async def goodbye(self, i: discord.Interaction, channel: discord.TextChannel, message: str = "Au revoir {user}."):
        cfg = db.get_guild(i.guild.id)
        cfg["goodbye_channel"] = channel.id
        cfg["goodbye_msg"] = message
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Goodbye → {channel.mention}"))

    @app_commands.command(name="embed", description="Envoie un embed personnalisé")
    @app_commands.default_permissions(manage_messages=True)
    async def embed_cmd(self, i: discord.Interaction, title: str, description: str, color: str = "blue", channel: discord.TextChannel = None):
        colors = {"red": discord.Color.red(), "green": discord.Color.green(), "blue": discord.Color.blue(),
                  "gold": discord.Color.gold(), "purple": discord.Color.purple(), "orange": discord.Color.orange()}
        e = discord.Embed(title=title, description=description, color=colors.get(color.lower(), discord.Color.blue()))
        ch = channel or i.channel
        await ch.send(embed=e)
        await i.response.send_message(embed=E.success(f"Embed envoyé dans {ch.mention}."), ephemeral=True)

    @app_commands.command(name="poll", description="Crée un sondage")
    async def poll(self, i: discord.Interaction, question: str, options: str = "Oui|Non"):
        opts = [o.strip() for o in options.split("|")][:5]
        emojis = ["㇡️", "㇢️", "㇣️", "㇤️", "㇥️"]
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        desc = "\n".join(f"{emojis[idx]} {opt}" for idx, opt in enumerate(opts))
        e = E.base(f"📊 {question}", desc)
        e.set_footer(text=f"Sondage par {i.user.display_name}")
        msg = await i.channel.send(embed=e)
        for idx in range(len(opts)):
            await msg.add_reaction(emojis[idx])
        await i.response.send_message(embed=E.success("Sondage créé !"), ephemeral=True)

    @app_commands.command(name="announcement", description="Envoie une annonce")
    @app_commands.default_permissions(manage_messages=True)
    async def announcement(self, i: discord.Interaction, title: str, message: str, channel: discord.TextChannel = None, ping: str = ""):
        ch = channel or i.channel
        e = E.base(f"📢 {title}", message)
        e.set_footer(text=f"Annonce par {i.user.display_name}")
        content = f"@everyone {ping}" if ping == "everyone" else (f"<@&{ping}>" if ping.isdigit() else "")
        await ch.send(content=content, embed=e)
        await i.response.send_message(embed=E.success(f"Annonce envoyée dans {ch.mention}."), ephemeral=True)

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

    @app_commands.command(name="verify", description="Configure le rôle de vérification")
    @app_commands.default_permissions(administrator=True)
    async def verify(self, i: discord.Interaction, role: discord.Role):
        cfg = db.get_guild(i.guild.id)
        cfg["verify_role"] = role.id
        db.save_guild(i.guild.id, cfg)
        await i.response.send_message(embed=E.success(f"Rôle de vérification → {role.mention}"))

    @app_commands.command(name="backup", description="Sauvegarde la configuration du serveur")
    @app_commands.default_permissions(administrator=True)
    async def backup(self, i: discord.Interaction):
        import json, io
        cfg = db.get_guild(i.guild.id)
        data = json.dumps(cfg, indent=2, ensure_ascii=False)
        f = discord.File(fp=io.StringIO(data), filename=f"backup-{i.guild.id}.json")
        await i.response.send_message(embed=E.success("Backup généré."), file=f)

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

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = db.get_guild(member.guild.id)

        if cfg.get("antibot") and member.bot:
            try:
                await member.kick(reason="Anti-bot activé")
            except Exception:
                pass
            return

        if cfg.get("autorole"):
            role = member.guild.get_role(cfg["autorole"])
            if role:
                try:
                    await member.add_roles(role)
                except Exception:
                    pass

        if cfg.get("welcome_channel"):
            ch = member.guild.get_channel(cfg["welcome_channel"])
            if ch:
                msg = cfg.get("welcome_msg", "Bienvenue {user} sur {server} !").format(
                    user=member.mention,
                    server=member.guild.name,
                    count=member.guild.member_count
                )
                e = discord.Embed(
                    title="👋 Bienvenue !",
                    description=msg,
                    color=discord.Color.from_str("#57F287")
                )
                e.set_thumbnail(url=member.display_avatar.url)
                _apply_welcome_image(e, cfg)
                e.set_footer(text=f"Tu es le {member.guild.member_count}ème membre • Kryvoox")
                e.timestamp = discord.utils.utcnow()
                try:
                    await ch.send(embed=e)
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = db.get_guild(member.guild.id)
        if cfg.get("goodbye_channel"):
            ch = member.guild.get_channel(cfg["goodbye_channel"])
            if ch:
                msg = cfg.get("goodbye_msg", "Au revoir {user}.").format(
                    user=str(member), server=member.guild.name
                )
                e = E.base("👋 Au revoir", msg, discord.Color.red())
                try:
                    await ch.send(embed=e)
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        cfg = db.get_guild(message.guild.id)
        if cfg.get("antiinvite") and re.search(r"discord\.gg/\S+", message.content, re.IGNORECASE):
            try:
                await message.delete()
                await message.channel.send(
                    embed=E.error(f"{message.author.mention} les invitations Discord sont interdites."),
                    delete_after=5
                )
            except Exception:
                pass
        if cfg.get("antilink") and re.search(r"https?://(?!discord)", message.content, re.IGNORECASE):
            try:
                await message.delete()
                await message.channel.send(
                    embed=E.error(f"{message.author.mention} les liens externes sont interdits."),
                    delete_after=5
                )
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(Admin(bot))
