"""
Kryvoox Premium System + Renouvellement
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button, Select
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

# Packs de renouvellement (jours → prix en coins)
PREMIUM_PACKS = {
    "7":  {"days": 7,  "price": 2500,  "label": "7 jours",  "emoji": "📅"},
    "30": {"days": 30, "price": 8000,  "label": "30 jours", "emoji": "📆"},
    "90": {"days": 90, "price": 20000, "label": "90 jours", "emoji": "🌟"},
}


class BuyPremiumView(View):
    def __init__(self):
        super().__init__(timeout=120)
        options = []
        for key, pack in PREMIUM_PACKS.items():
            options.append(discord.SelectOption(
                label=f"{pack['label']} — {pack['price']:,} coins",
                value=key,
                emoji=pack["emoji"],
                description=f"+{pack['days']} jours de Premium",
            ))
        select = Select(placeholder="Choisir un pack…", options=options, custom_id="premium_buy_select")
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        key = self.children[0].values[0]
        pack = PREMIUM_PACKS[key]
        u = db.get_user(interaction.user.id)

        if u["coins"] < pack["price"]:
            await interaction.response.send_message(
                embed=E.error(
                    f"Pas assez de coins.\n"
                    f"Prix : **{pack['price']:,}** 🪙 — Solde : **{u['coins']:,}**"
                ),
                ephemeral=True,
            )
            return

        # Lifetime check
        if u.get("premium") and not u.get("premium_until"):
            await interaction.response.send_message(
                embed=E.info("Tu as déjà le Premium **à vie**. Pas besoin d'acheter."),
                ephemeral=True,
            )
            return

        was_active = db.is_premium(interaction.user.id)

        # Débite
        u["coins"] -= pack["price"]
        db.save_user(interaction.user.id, u)

        # Renouvelle (empile si déjà actif)
        new_exp = db.renew_premium(interaction.user.id, pack["days"])

        action = "prolongé" if was_active else "activé"
        e = discord.Embed(
            title="⭐ Premium " + ("renouvelé" if was_active else "acheté") + " !",
            description=(
                f"Tu as **{action}** le Premium pour **{pack['days']} jours**.\n"
                f"Coût : **{pack['price']:,} coins** 🪙\n"
                f"Nouveau solde : **{u['coins']:,}**\n\n"
                f"Expiration : <t:{int(new_exp.timestamp())}:F>"
            ),
            color=discord.Color.gold(),
        )
        e.add_field(name="Avantages", value="\n".join(PREMIUM_BENEFITS[:4]) + "\n…", inline=False)
        await interaction.response.edit_message(embed=e, view=None)


class Premium(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.premium_loop.start()

    def cog_unload(self):
        self.premium_loop.cancel()

    # ── /premium ────────────────────────────────────────────────

    @app_commands.command(name="premium", description="Voir ton statut Premium, les avantages et les packs")
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
                    status = (
                        f"✅ **Actif** — expire dans **{days_left}j {hours_left}h**\n"
                        f"📅 Fin : <t:{int(exp.timestamp())}:F>"
                    )
                except Exception:
                    status = "✅ **Actif**"
            else:
                status = "✅ **Actif à vie** ∞"
        else:
            status = "❌ Non actif"

        e.add_field(name="Statut", value=status, inline=False)
        e.add_field(name="Avantages", value="\n".join(PREMIUM_BENEFITS), inline=False)

        packs_txt = "\n".join(
            f"{p['emoji']} **{p['label']}** — `{p['price']:,}` coins"
            for p in PREMIUM_PACKS.values()
        )
        e.add_field(name="Packs de renouvellement", value=packs_txt, inline=False)
        e.set_footer(text="/premium-buy pour acheter ou renouveler • Admin : /premium-renew")
        await i.response.send_message(embed=e)

    # ── /premium-buy (utilisateur) ────────────────────────────────

    @app_commands.command(name="premium-buy", description="Acheter ou renouveler le Premium avec tes coins")
    async def premium_buy(self, i: discord.Interaction):
        u = db.get_user(i.user.id)

        if u.get("premium") and not u.get("premium_until"):
            await i.response.send_message(
                embed=E.info("Tu as déjà le Premium **à vie**. Rien à acheter."),
                ephemeral=True,
            )
            return

        e = discord.Embed(
            title="🛒 Acheter / Renouveler Premium",
            description=(
                f"Solde actuel : **{u['coins']:,}** 🪙\n\n"
                "Choisis un pack ci-dessous.\n"
                "Si tu as déjà le Premium, les jours s'**ajoutent** à ta date actuelle."
            ),
            color=discord.Color.gold(),
        )
        for p in PREMIUM_PACKS.values():
            e.add_field(
                name=f"{p['emoji']} {p['label']}",
                value=f"**{p['price']:,}** coins",
                inline=True,
            )
        await i.response.send_message(embed=e, view=BuyPremiumView(), ephemeral=True)

    # ── /premium-give (admin) ──────────────────────────────────

    @app_commands.command(name="premium-give", description="[Admin] Donne le Premium (remplace la durée)")
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
                color=discord.Color.gold(),
            )
            e.set_footer(text=f"Durée : {'à vie' if days == 0 else f'{days} jours'}")
            await member.send(embed=e)
        except Exception:
            pass

    # ── /premium-renew (admin — empile) ────────────────────────

    @app_commands.command(name="premium-renew", description="[Admin] Renouvelle / prolonge le Premium (empile les jours)")
    @app_commands.describe(member="Le membre", days="Jours à ajouter")
    @app_commands.default_permissions(administrator=True)
    async def premium_renew(self, i: discord.Interaction, member: discord.Member, days: app_commands.Range[int, 1, 3650] = 30):
        u = db.get_user(member.id)
        was_active = db.is_premium(member.id)

        if was_active and not u.get("premium_until"):
            await i.response.send_message(
                embed=E.info(f"{member.mention} a déjà le Premium **à vie**."),
                ephemeral=True,
            )
            return

        new_exp = db.renew_premium(member.id, days)
        if new_exp is None:
            await i.response.send_message(embed=E.info("Premium à vie — rien à faire."), ephemeral=True)
            return

        action = "prolongé" if was_active else "renouvelé / réactivé"
        await i.response.send_message(embed=E.success(
            f"⭐ Premium **{action}** pour {member.mention}\n"
            f"+**{days} jours**\n"
            f"Nouvelle expiration : <t:{int(new_exp.timestamp())}:F>"
        ))

        try:
            dm = discord.Embed(
                title="🔄 Premium renouvelé !",
                description=(
                    f"Ton Kryvoox Premium a été **{action}** de **{days} jours**.\n\n"
                    f"Nouvelle date de fin : <t:{int(new_exp.timestamp())}:F>"
                ),
                color=discord.Color.gold(),
            )
            await member.send(embed=dm)
        except Exception:
            pass

    # ── /premium-remove ────────────────────────────────────

    @app_commands.command(name="premium-remove", description="[Admin] Retire le Premium d'un membre")
    @app_commands.default_permissions(administrator=True)
    async def premium_remove(self, i: discord.Interaction, member: discord.Member):
        db.remove_premium(member.id)
        await i.response.send_message(embed=E.success(f"Premium retiré à {member.mention}."))

    # ── Boucle rappels + expiration ────────────────────────────────

    @tasks.loop(hours=6)
    async def premium_loop(self):
        # 1. Expirés
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
                        "Utilise `/premium-buy` pour le **renouveler** avec tes coins."
                    ),
                    color=discord.Color.orange(),
                )
                await user.send(embed=e)
            except Exception:
                pass

        # 2. Rappels 3j / 1j
        expiring = db.get_expiring_premiums(within_days=3)
        for uid, until_str, days_left, reminded in expiring:
            try:
                if days_left <= 1:
                    tag = "1d"
                    title = "⚠️ Premium expire demain !"
                    body = (
                        f"Ton Kryvoox Premium expire dans **moins de 24h**.\n"
                        f"Fin : <t:{int(datetime.fromisoformat(until_str).timestamp())}:F>\n\n"
                        "Renouvelle avec `/premium-buy` pour garder tes avantages."
                    )
                else:
                    tag = "3d"
                    title = "📅 Premium expire bientôt"
                    body = (
                        f"Ton Kryvoox Premium expire dans **{days_left} jours**.\n"
                        f"Fin : <t:{int(datetime.fromisoformat(until_str).timestamp())}:F>\n\n"
                        "Pense à le renouveler avec `/premium-buy` ⭐"
                    )

                if reminded == tag or (reminded == "1d" and tag == "3d"):
                    continue
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
