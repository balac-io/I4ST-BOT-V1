"""
Kryvoox Premium System + Renouvellement
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

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
        self.premium_loop.start()

    def cog_unload(self):
        self.premium_loop.cancel()

    # ── /premium ────────────────────────────────────────────────

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
                    hours_left = max(0, remaining.seconds // 3600)
                    status = f"✅ **Actif** — expire dans **{days_left}j {hours_left}h**\n📅 Fin : <t:{int(exp.timestamp())}:F>"
                except Exception:
                    status = "✅ **Actif**"
            else:
                status = "✅ **Actif à vie** ∞"
        else:
            status = "❌ Non actif\n🔄 Demande un admin pour un renouvellement"

        e.add_field(name="Statut", value=status, inline=False)
        e.add_field(name="Avantages Premium", value="\n".join(PREMIUM_BENEFITS), inline=False)
        e.set_footer(text="/premium-renew pour prolonger • Contacte un admin")
        await i.response.send_message(embed=e)

    # ── /premium-give ──────────────────────────────────────────

    @app_commands.command(name="premium-give", description="[Admin] Donne le Premium à un membre (remplace la durée)")
    @app_commands.describe(member="Le membre", days="Durée en jours (0 = à vie)")
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

    # ── /premium-renew (RENOUVELLEMENT) ─────────────────────────

    @app_commands.command(name="premium-renew", description="[Admin] Renouvelle / prolonge le Premium (empile les jours)")
    @app_commands.describe(
        member="Le membre",
        days="Jours à ajouter (s'ajoutent à la date actuelle si encore actif)"
    )
    @app_commands.default_permissions(administrator=True)
    async def premium_renew(self, i: discord.Interaction, member: discord.Member, days: app_commands.Range[int, 1, 3650] = 30):
        u = db.get_user(member.id)
        was_active = db.is_premium(member.id)
        old_until = u.get("premium_until")

        # Lifetime ?
        if was_active and not old_until:
            await i.response.send_message(
                embed=E.info(f"{member.mention} a déjà le Premium **à vie**. Pas besoin de renouveler."),
                ephemeral=True
            )
            return

        new_exp = db.renew_premium(member.id, days)

        if new_exp is None:
            await i.response.send_message(embed=E.info("Premium à vie — rien à faire."), ephemeral=True)
            return

        action = "prolongé" if was_active else "renouvelé / réactivé"
        e = E.success(
            f"⭐ Premium **{action}** pour {member.mention}\n"
            f"+**{days} jours**\n"
            f"Nouvelle expiration : <t:{int(new_exp.timestamp())}:F>"
        )
        await i.response.send_message(embed=e)

        try:
            dm = discord.Embed(
                title="🔄 Premium renouvelé !",
                description=(
                    f"Ton Kryvoox Premium a été **{action}** de **{days} jours**.\n\n"
                    f"Nouvelle date de fin : <t:{int(new_exp.timestamp())}:F>"
                ),
                color=discord.Color.gold()
            )
            dm.add_field(name="Avantages", value="\n".join(PREMIUM_BENEFITS[:3]) + "\n…", inline=False)
            await member.send(embed=dm)
        except Exception:
            pass

    # ── /premium-remove ─────────────────────────────────────

    @app_commands.command(name="premium-remove", description="[Admin] Retire le Premium d'un membre")
    @app_commands.default_permissions(administrator=True)
    async def premium_remove(self, i: discord.Interaction, member: discord.Member):
        db.remove_premium(member.id)
        await i.response.send_message(embed=E.success(f"Premium retiré à {member.mention}."))

    # ── Boucle de renouvellement / rappels / expiration ───────────────

    @tasks.loop(hours=6)
    async def premium_loop(self):
        """Toutes les 6h : rappels d'expiration + désactivation des expirés."""
        # 1. Désactiver les expirés
        expired = db.get_expired_premiums()
        for uid in expired:
            db.remove_premium(int(uid))
            try:
                user = await self.bot.fetch_user(int(uid))
                e = discord.Embed(
                    title="⏰ Premium expiré",
                    description=(
                        "Ton **Kryvoox Premium** a expiré.\n"
                        "Tu as perdu les avantages (daily x2, XP bonus, etc.).\n\n"
                        "Contacte un admin pour le **renouveler** avec `/premium-renew`."
                    ),
                    color=discord.Color.orange()
                )
                await user.send(embed=e)
            except Exception:
                pass

        # 2. Rappels (3 jours et 1 jour)
        expiring = db.get_expiring_premiums(within_days=3)
        for uid, until_str, days_left, reminded in expiring:
            try:
                # Déterminer le tag de rappel
                if days_left <= 1:
                    tag = "1d"
                    title = "⚠️ Premium expire demain !"
                    body = (
                        f"Ton Kryvoox Premium expire dans **moins de 24h**.\n"
                        f"Fin : <t:{int(datetime.fromisoformat(until_str).timestamp())}:F>\n\n"
                        "Demande un admin de le **renouveler** avec `/premium-renew`."
                    )
                else:
                    tag = "3d"
                    title = "📅 Premium expire bientôt"
                    body = (
                        f"Ton Kryvoox Premium expire dans **{days_left} jours**.\n"
                        f"Fin : <t:{int(datetime.fromisoformat(until_str).timestamp())}:F>\n\n"
                        "Pense à le renouveler pour garder tes avantages ⭐"
                    )

                # Éviter les doubles rappels
                if reminded == tag or (reminded == "1d" and tag == "3d"):
                    continue
                # Si déjà rappelé 3d et on est à 1d, on envoie quand même le 1d
                if reminded == "3d" and tag == "3d":
                    continue

                user = await self.bot.fetch_user(int(uid))
                e = discord.Embed(title=title, description=body, color=discord.Color.gold())
                await user.send(embed=e)
                db.mark_premium_reminded(int(uid), tag)
            except Exception:
                pass

    @premium_loop.before_loop
    async def before_premium_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Premium(bot))
