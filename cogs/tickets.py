import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Button
import asyncio, io
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

CATEGORIES = ["Support","Signalement","Question","Partenariat","Autre"]

# ─── UI Components ────────────────────────────────────────────────────────────

class TicketSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Support",      emoji="🆘", description="Besoin d'aide"),
            discord.SelectOption(label="Signalement",  emoji="🚨", description="Signaler un membre"),
            discord.SelectOption(label="Question",     emoji="❓", description="Question générale"),
            discord.SelectOption(label="Partenariat",  emoji="🤝", description="Proposition partenariat"),
            discord.SelectOption(label="Autre",        emoji="📩", description="Autre demande"),
        ]
        super().__init__(placeholder="Sélectionne une catégorie...", options=options, custom_id="ticket_select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = interaction.client.cogs.get("Tickets")
        if cog:
            await cog._create_ticket(interaction.guild, interaction.user, self.values[0])

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

class TicketControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer", style=discord.ButtonStyle.danger,  custom_id="ticket_close")
    async def close_btn(self, i: discord.Interaction, btn: Button):
        cog = i.client.cogs.get("Tickets")
        if cog: await cog._close_ticket(i.channel, i.user, i.guild)

    @discord.ui.button(label="✋ Claim",  style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim_btn(self, i: discord.Interaction, btn: Button):
        ch = i.channel
        if not ch.name.startswith("ticket-"):
            await i.response.send_message("Pas un ticket.", ephemeral=True); return
        await ch.edit(topic=f"{ch.topic} | Pris en charge par {i.user}")
        await i.response.send_message(embed=E.success(f"Ticket pris en charge par {i.user.mention}."))


# ─── Cog ──────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ticket_counter: dict[int, int] = {}

    async def _create_ticket(self, guild: discord.Guild, user: discord.Member, category: str):
        """Crée un salon de ticket privé."""
        existing = discord.utils.find(lambda c: c.name == f"ticket-{user.name.lower()}", guild.text_channels)
        if existing:
            await existing.send(f"{user.mention} tu as déjà un ticket ouvert ici.", delete_after=5)
            return

        num = self.ticket_counter.get(guild.id, 0) + 1
        self.ticket_counter[guild.id] = num

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_guild:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        cfg = db.get_guild(guild.id)
        cat_obj = None
        if cfg.get("ticket_category"):
            cat_obj = guild.get_channel(cfg["ticket_category"])

        channel = await guild.create_text_channel(
            name=f"ticket-{user.name.lower()}",
            overwrites=overwrites,
            category=cat_obj,
            topic=f"#{num} | {category} | {user}"
        )

        e = E.base(f"🎫 Ticket #{num} — {category}")
        e.description = (
            f"Bienvenue {user.mention} !\n\n"
            f"**Catégorie :** {category}\n"
            f"Décris ton problème, l'équipe arrive dès que possible.\n\n"
            f"Clique sur **Fermer** quand c'est résolu."
        )
        await channel.send(embed=e, view=TicketControlView())
        db.save_ticket(guild.id, str(num), {
            "channel_id": channel.id,
            "user_id": user.id,
            "category": category,
            "status": "open"
        })

    async def _close_ticket(self, channel: discord.TextChannel, closer: discord.Member, guild: discord.Guild):
        """Ferme un ticket avec transcript."""
        await channel.send(embed=E.warn("Fermeture dans 5 secondes... Génération du transcript."))

        transcript = f"=== TRANSCRIPT — {channel.name} === {discord.utils.utcnow().strftime('%d/%m/%Y %H:%M')}\n\n"
        async for msg in channel.history(limit=500, oldest_first=True):
            if not msg.author.bot:
                transcript += f"[{msg.created_at.strftime('%H:%M')}] {msg.author}: {msg.content}\n"

        cfg = db.get_guild(guild.id)
        if cfg.get("log_channel"):
            log_ch = guild.get_channel(cfg["log_channel"])
            if log_ch:
                f = discord.File(fp=io.StringIO(transcript), filename=f"transcript-{channel.name}.txt")
                await log_ch.send(
                    embed=E.base("📋 Ticket fermé", f"**{channel.name}** fermé par {closer.mention}", discord.Color.red()),
                    file=f
                )
        await asyncio.sleep(5)
        await channel.delete()

    # ── /ticket create ────────────────────────────────────────────────────────

    ticket_group = app_commands.Group(name="ticket", description="Gestion des tickets")

    @ticket_group.command(name="create", description="Crée un ticket de support")
    @app_commands.describe(category="La catégorie")
    @app_commands.choices(category=[app_commands.Choice(name=c, value=c) for c in CATEGORIES])
    async def ticket_create(self, i: discord.Interaction, category: str = "Support"):
        await i.response.defer(ephemeral=True)
        await self._create_ticket(i.guild, i.user, category)
        await i.followup.send(embed=E.success("Ticket créé ! Vérifie tes salons."), ephemeral=True)

    @ticket_group.command(name="close", description="Ferme ce ticket")
    async def ticket_close(self, i: discord.Interaction):
        if not i.channel.name.startswith("ticket-"):
            await i.response.send_message(embed=E.error("Ce n'est pas un salon de ticket."), ephemeral=True); return
        await i.response.send_message(embed=E.warn("Fermeture en cours..."))
        await self._close_ticket(i.channel, i.user, i.guild)

    @ticket_group.command(name="claim", description="Prend en charge ce ticket")
    async def ticket_claim(self, i: discord.Interaction):
        if not i.channel.name.startswith("ticket-"):
            await i.response.send_message(embed=E.error("Pas un ticket."), ephemeral=True); return
        await i.channel.edit(topic=f"{i.channel.topic} | Pris en charge par {i.user}")
        await i.response.send_message(embed=E.success(f"Ticket pris en charge par {i.user.mention}."))

    @ticket_group.command(name="add", description="Ajoute un membre au ticket")
    async def ticket_add(self, i: discord.Interaction, member: discord.Member):
        await i.channel.set_permissions(member, view_channel=True, send_messages=True)
        await i.response.send_message(embed=E.success(f"{member.mention} ajouté au ticket."))

    @ticket_group.command(name="remove", description="Retire un membre du ticket")
    async def ticket_remove(self, i: discord.Interaction, member: discord.Member):
        await i.channel.set_permissions(member, overwrite=None)
        await i.response.send_message(embed=E.success(f"{member.mention} retiré du ticket."))

    @ticket_group.command(name="rename", description="Renomme le ticket")
    async def ticket_rename(self, i: discord.Interaction, name: str):
        await i.channel.edit(name=f"ticket-{name.lower().replace(' ','-')}")
        await i.response.send_message(embed=E.success(f"Ticket renommé."))

    @ticket_group.command(name="transcript", description="Génère le transcript de ce ticket")
    async def ticket_transcript(self, i: discord.Interaction):
        await i.response.defer()
        transcript = f"=== TRANSCRIPT — {i.channel.name} ===\n\n"
        async for msg in i.channel.history(limit=500, oldest_first=True):
            if not msg.author.bot:
                transcript += f"[{msg.created_at.strftime('%H:%M')}] {msg.author}: {msg.content}\n"
        f = discord.File(fp=io.StringIO(transcript), filename=f"transcript-{i.channel.name}.txt")
        await i.followup.send(file=f)

    @ticket_group.command(name="reopen", description="Réouvre un ticket fermé")
    async def ticket_reopen(self, i: discord.Interaction):
        await i.channel.set_permissions(i.guild.default_role, view_channel=False)
        await i.response.send_message(embed=E.success("Ticket réouvert."))

    @ticket_group.command(name="delete", description="Supprime définitivement ce ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_delete(self, i: discord.Interaction):
        await i.response.send_message(embed=E.warn("Suppression dans 3 secondes..."))
        await asyncio.sleep(3)
        await i.channel.delete()

    # ── /setup tickets ────────────────────────────────────────────────────────

    @app_commands.command(name="setup_tickets", description="[Admin] Crée le panneau de tickets")
    @app_commands.default_permissions(administrator=True)
    async def setup_tickets(self, i: discord.Interaction):
        e = E.base("🎫 Support — Créer un ticket",
            "Besoin d'aide ? Sélectionne une catégorie ci-dessous pour ouvrir un ticket privé.")
        await i.channel.send(embed=e, view=TicketPanelView())
        await i.response.send_message(embed=E.success("Panneau de tickets créé."), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Tickets(bot))
