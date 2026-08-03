import discord
from discord import app_commands
from discord.ext import commands
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E

class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_voice_channel(self, member: discord.Member):
        if not member.voice or not member.voice.channel:
            return None
        return member.voice.channel

    voice_group = app_commands.Group(name="voice", description="Gestion des salons vocaux")

    @voice_group.command(name="lock", description="Verrouille ton salon vocal")
    async def voice_lock(self, i: discord.Interaction):
        ch = self._get_voice_channel(i.user)
        if not ch:
            await i.response.send_message(embed=E.error("Tu n'es pas dans un salon vocal."), ephemeral=True); return
        await ch.set_permissions(i.guild.default_role, connect=False)
        await i.response.send_message(embed=E.success(f"🔒 **{ch.name}** verrouillé."))

    @voice_group.command(name="unlock", description="Déverrouille ton salon vocal")
    async def voice_unlock(self, i: discord.Interaction):
        ch = self._get_voice_channel(i.user)
        if not ch:
            await i.response.send_message(embed=E.error("Tu n'es pas dans un salon vocal."), ephemeral=True); return
        await ch.set_permissions(i.guild.default_role, connect=None)
        await i.response.send_message(embed=E.success(f"🔓 **{ch.name}** déverrouillé."))

    @voice_group.command(name="rename", description="Renomme ton salon vocal")
    async def voice_rename(self, i: discord.Interaction, name: str):
        ch = self._get_voice_channel(i.user)
        if not ch:
            await i.response.send_message(embed=E.error("Tu n'es pas dans un salon vocal."), ephemeral=True); return
        old = ch.name
        await ch.edit(name=name)
        await i.response.send_message(embed=E.success(f"**{old}** → **{name}**"))

    @voice_group.command(name="limit", description="Définit la limite d'utilisateurs")
    @app_commands.describe(limit="0 = illimité, max 99")
    async def voice_limit(self, i: discord.Interaction, limit: int):
        ch = self._get_voice_channel(i.user)
        if not ch:
            await i.response.send_message(embed=E.error("Tu n'es pas dans un salon vocal."), ephemeral=True); return
        await ch.edit(user_limit=max(0, min(limit, 99)))
        msg = f"Limite supprimée." if limit == 0 else f"Limite → **{limit} utilisateurs**."
        await i.response.send_message(embed=E.success(msg))

    @voice_group.command(name="bitrate", description="Définit le bitrate (kbps)")
    @app_commands.describe(kbps="Entre 8 et 384")
    async def voice_bitrate(self, i: discord.Interaction, kbps: int):
        ch = self._get_voice_channel(i.user)
        if not ch:
            await i.response.send_message(embed=E.error("Tu n'es pas dans un salon vocal."), ephemeral=True); return
        kbps = max(8, min(kbps, 384))
        await ch.edit(bitrate=kbps * 1000)
        await i.response.send_message(embed=E.success(f"Bitrate → **{kbps} kbps**."))


async def setup(bot):
    await bot.add_cog(Voice(bot))
