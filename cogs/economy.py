import discord
from discord import app_commands
from discord.ext import commands
from datetime import date, datetime, timedelta
import random
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E, db

DAILY_AMOUNT = 200
DAILY_PREMIUM_MULT = 2
STREAK_BONUS_PER_DAY = 25   # +25 coins par jour de streak
STREAK_CAP = 14            # bonus plafonné à 14 jours

WORK_MIN, WORK_MAX = 50, 300
WORK_COOLDOWN = 3600
WORK_COOLDOWN_PREMIUM = 1800
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
    ("💎", "💎", "💎"): 15, ("⭐", "⭐", "⭐"): 10,
    ("🍎", "🍎", "🍎"): 5, ("🍌", "🍌", "🍌"): 5,
    ("🍊", "🍊", "🍊"): 5, ("🍇", "🍇", "🍇"): 5,
    ("🍒", "🍒", "🍒"): 5,
}
COIN_FRAMES = ["🪙", "🟡", "🪙", "🟡", "🪙"]

ROULETTE_RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
ROULETTE_BLACK = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}

def _card_value(card: str) -> int:
    if card in ("J", "Q", "K"): return 10
    if card == "A": return 11
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
    async def balance(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        u = db.get_user(t.id)
        e = E.base(f"💰 Solde — {t.display_name}", color=discord.Color.gold())
        e.set_thumbnail(url=t.display_avatar.url)
        e.add_field(name="👛 Portefeuille", value=f"**{u['coins']}** 🪙")
        e.add_field(name="🏦 Banque", value=f"**{u['bank']}** 🪙")
        e.add_field(name="💎 Total", value=f"**{u['coins'] + u['bank']}** 🪙")
        streak = u.get("daily_streak", 0)
        if streak:
            e.add_field(name="🔥 Streak", value=f"**{streak}** jour(s)")
        if db.is_premium(t.id):
            e.set_footer(text="⭐ Premium")
        await i.response.send_message(embed=e)

    @app_commands.command(name="daily", description="Récompense quotidienne (avec streak !)")
    async def daily(self, i: discord.Interaction):
        u = db.get_user(i.user.id)
        today = date.today()
        today_str = str(today)

        if u.get("last_daily") == today_str:
            await i.response.send_message(
                embed=E.error(f"Déjà réclamé aujourd'hui ! Streak actuel : **{u.get('daily_streak', 0)}** 🔥"),
                ephemeral=True
            )
            return

        # Calcul du streak
        streak = u.get("daily_streak", 0) or 0
        last = u.get("last_daily")
        if last:
            try:
                last_date = date.fromisoformat(last)
                if last_date == today - timedelta(days=1):
                    streak += 1
                else:
                    streak = 1  # cassé
            except Exception:
                streak = 1
        else:
            streak = 1

        streak = min(streak, 999)
        streak_bonus = min(streak, STREAK_CAP) * STREAK_BONUS_PER_DAY

        amount = DAILY_AMOUNT + streak_bonus
        prem = db.is_premium(i.user.id)
        if prem:
            amount *= DAILY_PREMIUM_MULT

        u["coins"] += amount
        u["last_daily"] = today_str
        u["daily_streak"] = streak
        db.save_user(i.user.id, u)

        lines = [
            f"{i.user.mention} a reçu **{amount} coins** 🪙",
            f"🔥 Streak : **{streak}** jour(s) (+{streak_bonus} bonus)",
        ]
        if prem:
            lines.append("⭐ Premium x2 appliqué")
        lines.append(f"Solde : **{u['coins']} coins**")

        await i.response.send_message(embed=E.success("\n".join(lines), "🎁 Daily Reward"))

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
            earned = int(earned * 1.25)

        job = random.choice(WORK_MESSAGES)
        u["coins"] += earned
        u["last_work"] = now.isoformat()
        db.save_user(i.user.id, u)

        bonus = " ⭐" if prem else ""
        await i.response.send_message(embed=E.success(
            f"{job}\nTu as gagné **{earned} coins** 🪙{bonus}\nSolde : **{u['coins']} coins**",
            "💼 Travail"
        ))

    @app_commands.command(name="pay", description="Envoie des coins à un membre")
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
        await i.response.send_message(embed=E.success(f"{i.user.mention} a envoyé **{amount} coins** 🪙 à {member.mention}."))

    @app_commands.command(name="deposit", description="Dépose des coins en banque")
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
            await i.response.send_message(embed=E.error(f"{member.display_name} est trop fauché."))
            return
        if random.random() < ROB_CHANCE:
            pct = random.uniform(ROB_MIN, ROB_MAX)
            stolen = int(tgt["coins"] * pct)
            tgt["coins"] -= stolen
            src["coins"] += stolen
            db.save_user(i.user.id, src)
            db.save_user(member.id, tgt)
            await i.response.send_message(embed=E.success(
                f"Tu as volé **{stolen} coins** 🪙 à {member.mention} !\nSolde : **{src['coins']}**", "🦹 Vol réussi"
            ))
        else:
            fine = random.randint(50, 200)
            src["coins"] = max(0, src["coins"] - fine)
            db.save_user(i.user.id, src)
            await i.response.send_message(embed=E.error(
                f"Attrapé ! Amende : **{fine} coins**\nSolde : **{src['coins']}**", "🚨 Vol raté"
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
            except Exception:
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
        await i.response.send_message(embed=E.success(f"**+{amount} coins** à {member.mention}. Solde : **{u['coins']}**"))

    @app_commands.command(name="shop", description="Voir la boutique du serveur")
    async def shop(self, i: discord.Interaction):
        cfg = db.get_guild(i.guild.id)
        items = cfg.get("shop", {})
        if not items:
            await i.response.send_message(embed=E.info("Boutique vide.")); return
        lines = [f"**{v['name']}** — `{k}` — {v['price']} coins\n└ {v['desc']}" for k, v in items.items()]
        await i.response.send_message(embed=E.base("🛒 Boutique", "\n\n".join(lines), discord.Color.blue()))

    @app_commands.command(name="buy", description="Achète un item de la boutique")
    async def buy(self, i: discord.Interaction, item_id: str):
        cfg = db.get_guild(i.guild.id)
        item = cfg.get("shop", {}).get(item_id)
        if not item:
            await i.response.send_message(embed=E.error(f"Item `{item_id}` introuvable."), ephemeral=True); return
        u = db.get_user(i.user.id)
        if u["coins"] < item["price"]:
            await i.response.send_message(embed=E.error("Pas assez de coins."), ephemeral=True); return
        u["coins"] -= item["price"]
        u.setdefault("inventory", []).append(item_id)
        db.save_user(i.user.id, u)
        if item.get("role_id"):
            role = i.guild.get_role(item["role_id"])
            if role:
                await i.user.add_roles(role)
        await i.response.send_message(embed=E.success(f"Acheté **{item['name']}** pour **{item['price']} coins**."))

    @app_commands.command(name="sell", description="Vend un item de ton inventaire")
    async def sell(self, i: discord.Interaction, item_id: str):
        u = db.get_user(i.user.id)
        inv = u.get("inventory", [])
        if item_id not in inv:
            await i.response.send_message(embed=E.error(f"Tu n'as pas `{item_id}`."), ephemeral=True); return
        cfg = db.get_guild(i.guild.id)
        item = cfg.get("shop", {}).get(item_id, {})
        refund = int(item.get("price", 0) * 0.5)
        inv.remove(item_id)
        u["coins"] += refund
        db.save_user(i.user.id, u)
        await i.response.send_message(embed=E.success(f"Vendú pour **{refund} coins** (50%)."))

    @app_commands.command(name="inventory", description="Voir ton inventaire")
    async def inventory(self, i: discord.Interaction, member: discord.Member = None):
        t = member or i.user
        u = db.get_user(t.id)
        inv = u.get("inventory", [])
        if not inv:
            await i.response.send_message(embed=E.info(f"**{t.display_name}** : inventaire vide.")); return
        cfg = db.get_guild(i.guild.id)
        lines = [f"• `{iid}` — {cfg.get('shop', {}).get(iid, {}).get('name', 'Item')}" for iid in inv]
        await i.response.send_message(embed=E.base(f"🎒 Inventaire — {t.display_name}", "\n".join(lines)))

    # ─── JEUX ──────────────────────────────────────────────────────

    @app_commands.command(name="coinflip", description="Pile ou face — double ou rien !")
    @app_commands.describe(amount="Mise", choice="pile ou face")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Pile", value="pile"),
        app_commands.Choice(name="Face", value="face"),
    ])
    async def coinflip(self, i: discord.Interaction, amount: app_commands.Range[int, 10, 25000], choice: str):
        max_bet = 25000 if db.is_premium(i.user.id) else 10000
        if amount > max_bet:
            await i.response.send_message(embed=E.error(f"Mise max : **{max_bet}**"), ephemeral=True); return
        u = db.get_user(i.user.id)
        if u["coins"] < amount:
            await i.response.send_message(embed=E.error(f"Solde : **{u['coins']}**"), ephemeral=True); return

        await i.response.defer()
        msg = await i.followup.send(embed=E.base("🪙 Coinflip", "La pièce tourne...\n`🪙`"))
        for frame in COIN_FRAMES:
            await asyncio.sleep(0.35)
            try:
                await msg.edit(embed=E.base("🪙 Coinflip", f"La pièce tourne...\n`{frame}`"))
            except Exception:
                pass

        result = random.choice(["pile", "face"])
        if result == choice:
            u["coins"] += amount
            db.save_user(i.user.id, u)
            e = E.success(f"**{result.upper()}** ! +**{amount}** 🪙\nSolde : **{u['coins']}**", "🪙 Gagné !")
        else:
            u["coins"] -= amount
            db.save_user(i.user.id, u)
            e = E.error(f"**{result.upper()}**... -**{amount}**\nSolde : **{u['coins']}**", "🪙 Perdu")
        await asyncio.sleep(0.4)
        await msg.edit(embed=e)

    @app_commands.command(name="slots", description="Machine à sous")
    async def slots(self, i: discord.Interaction, amount: app_commands.Range[int, 20, 15000]):
        max_bet = 15000 if db.is_premium(i.user.id) else 5000
        if amount > max_bet:
            await i.response.send_message(embed=E.error(f"Mise max : **{max_bet}**"), ephemeral=True); return
        u = db.get_user(i.user.id)
        if u["coins"] < amount:
            await i.response.send_message(embed=E.error(f"Solde : **{u['coins']}**"), ephemeral=True); return

        await i.response.defer()
        msg = await i.followup.send(embed=E.base("🎰 Slots", "Les rouleaux tournent...\n`❓ | ❓ | ❓`"))
        for _ in range(4):
            temp = [random.choice(SLOTS_EMOJIS) for _ in range(3)]
            await asyncio.sleep(0.4)
            try:
                await msg.edit(embed=E.base("🎰", f"`{' | '.join(temp)}`"))
            except Exception:
                pass

        reels = [random.choice(SLOTS_EMOJIS) for _ in range(3)]
        display = " | ".join(reels)
        mult = SLOTS_MULTIPLIERS.get(tuple(reels), 0)
        if mult == 0 and (reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]):
            mult = 2

        if mult > 0:
            win = amount * mult
            u["coins"] += win
            db.save_user(i.user.id, u)
            e = E.success(f"`{display}`\n**x{mult}** → +**{win}** 🪙\nSolde : **{u['coins']}**", "🎰 Gagné !")
        else:
            u["coins"] -= amount
            db.save_user(i.user.id, u)
            e = E.error(f"`{display}`\nRien... -**{amount}**\nSolde : **{u['coins']}**", "🎰 Perdu")
        await asyncio.sleep(0.4)
        await msg.edit(embed=e)

    @app_commands.command(name="blackjack", description="Blackjack contre Kryvoox")
    async def blackjack(self, i: discord.Interaction, amount: app_commands.Range[int, 50, 25000]):
        max_bet = 25000 if db.is_premium(i.user.id) else 10000
        if amount > max_bet:
            await i.response.send_message(embed=E.error(f"Mise max : **{max_bet}**"), ephemeral=True); return
        u = db.get_user(i.user.id)
        if u["coins"] < amount:
            await i.response.send_message(embed=E.error(f"Solde : **{u['coins']}**"), ephemeral=True); return

        player = [_draw_card(), _draw_card()]
        dealer = [_draw_card(), _draw_card()]
        pv, dv = _hand_value(player), _hand_value(dealer)

        if pv == 21:
            if dv == 21:
                e = E.info(f"Toi: {' '.join(player)} ({pv})\nBot: {' '.join(dealer)} ({dv})\nÉgalité.")
            else:
                win = int(amount * 1.5)
                u["coins"] += win
                db.save_user(i.user.id, u)
                e = E.success(f"**BLACKJACK !** +**{win}** 🪙\nSolde : **{u['coins']}**")
            await i.response.send_message(embed=e)
            return

        while pv < 17:
            player.append(_draw_card())
            pv = _hand_value(player)

        if pv > 21:
            u["coins"] -= amount
            db.save_user(i.user.id, u)
            e = E.error(f"Toi: {' '.join(player)} ({pv}) **BUST**\n-**{amount}** → **{u['coins']}**")
            await i.response.send_message(embed=e)
            return

        while dv < 17:
            dealer.append(_draw_card())
            dv = _hand_value(dealer)

        if dv > 21 or pv > dv:
            u["coins"] += amount
            db.save_user(i.user.id, u)
            e = E.success(f"Toi: {' '.join(player)} ({pv})\nBot: {' '.join(dealer)} ({dv})\n+**{amount}** → **{u['coins']}**")
        elif pv == dv:
            e = E.info(f"Toi: {' '.join(player)} ({pv})\nBot: {' '.join(dealer)} ({dv})\nÉgalité.")
        else:
            u["coins"] -= amount
            db.save_user(i.user.id, u)
            e = E.error(f"Toi: {' '.join(player)} ({pv})\nBot: {' '.join(dealer)} ({dv})\n-**{amount}** → **{u['coins']}**")
        await i.response.send_message(embed=e)

    # ── /roulette ──────────────────────────────────────────────

    @app_commands.command(name="roulette", description="Roulette — mise sur rouge, noir ou un numéro")
    @app_commands.describe(
        amount="Mise (min 20)",
        bet="rouge / noir / 0-36"
    )
    async def roulette(self, i: discord.Interaction, amount: app_commands.Range[int, 20, 20000], bet: str):
        max_bet = 20000 if db.is_premium(i.user.id) else 8000
        if amount > max_bet:
            await i.response.send_message(embed=E.error(f"Mise max : **{max_bet}**"), ephemeral=True); return

        bet = bet.lower().strip()
        u = db.get_user(i.user.id)
        if u["coins"] < amount:
            await i.response.send_message(embed=E.error(f"Solde : **{u['coins']}**"), ephemeral=True); return

        # Validation de la mise
        if bet in ("rouge", "red", "r"):
            bet_type, bet_val = "color", "red"
        elif bet in ("noir", "black", "n"):
            bet_type, bet_val = "color", "black"
        elif bet.isdigit() and 0 <= int(bet) <= 36:
            bet_type, bet_val = "number", int(bet)
        else:
            await i.response.send_message(
                embed=E.error("Mise invalide. Utilise `rouge`, `noir` ou un numéro `0-36`."),
                ephemeral=True
            )
            return

        await i.response.defer()
        msg = await i.followup.send(embed=E.base("🎰 Roulette", "La bille tourne... 🎰"))
        await asyncio.sleep(1.2)

        result = random.randint(0, 36)
        if result == 0:
            color = "vert"
            color_emoji = "🟢"
        elif result in ROULETTE_RED:
            color = "rouge"
            color_emoji = "🔴"
        else:
            color = "noir"
            color_emoji = "⚫"

        won = False
        payout = 0

        if bet_type == "color":
            if bet_val == "red" and result in ROULETTE_RED:
                won, payout = True, amount * 2
            elif bet_val == "black" and result in ROULETTE_BLACK:
                won, payout = True, amount * 2
        else:
            if result == bet_val:
                won, payout = True, amount * 36  # numéro exact

        if won:
            gain = payout - amount
            u["coins"] += gain
            db.save_user(i.user.id, u)
            e = E.success(
                f"{color_emoji} **{result}** ({color})\n"
                f"Tu gagnes **+{gain} coins** 🪙\nSolde : **{u['coins']}**",
                "🎰 Roulette — Gagné !"
            )
        else:
            u["coins"] -= amount
            db.save_user(i.user.id, u)
            e = E.error(
                f"{color_emoji} **{result}** ({color})\n"
                f"Tu perds **-{amount} coins**\nSolde : **{u['coins']}**",
                "🎰 Roulette — Perdu"
            )

        await msg.edit(embed=e)

    # ── /dice ─────────────────────────────────────────────────

    @app_commands.command(name="dice", description="Lance les dés contre Kryvoox")
    @app_commands.describe(amount="Mise (min 10)")
    async def dice(self, i: discord.Interaction, amount: app_commands.Range[int, 10, 15000]):
        max_bet = 15000 if db.is_premium(i.user.id) else 5000
        if amount > max_bet:
            await i.response.send_message(embed=E.error(f"Mise max : **{max_bet}**"), ephemeral=True); return
        u = db.get_user(i.user.id)
        if u["coins"] < amount:
            await i.response.send_message(embed=E.error(f"Solde : **{u['coins']}**"), ephemeral=True); return

        await i.response.defer()
        msg = await i.followup.send(embed=E.base("🎲 Dés", "Lancement..."))
        await asyncio.sleep(0.8)

        player_roll = random.randint(1, 6) + random.randint(1, 6)
        bot_roll = random.randint(1, 6) + random.randint(1, 6)

        if player_roll > bot_roll:
            u["coins"] += amount
            db.save_user(i.user.id, u)
            e = E.success(
                f"Toi : **{player_roll}** 🎲\nKryvoox : **{bot_roll}**\n"
                f"+**{amount} coins** → **{u['coins']}**",
                "🎲 Gagné !"
            )
        elif player_roll < bot_roll:
            u["coins"] -= amount
            db.save_user(i.user.id, u)
            e = E.error(
                f"Toi : **{player_roll}** 🎲\nKryvoox : **{bot_roll}**\n"
                f"-**{amount} coins** → **{u['coins']}**",
                "🎲 Perdu"
            )
        else:
            e = E.info(
                f"Toi : **{player_roll}** 🎲\nKryvoox : **{bot_roll}**\nÉgalité — mise rendue.",
                "🎲 Égalité"
            )

        await msg.edit(embed=e)


async def setup(bot):
    await bot.add_cog(Economy(bot))
