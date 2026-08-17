"""
Kryvoox Giveaways
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import random
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E

_active: dict[int, dict] = {}


def _parse_duration(text: str) -> int | None:
    text = text.lower().strip()
    total = 0
    parts = re.findall(r"(\d+)\s*([smhd])", text)
    if not parts:
        return None
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    for num, unit in parts:
        total += int(num) * units.get(unit, 0)
    return total if total > 0 else None


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="Participer", style=discord.ButtonStyle.success, emoji="🎉", custom_id="gw_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        gw = _active.get(self.giveaway_id)
        if not gw or gw.get("ended"):
            await interaction.response.send_message("Ce giveaway est terminé.", ephemeral=True)
            return

        uid = interaction.user.id
        if uid in gw["participants"]:
            gw["participants"].discard(uid)
            await interaction.response.send_message("Tu as quitté le giveaway.", ephemeral=True)
        else:
            gw["participants"].add(uid)
            await interaction.response.send_message("Tu participes au giveaway ! 🎉", ephemeral=True)

        try:
            msg = await interaction.channel.fetch_message(self.giveaway_id)
            embed = msg.embeds[0] if msg.embeds else None
            if embed and len(embed.fields) > 0:
                embed.set_field_at(0, name="Participants", value=str(len(gw["participants"])), inline=True)
                await msg.edit(embed=embed, view=self)
        except Exception:
            pass


class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_loop.start()

    def cog_unload(self):
        self.check_loop.cancel()

    def _build_embed(self, prize: str, winners: int, ends_at: datetime, host: discord.Member, participants: int = 0) -> discord.Embed:
        e = discord.Embed(
            title="🎉 GIVEAWAY",
            description=f"**Prix :** {prize}\n\nClique sur le bouton pour participer !",
            color=discord.Color.magenta()
        )
        e.add_field(name="Participants", value=str(participants), inline=True)
        e.add_field(name="Gagnants", value=str(winners), inline=True)
        e.add_field(name="Fin", value=f"<t:{int(ends_at.timestamp())}:R>", inline=True)
        e.set_footer(text=f"Organisé par {host.display_name}")
        e.timestamp = ends_at
        return e

    async def _end_giveaway(self, message_id: int, channel: discord.TextChannel | None = None):
        gw = _active.get(message_id)
        if not gw or gw.get("ended"):
            return
        gw["ended"] = True

        participants = list(gw["participants"])
        winners_count = min(gw["winners"], len(participants))
        winners = random.sample(participants, winners_count) if winners_count > 0 else []

        ch = channel or self.bot.get_channel(gw["channel_id"])
        if not ch:
            return

        try:
            msg = await ch.fetch_message(message_id)
        except Exception:
            msg = None

        if winners:
            mentions = ", ".join(f"<@{w}>" for w in winners)
            result = f"🏆 Gagnant(s) : {mentions}\n**Prix :** {gw['prize']}"
            color = discord.Color.green()
        else:
            mentions = None
            result = "Personne n'a participé…"
            color = discord.Color.dark_grey()

        e = discord.Embed(title="🎉 Giveaway terminé", description=result, color=color)
        e.set_footer(text=f"{len(participants)} participant(s)")

        if msg:
            try:
                await msg.edit(embed=e, view=None)
            except Exception:
                pass
            await ch.send(content=mentions, embed=e)
        else:
            await ch.send(content=mentions, embed=e)

        gw["winner_ids"] = winners

    @app_commands.command(name="giveaway", description="Lance un giveaway")
    @app_commands.describe(
        duration="Durée (ex: 1h, 30m, 2d, 1d12h)",
        winners="Nombre de gagnants",
        prize="Le prix à gagner",
        channel="Salon (optionnel)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_start(
        self,
        i: discord.Interaction,
        duration: str,
        prize: str,
        winners: app_commands.Range[int, 1, 20] = 1,
        channel: discord.TextChannel = None,
    ):
        seconds = _parse_duration(duration)
        if not seconds or seconds < 30:
            await i.response.send_message(
                embed=E.error("Durée invalide. Exemples : `30m`, `1h`, `2d`, `1d12h` (min 30s)"),
                ephemeral=True
            )
            return
        if seconds > 30 * 86400:
            await i.response.send_message(embed=E.error("Durée max : 30 jours."), ephemeral=True)
            return

        ch = channel or i.channel
        ends_at = datetime.utcnow() + timedelta(seconds=seconds)

        embed = self._build_embed(prize, winners, ends_at, i.user, 0)
        await i.response.defer(ephemeral=True)
        msg = await ch.send(embed=embed)

        view = GiveawayView(msg.id)
        await msg.edit(view=view)

        _active[msg.id] = {
            "channel_id": ch.id,
            "guild_id": i.guild.id,
            "prize": prize,
            "winners": winners,
            "ends_at": ends_at,
            "host_id": i.user.id,
            "participants": set(),
            "ended": False,
            "winner_ids": [],
        }

        await i.followup.send(embed=E.success(f"Giveaway lancé dans {ch.mention} !"), ephemeral=True)

    @app_commands.command(name="gend", description="Termine un giveaway plus tôt")
    @app_commands.describe(message_id="ID du message du giveaway")
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_end(self, i: discord.Interaction, message_id: str):
        try:
            mid = int(message_id)
        except ValueError:
            await i.response.send_message(embed=E.error("ID invalide."), ephemeral=True)
            return
        if mid not in _active:
            await i.response.send_message(embed=E.error("Giveaway introuvable ou déjà terminé."), ephemeral=True)
            return
        await i.response.defer(ephemeral=True)
        await self._end_giveaway(mid)
        await i.followup.send(embed=E.success("Giveaway terminé."), ephemeral=True)

    @app_commands.command(name="greroll", description="Retire un nouveau gagnant pour un giveaway")
    @app_commands.describe(message_id="ID du message du giveaway")
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_reroll(self, i: discord.Interaction, message_id: str):
        try:
            mid = int(message_id)
        except ValueError:
            await i.response.send_message(embed=E.error("ID invalide."), ephemeral=True)
            return
        gw = _active.get(mid)
        if not gw:
            await i.response.send_message(embed=E.error("Giveaway introuvable."), ephemeral=True)
            return
        if not gw.get("ended"):
            await i.response.send_message(embed=E.error("Le giveaway n'est pas encore terminé. Utilise `/gend`."), ephemeral=True)
            return

        pool = [p for p in gw["participants"] if p not in gw.get("winner_ids", [])]
        if not pool:
            pool = list(gw["participants"])
        if not pool:
            await i.response.send_message(embed=E.error("Aucun participant."), ephemeral=True)
            return

        new_winner = random.choice(pool)
        gw.setdefault("winner_ids", []).append(new_winner)

        e = discord.Embed(
            title="🎉 Nouveau gagnant !",
            description=f"🏆 <@{new_winner}> gagne **{gw['prize']}**",
            color=discord.Color.gold()
        )
        await i.response.send_message(content=f"<@{new_winner}>", embed=e)

    @tasks.loop(seconds=20)
    async def check_loop(self):
        now = datetime.utcnow()
        to_end = [mid for mid, gw in list(_active.items()) if not gw.get("ended") and gw["ends_at"] <= now]
        for mid in to_end:
            try:
                await self._end_giveaway(mid)
            except Exception:
                pass

    @check_loop.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Giveaways(bot))
