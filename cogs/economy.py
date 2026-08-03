import discord
from discord import app_commands
from discord.ext import commands
from datetime import date, datetime
import random
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

DAILY_AMOUNT = 200
WORK_MIN, WORK_MAX = 50, 300
ROB_CHANCE = 0.45
ROB_MIN, ROB_MAX = 0.05, 0.25   # % du solde volé

WORK_MESSAGES = [
    "Tu as livré des pizzas 🍕", "Tu as codé toute la nuit 💻",
    "Tu as vendu des NFTs à des pigeons 🐦", "Tu as été garde du corps de Kryvoox 🤖",
    "Tu as traduit des manuels IKEA 📦", "Tu as streamer 12h de suite 🎮",
    "Tu as présenté la météo 🌤️", "Tu as joué de la guitare dans le métro 🎸",
]

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /balance ──────────────────────────────────────────────────────────────

    @app_commands.command(name="balance", description="Voir ton solde ou celui d'un membre")
    @app_commands.describe(member="Le membre (optionnel)")
    async def balance(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        u = db.get_user(t.id)
        e = E.base(f"💰 Solde — {t.display_name}", color=discord.Color.gold())
        e.set_thumbnail(url=t.display_avatar.url)
        e.add_field(name="👛 Portefeuille", value=f"**{u['coins']}** 🪙")
        e.add_field(name="🏦 Banque",       value=f"**{u['bank']}** 🪙")
        e.add_field(name="💎 Total",        value=f"**{u['coins'] + u['bank']}** 🪙")
        await i.response.send_message(embed=e)

    # ── /daily ────────────────────────────────────────────────────────────────

    @app_commands.command(name="daily", description="Récompense quotidienne")
    async def daily(self, i: discord.Interaction):
        u = db.get_user(i.user.id)
        today = str(date.today())
        if u.get("last_daily") == today:
            await i.response.send_message(embed=E.error("Tu as déjà réclamé ta récompense aujourd'hui. Reviens demain !"), ephemeral=True)
            return
        u["coins"] += DAILY_AMOUNT
        u["last_daily"] = today
        db.save_user(i.user.id, u)
        await i.response.send_message(embed=E.success(
            f"{i.user.mention} a reçu **{DAILY_AMOUNT} coins** 🪙\nNouveau solde : **{u['coins']} coins**",
            "🎁 Daily Reward"
        ))

    # ── /work ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="work", description="Travaille pour gagner des coins")
    async def work(self, i: discord.Interaction):
        u = db.get_user(i.user.id)
        now = datetime.now()
        last = u.get("last_work")
        if last:
            elapsed = (now - datetime.fromisoformat(last)).total_seconds()
            if elapsed < 3600:
                remaining = int(3600 - elapsed)
                m, s = divmod(remaining, 60)
                await i.response.send_message(embed=E.error(f"Tu es épuisé. Repose-toi encore **{m}min {s}s**."), ephemeral=True)
                return
        earned = random.randint(WORK_MIN, WORK_MAX)
        job = random.choice(WORK_MESSAGES)
        u["coins"] += earned
        u["last_work"] = now.isoformat()
        db.save_user(i.user.id, u)
        await i.response.send_message(embed=E.success(
            f"{job}\nTu as gagné **{earned} coins** 🪙\nSolde : **{u['coins']} coins**",
            "💼 Travail"
        ))

    # ── /pay ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="pay", description="Envoie des coins à un membre")
    @app_commands.describe(member="Le destinataire", amount="Le montant")
    async def pay(self, i: discord.Interaction, member: discord.Member, amount: int):
        if member == i.user:
            await i.response.send_message(embed=E.error("Tu ne peux pas te payer toi-même."), ephemeral=True); return
        if amount <= 0:
            await i.response.send_message(embed=E.error("Montant invalide."), ephemeral=True); return
        src = db.get_user(i.user.id)
        if src["coins"] < amount:
            await i.response.send_message(embed=E.error(f"Solde insuffisant. Tu as **{src['coins']} coins**."), ephemeral=True); return
        src["coins"] -= amount
        dst = db.get_user(member.id)
        dst["coins"] += amount
        db.save_user(i.user.id, src)
        db.save_user(member.id, dst)
        await i.response.send_message(embed=E.success(
            f"{i.user.mention} a envoyé **{amount} coins** 🪙 à {member.mention}."
        ))

    # ── /deposit ──────────────────────────────────────────────────────────────

    @app_commands.command(name="deposit", description="Dépose des coins en banque")
    @app_commands.describe(amount="Montant (ou 'all')")
    async def deposit(self, i: discord.Interaction, amount: str = "all"):
        u = db.get_user(i.user.id)
        n = u["coins"] if amount.lower() == "all" else int(amount)
        if n <= 0 or n > u["coins"]:
            await i.response.send_message(embed=E.error(f"Montant invalide. Solde : **{u['coins']} coins**"), ephemeral=True); return
        u["coins"] -= n
        u["bank"]  += n
        db.save_user(i.user.id, u)
        await i.response.send_message(embed=E.success(f"**{n} coins** déposés en banque 🏦\nBanque : **{u['bank']} coins**"))

    # ── /withdraw ─────────────────────────────────────────────────────────────

    @app_commands.command(name="withdraw", description="Retire des coins de la banque")
    @app_commands.describe(amount="Montant (ou 'all')")
    async def withdraw(self, i: discord.Interaction, amount: str = "all"):
        u = db.get_user(i.user.id)
        n = u["bank"] if amount.lower() == "all" else int(amount)
        if n <= 0 or n > u["bank"]:
            await i.response.send_message(embed=E.error(f"Montant invalide. Banque : **{u['bank']} coins**"), ephemeral=True); return
        u["bank"]  -= n
        u["coins"] += n
        db.save_user(i.user.id, u)
        await i.response.send_message(embed=E.success(f"**{n} coins** retirés 👛\nPortefeuille : **{u['coins']} coins**"))

    # ── /rob ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="rob", description="Tente de voler un membre (risqué !)")
    async def rob(self, i: discord.Interaction, member: discord.Member):
        if member == i.user:
            await i.response.send_message(embed=E.error("Voler toi-même... audacieux."), ephemeral=True); return
        src = db.get_user(i.user.id)
        tgt = db.get_user(member.id)
        if tgt["coins"] < 100:
            await i.response.send_message(embed=E.error(f"{member.display_name} est trop fauché pour valoir le coup.")); return
        if random.random() < ROB_CHANCE:
            pct = random.uniform(ROB_MIN, ROB_MAX)
            stolen = int(tgt["coins"] * pct)
            tgt["coins"] -= stolen
            src["coins"] += stolen
            db.save_user(i.user.id, src)
            db.save_user(member.id, tgt)
            await i.response.send_message(embed=E.success(
                f"Tu as volé **{stolen} coins** 🪙 à {member.mention} !\nTon solde : **{src['coins']} coins**", "🦹 Vol réussi"
            ))
        else:
            fine = random.randint(50, 200)
            src["coins"] = max(0, src["coins"] - fine)
            db.save_user(i.user.id, src)
            await i.response.send_message(embed=E.error(
                f"Tu t'es fait attraper ! Amende : **{fine} coins** 🪙\nSolde : **{src['coins']} coins**", "🚨 Vol raté"
            ))

    # ── /leaderboard ──────────────────────────────────────────────────────────

    @app_commands.command(name="leaderboard", description="Classement des plus riches")
    async def leaderboard(self, i: discord.Interaction):
        top = db.get_leaderboard_economy()
        medals = ["🥇","🥈","🥉"]
        lines = []
        for idx, (uid, data) in enumerate(top):
            try:
                u = await self.bot.fetch_user(int(uid))
                name = u.display_name
            except:
                name = f"User#{uid[:4]}"
            medal = medals[idx] if idx < 3 else f"`{idx+1}.`"
            total = data.get("coins",0) + data.get("bank",0)
            lines.append(f"{medal} **{name}** — {total} coins 🪙")
        await i.response.send_message(embed=E.base("🏆 Classement — Économie", "\n".join(lines) or "Aucune donnée.", discord.Color.gold()))

    # ── /give ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="give", description="[Admin] Donne des coins à un membre")
    @app_commands.default_permissions(administrator=True)
    async def give(self, i: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await i.response.send_message(embed=E.error("Montant invalide."), ephemeral=True); return
        u = db.get_user(member.id)
        u["coins"] += amount
        db.save_user(member.id, u)
        await i.response.send_message(embed=E.success(f"**+{amount} coins** donnés à {member.mention}. Solde : **{u['coins']} coins**"))

    # ── /shop ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="shop", description="Voir la boutique du serveur")
    async def shop(self, i: discord.Interaction):
        cfg = db.get_guild(i.guild.id)
        items = cfg.get("shop", {})
        if not items:
            await i.response.send_message(embed=E.info("La boutique est vide. Un admin peut ajouter des items.")); return
        lines = [f"**{v['name']}** — `{k}` — {v['price']} coins 🪙\n└ {v['desc']}" for k, v in items.items()]
        await i.response.send_message(embed=E.base("🛒 Boutique", "\n\n".join(lines), discord.Color.blue()))

    # ── /buy ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="buy", description="Achète un item de la boutique")
    @app_commands.describe(item_id="L'ID de l'item")
    async def buy(self, i: discord.Interaction, item_id: str):
        cfg = db.get_guild(i.guild.id)
        item = cfg.get("shop", {}).get(item_id)
        if not item:
            await i.response.send_message(embed=E.error(f"Item `{item_id}` introuvable. Voir `/shop`."), ephemeral=True); return
        u = db.get_user(i.user.id)
        if u["coins"] < item["price"]:
            await i.response.send_message(embed=E.error(f"Pas assez de coins. Prix : {item['price']} — Solde : {u['coins']}"), ephemeral=True); return
        u["coins"] -= item["price"]
        u.setdefault("inventory", []).append(item_id)
        db.save_user(i.user.id, u)
        if item.get("role_id"):
            role = i.guild.get_role(item["role_id"])
            if role:
                await i.user.add_roles(role)
        await i.response.send_message(embed=E.success(f"Tu as acheté **{item['name']}** pour **{item['price']} coins** 🪙"))

    # ── /sell ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="sell", description="Vend un item de ton inventaire")
    @app_commands.describe(item_id="L'ID de l'item")
    async def sell(self, i: discord.Interaction, item_id: str):
        u = db.get_user(i.user.id)
        inv = u.get("inventory", [])
        if item_id not in inv:
            await i.response.send_message(embed=E.error(f"Tu ne possèdes pas `{item_id}`."), ephemeral=True); return
        cfg = db.get_guild(i.guild.id)
        item = cfg.get("shop", {}).get(item_id, {})
        refund = int(item.get("price", 0) * 0.5)
        inv.remove(item_id)
        u["coins"] += refund
        db.save_user(i.user.id, u)
        await i.response.send_message(embed=E.success(f"Item vendu pour **{refund} coins** 🪙 (50% du prix d'achat)."))

    # ── /inventory ────────────────────────────────────────────────────────────

    @app_commands.command(name="inventory", description="Voir ton inventaire")
    async def inventory(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        u = db.get_user(t.id)
        inv = u.get("inventory", [])
        if not inv:
            await i.response.send_message(embed=E.info(f"**{t.display_name}** n'a rien dans son inventaire.")); return
        cfg = db.get_guild(i.guild.id)
        lines = []
        for iid in inv:
            item = cfg.get("shop", {}).get(iid)
            lines.append(f"• `{iid}` — {item['name'] if item else 'Item inconnu'}")
        await i.response.send_message(embed=E.base(f"🎒 Inventaire — {t.display_name}", "\n".join(lines)))


async def setup(bot):
    await bot.add_cog(Economy(bot))