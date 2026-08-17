import discord
from discord import app_commands
from discord.ext import commands
from datetime import date, datetime
import random
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

DAILY_AMOUNT = 200
DAILY_PREMIUM_MULT = 2
WORK_MIN, WORK_MAX = 50, 300
WORK_COOLDOWN = 3600          # 1h normal
WORK_COOLDOWN_PREMIUM = 1800  # 30 min premium
ROB_CHANCE = 0.45
ROB_MIN, ROB_MAX = 0.05, 0.25

WORK_MESSAGES = [
    "Tu as livré des pizzas 🍕", "Tu as codé toute la nuit 💻",
    "Tu as vendu des NFTs à des pigeons 🐦", "Tu as été garde du corps de Kryvoox 🤖",
    "Tu as traduit des manuels IKEA 📦", "Tu as streamer 12h de suite 🎮",
    "Tu as présenté la météo 🌤️", "Tu as joué de la guitare dans le métro 🎸",
]

SLOTS_EMOJIS = ["🍎", "🍌", "🍊", "🍇", "⭐", "💎", "🍒"]
SLOTS_MULTIPLIERS = {
    ("💎", "💎", "💎"): 15,
    ("⭐", "⭐", "⭐"): 10,
    ("🍎", "🍎", "🍎"): 5,
    ("🍌", "🍌", "🍌"): 5,
    ("🍊", "🍊", "🍊"): 5,
    ("🍇", "🍇", "🍇"): 5,
    ("🍒", "🍒", "🍒"): 5,
}

COIN_FRAMES = ["🪙", "🟡", "🪙", "🟡", "🪙"]

def _card_value(card: str) -> int:
    if card in ("J", "Q", "K"):
        return 10
    if card == "A":
        return 11
    return int(card)

