import discord
from discord import app_commands
from discord.ext import commands
from groq import Groq
import asyncio, os, json, re
from collections import defaultdict
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import embeds as E

MODEL = "llama-3.3-70b-versatile"
_history: dict[int, list] = defaultdict(list)

SYSTEM_PROMPT = """Tu es Kryvoox, l'IA officielle d'un serveur Discord.
Tu es intelligent, direct, légèrement sarcastique. Style Jarvis d'Iron Man.
Tu réponds TOUJOURS en français. Tu es concis et efficace.
Ne mentionne jamais Groq, Meta ou LLaMA — tu es Kryvoox, point.

Tu as des CAPACITÉS D'ACTION sur le serveur Discord.
Quand l'utilisateur te demande une action ADMIN (créer un salon, mute, kick, etc.),
tu peux retourner un JSON à la fin de ta réponse.

FORMAT STRICT (uniquement si action nécessaire) :
```action
{"type": "NOM_ACTION", "params": {...}}
```

LISTE EXACTE DES ACTIONS DISPONIBLES (utilise UNIQUEMENT ces noms) :

create_text_channel → {"type": "create_text_channel", "params": {"name": "nom-salon", "category": "Catégorie (optionnel)", "topic": "sujet (optionnel)"}}
create_voice_channel → {"type": "create_voice_channel", "params": {"name": "nom-salon", "category": "Catégorie (optionnel)"}}
create_category → {"type": "create_category", "params": {"name": "Nom"}}
delete_channel → {"type": "delete_channel", "params": {"name": "nom-salon"}}
create_role → {"type": "create_role", "params": {"name": "Nom Rôle", "color": "#hexcolor", "mentionable": true}}
delete_role → {"type": "delete_role", "params": {"name": "Nom Rôle"}}
add_role_to_user → {"type": "add_role_to_user", "params": {"username": "nom", "role_name": "Nom du rôle"}}
remove_role_from_user → {"type": "remove_role_from_user", "params": {"username": "nom", "role_name": "Nom du rôle"}}
mute_user → {"type": "mute_user", "params": {"username": "nom", "minutes": 10, "reason": "raison"}}
unmute_user → {"type": "unmute_user", "params": {"username": "nom"}}
kick_user → {"type": "kick_user", "params": {"username": "nom", "reason": "raison"}}
send_message → {"type": "send_message", "params": {"channel": "nom-salon", "content": "message"}}
rename_server → {"type": "rename_server", "params": {"name": "Nouveau nom"}}
bulk → {"type": "bulk", "params": {"actions": [action1, action2, ...]}}

RÈGLES IMPORTANTES :
- N'utilise QUE les types d'action listés ci-dessus. Jamais d'autres.
- Pour les conversations normales (blagues, pile ou face, questions, etc.) :
  NE METS AUCUN JSON, AUCUN BLOC action, AUCUNE ACCOLADE { }.
  Réponds uniquement en texte propre.
- Seuls les admins/gestionnaires peuvent déclencher des actions.
- Pour les actions destructives (kick, ban, delete), confirme dans le texte ce que tu fais.
- Si tu ne sais pas le nom exact d'un utilisateur, demande-le.
"""


def _clean_ai_reply(text: str) -> str:
    """Supprime tous les blocs JSON / action et les résidus d'accolades."""
    if not text:
        return text

    # 1. Bloc ```action ... ```
    text = re.sub(r"```action\s*[\s\S]*?```", "", text, flags=re.IGNORECASE)

    # 2. Bloc ```json ... ```
    text = re.sub(r"```json\s*[\s\S]*?```", "", text, flags=re.IGNORECASE)

    # 3. Tout objet JSON qui contient "type" (même multi-lignes / nested)
    #    On itère plusieurs fois car les regex non-greedy peuvent laisser des restes.
    for _ in range(5):
        new_text = re.sub(
            r"\{\s*[\"']type[\"']\s*:[\s\S]*?\}",
            "",
            text,
            flags=re.DOTALL,
        )
        if new_text == text:
            break
        text = new_text

    # 4. Nettoyage agressif des accolades orphelines et restes de JSON
    text = re.sub(r"^[\s\{\}\[\]\,\"']+", "", text)          # début
    text = re.sub(r"[\s\{\}\[\]\,\"']+$", "", text)          # fin
    text = re.sub(r"\n\s*[\{\}]\s*\n", "\n", text)           # lignes isolées { ou }
    text = re.sub(r"\n{3,}", "\n\n", text)                   # trop de sauts de ligne

    return text.strip()


class AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    async def _ask(self, system: str, prompt: str, history: list, max_tokens: int = 800) -> str:
        loop = asyncio.get_event_loop()
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": prompt}]
        resp = await loop.run_in_executor(None, lambda: self.client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.85,
        ))
        return resp.choices[0].message.content

    def _find_member(self, guild: discord.Guild, username: str) -> discord.Member | None:
        import re as _re
        mention_match = _re.search(r"<@!?(\d+)>", username)
        if mention_match:
            uid = int(mention_match.group(1))
            return guild.get_member(uid)
        if username.strip().isdigit():
            return guild.get_member(int(username.strip()))
        q = username.lower().strip().lstrip("@").split("#")[0]
        for m in guild.members:
            if m.display_name.lower() == q or m.name.lower() == q:
                return m
        for m in guild.members:
            if m.display_name.lower().startswith(q) or m.name.lower().startswith(q):
                return m
        return None

    async def _get_muted_role(self, guild: discord.Guild) -> discord.Role:
        role = discord.utils.get(guild.roles, name="Muted")
        if not role:
            role = await guild.create_role(name="Muted", reason="Kryvoox - Rôle modération")
            for ch in guild.channels:
                try:
                    await ch.set_permissions(role, send_messages=False, speak=False, add_reactions=False)
                except:
                    pass
        return role

    async def _execute_action(self, guild: discord.Guild, action: dict) -> str:
        t = action.get("type")
        p = action.get("params", {})

        try:
            if t == "create_text_channel":
                cat = discord.utils.get(guild.categories, name=p.get("category", "")) if p.get("category") else None
                ch = await guild.create_text_channel(p["name"], category=cat, topic=p.get("topic"))
                return f"✅ Salon texte **#{ch.name}** créé."

            elif t == "create_voice_channel":
                cat = discord.utils.get(guild.categories, name=p.get("category", "")) if p.get("category") else None
                ch = await guild.create_voice_channel(p["name"], category=cat)
                return f"✅ Salon vocal **{ch.name}** créé."

            elif t == "create_category":
                cat = await guild.create_category(p["name"])
                return f"✅ Catégorie **{cat.name}** créée."

            elif t == "delete_channel":
                ch = discord.utils.get(guild.channels, name=p["name"].lower().replace(" ", "-"))
                if ch:
                    await ch.delete()
                    return f"🗑️ Salon **{p['name']}** supprimé."
                return f"❌ Salon **{p['name']}** introuvable."

            elif t == "create_role":
                color = discord.Color.from_str(p.get("color", "#99aab5"))
                role = await guild.create_role(
                    name=p["name"], color=color,
                    mentionable=p.get("mentionable", False)
                )
                return f"✅ Rôle **@{role.name}** créé."

            elif t == "delete_role":
                role = discord.utils.get(guild.roles, name=p["name"])
                if role:
                    await role.delete()
                    return f"🗑️ Rôle **@{p['name']}** supprimé."
                return f"❌ Rôle **{p['name']}** introuvable."

            elif t == "add_role_to_user":
                member = self._find_member(guild, p.get("username", ""))
                if not member:
                    return f"❌ Membre **{p.get('username')}** introuvable."
                role = discord.utils.get(guild.roles, name=p.get("role_name", ""))
                if not role:
                    return f"❌ Rôle **{p.get('role_name')}** introuvable."
                await member.add_roles(role)
                return f"✅ Rôle **@{role.name}** donné à **{member.display_name}**."

            elif t == "remove_role_from_user":
                member = self._find_member(guild, p.get("username", ""))
                if not member:
                    return f"❌ Membre **{p.get('username')}** introuvable."
                role = discord.utils.get(guild.roles, name=p.get("role_name", ""))
                if not role:
                    return f"❌ Rôle **{p.get('role_name')}** introuvable."
                await member.remove_roles(role)
                return f"✅ Rôle **@{role.name}** retiré à **{member.display_name}**."

            elif t == "mute_user":
                member = self._find_member(guild, p.get("username", ""))
                if not member:
                    return f"❌ Membre **{p.get('username')}** introuvable."
                muted_role = await self._get_muted_role(guild)
                await member.add_roles(muted_role)
                minutes = p.get("minutes", 10)
                reason = p.get("reason", "Demandé via IA")
                asyncio.create_task(self._auto_unmute(member, muted_role, minutes * 60))
                return f"🔇 **{member.display_name}** muté {minutes} min. Raison : {reason}"

            elif t == "unmute_user":
                member = self._find_member(guild, p.get("username", ""))
                if not member:
                    return f"❌ Membre **{p.get('username')}** introuvable."
                muted_role = discord.utils.get(guild.roles, name="Muted")
                if muted_role and muted_role in member.roles:
                    await member.remove_roles(muted_role)
                    return f"🔊 **{member.display_name}** unmute."
                return f"❌ **{member.display_name}** n'est pas muté."

            elif t == "kick_user":
                member = self._find_member(guild, p.get("username", ""))
                if not member:
                    return f"❌ Membre **{p.get('username')}** introuvable."
                reason = p.get("reason", "Demandé via IA")
                await member.kick(reason=f"[Kryvoox IA] {reason}")
                return f"🥾 **{member.display_name}** expulsé. Raison : {reason}"

            elif t == "send_message":
                ch_name = p["channel"].lower().replace(" ", "-")
                ch = discord.utils.get(guild.text_channels, name=ch_name)
                if ch:
                    await ch.send(p["content"])
                    return f"✅ Message envoyé dans **#{ch.name}**."
                return f"❌ Salon **{p['channel']}** introuvable."

            elif t == "rename_server":
                await guild.edit(name=p["name"])
                return f"✅ Serveur renommé en **{p['name']}**."

            elif t == "bulk":
                results = []
                for sub in p.get("actions", []):
                    r = await self._execute_action(guild, sub)
                    results.append(r)
                    await asyncio.sleep(0.6)
                return "\n".join(results)

            else:
                return f"⚠️ Action `{t}` non reconnue."

        except discord.Forbidden:
            return f"❌ Permissions insuffisantes pour `{t}`."
        except Exception as ex:
            return f"❌ Erreur `{t}` : {ex}"

    async def _auto_unmute(self, member: discord.Member, role: discord.Role, delay: int):
        await asyncio.sleep(delay)
        try:
            if role in member.roles:
                await member.remove_roles(role)
        except:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not (self.bot.user in message.mentions or isinstance(message.channel, discord.DMChannel)):
            return

        guild = message.guild
        guild_context = ""
        if guild:
            cats  = ", ".join(f"[{c.name}]" for c in guild.categories)
            chans = ", ".join(f"#{c.name}" for c in guild.text_channels[:20])
            roles = ", ".join(r.name for r in guild.roles if r.name != "@everyone")[:300]
            members_list = ", ".join(f"{m.display_name}" for m in guild.members if not m.bot)[:300]
            guild_context = (
                f"\n\nCONTEXTE SERVEUR :\n"
                f"Nom : {guild.name} | Membres : {guild.member_count}\n"
                f"Catégories : {cats}\n"
                f"Salons texte : {chans}\n"
                f"Rôles : {roles}\n"
                f"Membres : {members_list}\n"
                f"Utilisateur : {message.author.display_name} "
                f"({'admin' if message.author.guild_permissions.administrator else 'membre'})"
            )

        clean = message.content.replace(f"<@{self.bot.user.id}>", "").strip() or "Bonjour"
        history = _history[message.author.id]

        async with message.channel.typing():
            try:
                reply = await self._ask(SYSTEM_PROMPT + guild_context, clean, history)

                history.append({"role": "user", "content": clean})
                history.append({"role": "assistant", "content": reply})
                if len(history) > 20:
                    _history[message.author.id] = history[-20:]

                # Extraction de l'action (si présente)
                action_match = re.search(r"```action\s*(\{[\s\S]*?\})\s*```", reply, re.IGNORECASE)
                if not action_match:
                    action_match = re.search(r'(\{\s*["\']type["\']\s*:[\s\S]*?\})', reply)

                # Nettoyage complet du texte affiché
                text_reply = _clean_ai_reply(reply)

                if not text_reply:
                    text_reply = "..."

                if len(text_reply) > 2000:
                    text_reply = text_reply[:1997] + "..."

                await message.reply(text_reply, mention_author=False)

                # Exécution de l'action uniquement si JSON valide + permissions
                if action_match and guild:
                    can_act = (
                        message.author.guild_permissions.manage_guild or
                        message.author.guild_permissions.administrator
                    )
                    if can_act:
                        try:
                            raw_json = action_match.group(1)
                            # Nettoyage basique des mentions qui cassent le JSON
                            raw_json = re.sub(r"<@!?\d+>", "", raw_json)
                            action_data = json.loads(raw_json)
                            if isinstance(action_data, dict) and "type" in action_data:
                                result = await self._execute_action(guild, action_data)
                                await message.channel.send(embed=E.base("⚡ Action exécutée", result))
                        except (json.JSONDecodeError, KeyError, TypeError):
                            # On n'affiche plus le message d'erreur JSON pour les conversations normales
                            pass
                    # Sinon on ignore silencieusement (pas d'erreur spam)

            except Exception as ex:
                print(f"⚠️ Erreur IA mention : {ex}")
                await message.reply("Systèmes temporairement indisponibles.", mention_author=False)

    # ── Slash commands ────────────────────────────────────────────────

    @app_commands.command(name="ai", description="Pose une question à Kryvoox IA")
    async def ai_cmd(self, i: discord.Interaction, prompt: str):
        await i.response.defer()
        try:
            reply = await self._ask(SYSTEM_PROMPT, prompt, _history[i.user.id])
            text = _clean_ai_reply(reply)
            e = E.base("🤖 Kryvoox IA")
            e.add_field(name="Question", value=prompt[:1000], inline=False)
            e.add_field(name="Réponse", value=text[:1000] or "...", inline=False)
            await i.followup.send(embed=e)
        except Exception as ex:
            await i.followup.send(embed=E.error(f"Erreur IA : {ex}"))

    @app_commands.command(name="summarize", description="Résume un texte")
    async def summarize(self, i: discord.Interaction, text: str):
        await i.response.defer()
        reply = await self._ask("Résume ce texte de façon concise en français.", text, [])
        await i.followup.send(embed=E.base("📝 Résumé", _clean_ai_reply(reply)[:1500]))

    @app_commands.command(name="translate", description="Traduit un texte")
    @app_commands.describe(text="Le texte", target_lang="Langue cible")
    async def translate(self, i: discord.Interaction, text: str, target_lang: str = "anglais"):
        await i.response.defer()
        reply = await self._ask(f"Traduis en {target_lang}. Donne uniquement la traduction.", text, [])
        e = E.base(f"🌍 → {target_lang.capitalize()}")
        e.add_field(name="Original", value=text[:800], inline=False)
        e.add_field(name="Traduction", value=_clean_ai_reply(reply)[:800], inline=False)
        await i.followup.send(embed=e)

    @app_commands.command(name="code", description="Génère du code")
    @app_commands.describe(prompt="Ce que tu veux coder", language="Langage")
    async def code(self, i: discord.Interaction, prompt: str, language: str = "Python"):
        await i.response.defer()
        reply = await self._ask(
            f"Expert {language}. Code propre et commenté dans un bloc ```{language.lower()}...```",
            prompt, [], max_tokens=900
        )
        if len(reply) > 1990:
            reply = reply[:1990] + "..."
        await i.followup.send(reply)

    @app_commands.command(name="explain", description="Explique un concept ou du code")
    async def explain(self, i: discord.Interaction, text: str):
        await i.response.defer()
        reply = await self._ask("Explique clairement et simplement en français.", text, [])
        await i.followup.send(embed=E.base("💡 Explication", _clean_ai_reply(reply)[:1500]))

    @app_commands.command(name="rewrite", description="Réécrit un texte")
    @app_commands.describe(text="Le texte", style="Style : formel, casual, persuasif...")
    async def rewrite(self, i: discord.Interaction, text: str, style: str = "clair et professionnel"):
        await i.response.defer()
        reply = await self._ask(f"Réécris en style {style} en français. Texte uniquement.", text, [])
        e = E.base("✍️ Réécriture")
        e.add_field(name="Original", value=text[:800], inline=False)
        e.add_field(name="Résultat", value=_clean_ai_reply(reply)[:800], inline=False)
        await i.followup.send(embed=e)

    @app_commands.command(name="resetai", description="Réinitialise ta conversation avec Kryvoox")
    async def resetai(self, i: discord.Interaction):
        _history.pop(i.user.id, None)
        await i.response.send_message(embed=E.success("Historique effacé."), ephemeral=True)


async def setup(bot):
    await bot.add_cog(AI(bot))
