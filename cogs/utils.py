import discord
from discord import app_commands
from discord.ext import commands
import asyncio, aiohttp, time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E

class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /weather ──────────────────────────────────────────────────────────────

    @app_commands.command(name="weather", description="Météo d'une ville")
    @app_commands.describe(city="La ville (ex: Paris, Abidjan)")
    async def weather(self, i: discord.Interaction, city: str):
        await i.response.defer()
        try:
            url = f"https://wttr.in/{city.replace(' ', '+')}?format=j1"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        await i.followup.send(embed=E.error(f"Ville **{city}** introuvable.")); return
                    data = await r.json()

            current = data["current_condition"][0]
            area    = data["nearest_area"][0]
            city_name = area["areaName"][0]["value"]
            country   = area["country"][0]["value"]

            temp_c   = current["temp_C"]
            feels    = current["FeelsLikeC"]
            humidity = current["humidity"]
            desc     = current["weatherDesc"][0]["value"]
            wind     = current["windspeedKmph"]

            icons = {"Sunny":"☀️","Clear":"🌙","Cloudy":"☁️","Rain":"🌧️","Snow":"❄️","Thunder":"⛈️","Fog":"🌫️","Mist":"🌫️"}
            icon = next((v for k,v in icons.items() if k.lower() in desc.lower()), "🌡️")

            e = E.base(f"{icon} Météo — {city_name}, {country}")
            e.add_field(name="🌡️ Température", value=f"**{temp_c}°C** (ressenti {feels}°C)")
            e.add_field(name="💧 Humidité",    value=f"**{humidity}%**")
            e.add_field(name="💨 Vent",        value=f"**{wind} km/h**")
            e.add_field(name="📋 Condition",   value=desc)
            await i.followup.send(embed=e)
        except Exception as ex:
            await i.followup.send(embed=E.error(f"Erreur météo : {ex}"))

    # ── /calculator ───────────────────────────────────────────────────────────

    @app_commands.command(name="calculator", description="Calcule une expression mathématique")
    @app_commands.describe(expression="L'expression (ex: 2 + 2 * 10 / 3)")
    async def calculator(self, i: discord.Interaction, expression: str):
        try:
            # Sécurisé : on autorise que les caractères mathématiques
            clean = expression.replace(" ", "")
            allowed = set("0123456789+-*/.()%")
            if not all(c in allowed for c in clean):
                await i.response.send_message(embed=E.error("Expression invalide. Utilise uniquement des chiffres et opérateurs."), ephemeral=True); return
            result = eval(clean)
            await i.response.send_message(embed=E.success(f"`{expression}` = **{result}**", "🧮 Calculatrice"))
        except ZeroDivisionError:
            await i.response.send_message(embed=E.error("Division par zéro."), ephemeral=True)
        except:
            await i.response.send_message(embed=E.error("Expression invalide."), ephemeral=True)

    # ── /reminder ─────────────────────────────────────────────────────────────

    @app_commands.command(name="reminder", description="Crée un rappel")
    @app_commands.describe(duration="Durée (ex: 10m, 1h, 30s)", message="Le rappel")
    async def reminder(self, i: discord.Interaction, duration: str, message: str):
        import re
        m = re.match(r"(\d+)([smhd])", duration)
        if not m:
            await i.response.send_message(embed=E.error("Format : `30s`, `10m`, `1h`, `1d`"), ephemeral=True); return
        val, unit = int(m.group(1)), m.group(2)
        secs = val * {"s":1,"m":60,"h":3600,"d":86400}[unit]
        if secs > 7 * 86400:
            await i.response.send_message(embed=E.error("Max 7 jours."), ephemeral=True); return
        display = f"{val}{'s' if unit=='s' else 'min' if unit=='m' else 'h' if unit=='h' else 'j'}"
        await i.response.send_message(embed=E.success(f"⏰ Rappel dans **{display}** : *{message}*"))

        await asyncio.sleep(secs)
        try:
            await i.user.send(embed=E.base("⏰ Rappel !", f"*{message}*\n\nDans : **#{i.channel.name}**"))
        except:
            await i.channel.send(f"⏰ {i.user.mention} — rappel : **{message}**")

    # ── /timer ────────────────────────────────────────────────────────────────

    @app_commands.command(name="timer", description="Lance un compte à rebours")
    @app_commands.describe(duration="Durée (ex: 30s, 5m)", label="Label du timer")
    async def timer(self, i: discord.Interaction, duration: str, label: str = "Timer"):
        import re
        m = re.match(r"(\d+)([smh])", duration)
        if not m:
            await i.response.send_message(embed=E.error("Format : `30s`, `5m`, `1h`"), ephemeral=True); return
        val, unit = int(m.group(1)), m.group(2)
        secs = val * {"s":1,"m":60,"h":3600}[unit]
        if secs > 3600:
            await i.response.send_message(embed=E.error("Max 1h pour un timer."), ephemeral=True); return

        end_ts = int(time.time()) + secs
        await i.response.send_message(embed=E.base(f"⏱️ {label}", f"Se termine <t:{end_ts}:R> (<t:{end_ts}:T>)"))
        await asyncio.sleep(secs)
        await i.channel.send(f"⏱️ {i.user.mention} — **{label}** terminé !")

    # ── /timestamp ────────────────────────────────────────────────────────────

    @app_commands.command(name="timestamp", description="Convertit une date en timestamp Discord")
    @app_commands.describe(date="Format : YYYY-MM-DD HH:MM (ex: 2025-12-31 20:00)")
    async def timestamp(self, i: discord.Interaction, date: str):
        from datetime import datetime
        try:
            dt = datetime.strptime(date, "%Y-%m-%d %H:%M")
            ts = int(dt.timestamp())
            e = E.base("🕐 Timestamp Discord")
            formats = [
                ("Court", f"<t:{ts}:d>",  f"`<t:{ts}:d>`"),
                ("Long",  f"<t:{ts}:D>",  f"`<t:{ts}:D>`"),
                ("Heure", f"<t:{ts}:T>",  f"`<t:{ts}:T>`"),
                ("Relatif", f"<t:{ts}:R>", f"`<t:{ts}:R>`"),
                ("Complet", f"<t:{ts}:F>", f"`<t:{ts}:F>`"),
            ]
            for name, preview, code in formats:
                e.add_field(name=name, value=f"{preview}\n{code}", inline=True)
            await i.response.send_message(embed=e)
        except:
            await i.response.send_message(embed=E.error("Format invalide. Exemple : `2025-12-31 20:00`"), ephemeral=True)

    # ── /qrcode ───────────────────────────────────────────────────────────────

    @app_commands.command(name="qrcode", description="Génère un QR code")
    @app_commands.describe(content="Le contenu (URL, texte...)")
    async def qrcode(self, i: discord.Interaction, content: str):
        from urllib.parse import quote
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(content)}"
        e = E.base("📱 QR Code")
        e.set_image(url=qr_url)
        e.add_field(name="Contenu", value=f"`{content[:200]}`")
        await i.response.send_message(embed=e)

    # ── /shorturl ─────────────────────────────────────────────────────────────

    @app_commands.command(name="shorturl", description="Raccourcit une URL")
    @app_commands.describe(url="L'URL à raccourcir")
    async def shorturl(self, i: discord.Interaction, url: str):
        await i.response.defer()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://tinyurl.com/api-create.php?url={url}",
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    short = await r.text()
            e = E.base("🔗 URL raccourcie")
            e.add_field(name="Original", value=f"`{url[:200]}`", inline=False)
            e.add_field(name="Courte",   value=short, inline=False)
            await i.followup.send(embed=e)
        except:
            await i.followup.send(embed=E.error("Impossible de raccourcir cette URL."))


async def setup(bot):
    await bot.add_cog(Utils(bot))