def _hand_value(hand: list[str]) -> int:
    total = sum(_card_value(c) for c in hand)
    aces = hand.count("A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

def _draw_card() -> str:
    return random.choice(["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"])


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Voir ton solde ou celui d'un membre")
    @app_commands.describe(member="Le membre (optionnel)")
    async def balance(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        u = db.get_user(t.id)
        e = E.base(f"💰 Solde — {t.display_name}", color=discord.Color.gold())
        e.set_thumbnail(url=t.display_avatar.url)
        e.add_field(name="👛 Portefeuille", value=f"**{u['coins']}** 🪙")
        e.add_field(name="🏦 Banque", value=f"**{u['bank']}** 🪙")
        e.add_field(name="💎 Total", value=f"**{u['coins'] + u['bank']}** 🪙")
        if db.is_premium(t.id):
            e.set_footer(text="⭐ Premium")
        await i.response.send_message(embed=e)

    @app_commands.command(name="daily", description="Récompense quotidienne")
    async def daily(self, i: discord.Interaction):
        u = db.get_user(i.user.id)
        today = str(date.today())
        if u.get("last_daily") == today:
            await i.response.send_message(embed=E.error("Tu as déjà réclamé ta récompense aujourd'hui. Reviens demain !"), ephemeral=True)
            return

        amount = DAILY_AMOUNT
        prem = db.is_premium(i.user.id)
        if prem:
            amount = DAILY_AMOUNT * DAILY_PREMIUM_MULT

        u["coins"] += amount
        u["last_daily"] = today
        db.save_user(i.user.id, u)

        bonus = " (\u2b50 Premium x2)" if prem else ""
        await i.response.send_message(embed=E.success(
            f"{i.user.mention} a reçu **{amount} coins** 🪙{bonus}\nNouveau solde : **{u['coins']} coins**",
            "🎁 Daily Reward"
        ))

    @app_commands.command(name="work", description="Travaille pour gagner des coins")
    async def work(self, i: discord.Interaction):
        u = db.get_user(i.user.id)
        now = datetime.now()
        last = u.get("last_work")
        prem = db.is_premium(i.user.id)
        cooldown = WORK_COOLDOWN_PREMIUM if prem else WORK_COOLDOWN

        if last:
            elapsed = (now - datetime.fromisoformat(last)).total_seconds()
            if elapsed < cooldown:
                remaining = int(cooldown - elapsed)
                m, s = divmod(remaining, 60)
                await i.response.send_message(embed=E.error(f"Tu es épuisé. Repose-toi encore **{m}min {s}s**."), ephemeral=True)
                return

        earned = random.randint(WORK_MIN, WORK_MAX)
        if prem:
            earned = int(earned * 1.25)  # +25% pour premium

        job = random.choice(WORK_MESSAGES)
        u["coins"] += earned
        u["last_work"] = now.isoformat()
        db.save_user(i.user.id, u)

        bonus = " \u2b50" if prem else ""
        await i.response.send_message(embed=E.success(
            f"{job}\nTu as gagné **{earned} coins** 🪙{bonus}\nSolde : **{u['coins']} coins**",
            "💼 Travail"
        ))

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

    @app_commands.command(name="deposit", description="Dépose des coins en banque")
    @app_commands.describe(amount="Montant (ou 'all')")
    async def deposit(self, i: discord.Interaction, amount: str = "all"):
        u = db.get_user(i.user.id)
        n = u["coins"] if amount.lower() == "all" else int(amount)
        if n <= 0 or n > u["coins"]:
            await i.response.send_message(embed=E.error(f"Montant invalide. Solde : **{u['coins']} coins**"), ephemeral=True); return
        u["coins"] -= n
        u["bank"] += n
        db.save_user(i.user.id, u)
        await i.response.send_message(embed=E.success(f"**{n} coins** déposés en banque 🏦\nBanque : **{u['bank']} coins**"))

    @app_commands.command(name="withdraw", description="Retire des coins de la banque")
    @app_commands.describe(amount="Montant (ou 'all')")
    async def withdraw(self, i: discord.Interaction, amount: str = "all"):
        u = db.get_user(i.user.id)
        n = u["bank"] if amount.lower() == "all" else int(amount)
        if n <= 0 or n > u["bank"]:
            await i.response.send_message(embed=E.error(f"Montant invalide. Banque : **{u['bank']} coins**"), ephemeral=True); return
        u["bank"] -= n
        u["coins"] += n
        db.save_user(i.user.id, u)
        await i.response.send_message(embed=E.success(f"**{n} coins** retirés 👛\nPortefeuille : **{u['coins']} coins**"))

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

    @app_commands.command(name="leaderboard", description="Classement des plus riches")
    async def leaderboard(self, i: discord.Interaction):
        top = db.get_leaderboard_economy()
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for idx, (uid, data) in enumerate(top):
            try:
                u = await self.bot.fetch_user(int(uid))
                name = u.display_name
            except:
                name = f"User#{str(uid)[:4]}"
            medal = medals[idx] if idx < 3 else f"`{idx+1}.`"
            total = data.get("coins", 0) + data.get("bank", 0)
            star = " ⭐" if data.get("premium") else ""
            lines.append(f"{medal} **{name}**{star} — {total} coins 🪙")
        await i.response.send_message(embed=E.base("🏆 Classement — Économie", "\n".join(lines) or "Aucune donnée.", discord.Color.gold()))

    @app_commands.command(name="give", description="[Admin] Donne des coins à un membre")
    @app_commands.default_permissions(administrator=True)
    async def give(self, i: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await i.response.send_message(embed=E.error("Montant invalide."), ephemeral=True); return
        u = db.get_user(member.id)
        u["coins"] += amount
        db.save_user(member.id, u)
        await i.response.send_message(embed=E.success(f"**+{amount} coins** donnés à {member.mention}. Solde : **{u['coins']} coins**"))

    @app_commands.command(name="shop", description="Voir la boutique du serveur")
    async def shop(self, i: discord.Interaction):
        cfg = db.get_guild(i.guild.id)
        items = cfg.get("shop", {})
        if not items:
            await i.response.send_message(embed=E.info("La boutique est vide. Un admin peut ajouter des items.")); return
        lines = [f"**{v['name']}** — `{k}` — {v['price']} coins 🪙\n└ {v['desc']}" for k, v in items.items()]
        await i.response.send_message(embed=E.base("🛒 Boutique", "\n\n".join(lines), discord.Color.blue()))

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

    # ─── JEUX ──────────────────────────────────────────────────────────

    @app_commands.command(name="coinflip", description="Pile ou face — double ou rien ! (animé)")
    @app_commands.describe(amount="Mise (min 10)", choice="pile ou face")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Pile", value="pile"),
        app_commands.Choice(name="Face", value="face"),
    ])
    async def coinflip(self, i: discord.Interaction, amount: app_commands.Range[int, 10, 25000], choice: str):
        max_bet = 25000 if db.is_premium(i.user.id) else 10000
        if amount > max_bet:
            await i.response.send_message(embed=E.error(f"Mise max : **{max_bet}** (Premium = 25k)"), ephemeral=True)
            return
        u = db.get_user(i.user.id)
        if u["coins"] < amount:
            await i.response.send_message(embed=E.error(f"Pas assez de coins. Solde : **{u['coins']}**"), ephemeral=True)
            return

        await i.response.defer()
        msg = await i.followup.send(embed=E.base("🪙 Coinflip", "La pièce tourne...\n`🪙`"))
        for frame in COIN_FRAMES:
            await asyncio.sleep(0.35)
            try:
                await msg.edit(embed=E.base("🪙 Coinflip", f"La pièce tourne...\n`{frame}`"))
            except Exception:
                pass

        result = random.choice(["pile", "face"])
        won = result == choice
        if won:
            u["coins"] += amount
            db.save_user(i.user.id, u)
            e = E.success(f"La pièce tombe sur **{result.upper()}** !\nTu gagnes **+{amount} coins** 🪙\nNouveau solde : **{u['coins']}**", "🪙 Coinflip — Gagné !")
        else:
            u["coins"] -= amount
            db.save_user(i.user.id, u)
            e = E.error(f"La pièce tombe sur **{result.upper()}**...\nTu perds **-{amount} coins**\nNouveau solde : **{u['coins']}**", "🪙 Coinflip — Perdu")
        await asyncio.sleep(0.4)
        await msg.edit(embed=e)

    @app_commands.command(name="slots", description="Machine à sous — tente le jackpot ! (animé)")
    @app_commands.describe(amount="Mise (min 20)")
    async def slots(self, i: discord.Interaction, amount: app_commands.Range[int, 20, 15000]):
        max_bet = 15000 if db.is_premium(i.user.id) else 5000
        if amount > max_bet:
            await i.response.send_message(embed=E.error(f"Mise max : **{max_bet}** (Premium = 15k)"), ephemeral=True)
            return
        u = db.get_user(i.user.id)
        if u["coins"] < amount:
            await i.response.send_message(embed=E.error(f"Pas assez de coins. Solde : **{u['coins']}**"), ephemeral=True)
            return

        await i.response.defer()
        msg = await i.followup.send(embed=E.base("🎰 Slots", "Les rouleaux tournent...\n`❓ | ❓ | ❓`"))
        for _ in range(4):
            temp = [random.choice(SLOTS_EMOJIS) for _ in range(3)]
            display = " | ".join(temp)
            await asyncio.sleep(0.4)
            try:
                await msg.edit(embed=E.base("🎰 Slots", f"Les rouleaux tournent...\n`{display}`"))
            except Exception:
                pass

        reels = [random.choice(SLOTS_EMOJIS) for _ in range(3)]
        display = " | ".join(reels)
        key = tuple(reels)
        mult = SLOTS_MULTIPLIERS.get(key, 0)
        if mult == 0 and (reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]):
            mult = 2

        if mult > 0:
            win = amount * mult
            u["coins"] += win
            db.save_user(i.user.id, u)
            e = E.success(f"`{display}`\n\n**x{mult}** ! Tu gagnes **+{win} coins** 🪙\nSolde : **{u['coins']}**", "🎰 Slots — Jackpot !" if mult >= 10 else "🎰 Slots — Gagné !")
        else:
            u["coins"] -= amount
            db.save_user(i.user.id, u)
            e = E.error(f"`{display}`\n\nRien... Tu perds **-{amount} coins**\nSolde : **{u['coins']}**", "🎰 Slots — Perdu")
        await asyncio.sleep(0.45)
        await msg.edit(embed=e)

    @app_commands.command(name="blackjack", description="Blackjack contre Kryvoox")
    @app_commands.describe(amount="Mise (min 50)")
    async def blackjack(self, i: discord.Interaction, amount: app_commands.Range[int, 50, 25000]):
        max_bet = 25000 if db.is_premium(i.user.id) else 10000
        if amount > max_bet:
            await i.response.send_message(embed=E.error(f"Mise max : **{max_bet}** (Premium = 25k)"), ephemeral=True)
            return
        u = db.get_user(i.user.id)
        if u["coins"] < amount:
            await i.response.send_message(embed=E.error(f"Pas assez de coins. Solde : **{u['coins']}**"), ephemeral=True)
            return

        player = [_draw_card(), _draw_card()]
        dealer = [_draw_card(), _draw_card()]
        player_val = _hand_value(player)
        dealer_val = _hand_value(dealer)

        if player_val == 21:
            if dealer_val == 21:
                e = E.info(f"**Toi :** {' '.join(player)} (`{player_val}`)\n**Kryvoox :** {' '.join(dealer)} (`{dealer_val}`)\n\nDouble Blackjack ! Égalité.", "🃏 Blackjack — Égalité")
            else:
                win = int(amount * 1.5)
                u["coins"] += win
                db.save_user(i.user.id, u)
                e = E.success(f"**Toi :** {' '.join(player)} (`{player_val}`) → **BLACKJACK !**\n**Kryvoox :** {' '.join(dealer)} (`{dealer_val}`)\n\nTu gagnes **+{win} coins** 🪙\nSolde : **{u['coins']}**", "🃏 Blackjack !")
            await i.response.send_message(embed=e)
            return

        while player_val < 17:
            player.append(_draw_card())
            player_val = _hand_value(player)

        if player_val > 21:
            u["coins"] -= amount
            db.save_user(i.user.id, u)
            e = E.error(f"**Toi :** {' '.join(player)} (`{player_val}`) → **BUST !**\n**Kryvoox :** {' '.join(dealer)} (`{dealer_val}`)\n\nTu perds **-{amount} coins**\nSolde : **{u['coins']}**", "🃏 Blackjack — Bust")
            await i.response.send_message(embed=e)
            return

        while dealer_val < 17:
            dealer.append(_draw_card())
            dealer_val = _hand_value(dealer)

        if dealer_val > 21 or player_val > dealer_val:
            u["coins"] += amount
            db.save_user(i.user.id, u)
            e = E.success(f"**Toi :** {' '.join(player)} (`{player_val}`)\n**Kryvoox :** {' '.join(dealer)} (`{dealer_val}`)\n\nTu gagnes **+{amount} coins** 🪙\nSolde : **{u['coins']}**", "🃏 Blackjack — Gagné !")
        elif player_val == dealer_val:
            e = E.info(f"**Toi :** {' '.join(player)} (`{player_val}`)\n**Kryvoox :** {' '.join(dealer)} (`{dealer_val}`)\n\nÉgalité ! Mise rendue.", "🃏 Blackjack — Égalité")
        else:
            u["coins"] -= amount
            db.save_user(i.user.id, u)
            e = E.error(f"**Toi :** {' '.join(player)} (`{player_val}`)\n**Kryvoox :** {' '.join(dealer)} (`{dealer_val}`)\n\nTu perds **-{amount} coins**\nSolde : **{u['coins']}**", "🃏 Blackjack — Perdu")
        await i.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(Economy(bot))
