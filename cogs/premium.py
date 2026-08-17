"""
Kryvoox Premium System
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

# Avantages Premium (affichés + utilisés dans les autres cogs)
PREMIUM_BENEFITS = [
    "💰 **Daily x2** — double récompense quotidienne",
    "⏱️ **Work plus rapide** — cooldown réduit de 50%",
    "🎰 **Mises plus élevées** — limites de jeux augmentées",
    "⭐ **Badge Premium** sur la rank card",
    "🌟 **XP bonus** — +20% d'XP message & vocal",
    "💎 Accès anticipé aux futures features",
]


class Premium(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /premium ───────────────────────────────────────────────

    @app_commands.command(name="premium", description="Voir ton statut Premium et les avantages")
    async def premium_status(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        is_prem = db.is_premium(t.id)
        u = db.get_user(t.id)

        e = discord.Embed(
            title="⭐ Kryvoox Premium",
            color=discord.Color.gold() if is_prem else discord.Color.dark_grey()
        )
        e.set_thumbnail(url=t.display_avatar.url)

        if is_prem:
            until = u.get("premium_until")
            if until:
                try:
                    exp = datetime.fromisoformat(until)
                    remaining = exp - datetime.utcnow()
                    days_left = max(0, remaining.days)
                    status = f"✅ **Actif** — expire dans **{days_left} jour(s)**"
                except Exception:
                    status = "✅ **Actif**"
            else:
                status = "✅ **Actif à vie** ∞"
        else:
            status = "❌ Non actif"

        e.add_field(name="Statut", value=status, inline=False)
        e.add_field(
            name="Avantages Premium",
            value="\n".join(PREMIUM_BENEFITS),
            inline=False
        )
        e.set_footer(text="Contacte un admin pour obtenir Premium")
        await i.response.send_message(embed=e)

    # ── /premium-give (admin) ──────────────────────────────────

    @app_commands.command(name="premium-give", description="[Admin] Donne le Premium à un membre")
    @app_commands.describe(
        member="Le membre",
        days="Durée en jours (0 = à vie)"
    )
    @app_commands.default_permissions(administrator=True)
    async def premium_give(self, i: discord.Interaction, member: discord.Member, days: app_commands.Range[int, 0, 3650] = 30):
        if days == 0:
            db.set_premium(member.id, days=None)
            msg = f"⭐ Premium **à vie** donné à {member.mention}"
        else:
            db.set_premium(member.id, days=days)
            msg = f"⭐ Premium donné à {member.mention} pour **{days} jours**"

        await i.response.send_message(embed=E.success(msg))

        try:
            e = discord.Embed(
                title="⭐ Tu as reçu Kryvoox Premium !",
                description="\n".join(PREMIUM_BENEFITS),
                color=discord.Color.gold()
            )
            e.set_footer(text=f"Durée : {'à vie' if days == 0 else f'{days} jours'}")
            await member.send(embed=e)
        except Exception:
            pass

    # ── /premium-remove ───────────────────────────────────────

    @app_commands.command(name="premium-remove", description="[Admin] Retire le Premium d'un membre")
    @app_commands.default_permissions(administrator=True)
    async def premium_remove(self, i: discord.Interaction, member: discord.Member):
        db.remove_premium(member.id)
        await i.response.send_message(embed=E.success(f"Premium retiré à {member.mention}."))


async def setup(bot):
    await bot.add_cog(Premium(bot))
