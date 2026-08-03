import asyncio
import logging
import datetime
import random
import time
from typing import Dict, List, Optional, Any, Callable
import dataclasses

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

logger = logging.getLogger("discord.bot.kryvoox.moderation.v7")

# ==========================================
# CONSTANTES ET VALIDATION
# ==========================================

MAX_REASON_LENGTH = 512          # Discord limite à 512 chars les reasons d'audit
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MUTED_ROLE_NAME    = "Muted"

# ==========================================
# INFRASTRUCTURE DE MONITORING
# ==========================================

class PrometheusMetrics:
    def __init__(self):
        self._counters: Dict[str, int]   = {}
        self._histograms: Dict[str, list] = {}

    def increment(self, metric: str, labels: Dict[str, str]):
        key = f"{metric}:{tuple(sorted(labels.items()))}"
        self._counters[key] = self._counters.get(key, 0) + 1

    def observe(self, metric: str, value: float, labels: Dict[str, str]):
        # En prod : pousse vers Prometheus pushgateway ou OpenTelemetry
        key = f"{metric}:{tuple(sorted(labels.items()))}"
        self._histograms.setdefault(key, []).append(value)
        # Log les latences anormales (>2s)
        if value > 2.0:
            logger.warning(f"[PERF] {metric} {labels} = {value:.3f}s (seuil dépassé)")

metrics = PrometheusMetrics()


@dataclasses.dataclass
class AuditLogEntry:
    guild_id:     int
    moderator_id: int
    target_id:    int
    action:       str
    reason:       str
    timestamp:    datetime.datetime
    shard_id:     int
    metadata:     Dict[str, Any] = dataclasses.field(default_factory=dict)


class DatabasePoolInterface:
    """Interface asyncpg.Pool — remplace par ta vraie implémentation en prod."""
    async def execute(self, query: str, *args) -> Any:            pass
    async def fetch(self,   query: str, *args) -> List[Dict]:     return []
    async def fetchrow(self,query: str, *args) -> Optional[Dict]: return None
    def transaction(self): return _AsyncTransactionContext()


class _AsyncTransactionContext:
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc_val, exc_tb): pass


# ==========================================
# UTILITAIRES DE RÉSILIENCE RÉSEAU
# ==========================================

async def run_with_retry(
    coro_func: Callable,
    *args,
    max_retries: int = 3,
    base_delay: float = 0.5,
    timeout: float = 10.0,   # FIX V8-5 : configurable — 10s par défaut pour les grosses guildes
    **kwargs
):
    """
    Backoff exponentiel + Full Jitter.
    FIX : capture aiohttp.ClientError, ConnectionResetError, OSError.
    FIX V8-5 : timeout configurable (create_role sur grosse guild peut dépasser 4s).
    """
    last_exc: Exception = RuntimeError("Aucune tentative effectuée")

    for attempt in range(1, max_retries + 1):
        try:
            async with asyncio.timeout(timeout):
                return await coro_func(*args, **kwargs)

        except (discord.HTTPException, discord.GatewayNotFound, discord.DiscordServerError) as e:
            status   = getattr(e, "status", 500)
            last_exc = e
            if status not in RETRYABLE_STATUSES:
                raise  # 403/400 → inutile de retry
            if attempt == max_retries:
                metrics.increment("bot_network_failures_total", {"status": str(status)})
                raise

        # FIX : erreurs réseau bas-niveau + aiohttp
        except (ConnectionResetError, ConnectionError, OSError,
                aiohttp.ClientConnectionError, aiohttp.ServerDisconnectedError) as e:
            last_exc = e
            if attempt == max_retries:
                metrics.increment("bot_network_failures_total", {"status": "network"})
                raise

        except asyncio.TimeoutError as e:
            last_exc = e
            if attempt == max_retries:
                metrics.increment("bot_timeout_failures_total", {})
                raise

        delay = random.uniform(0, min(8.0, base_delay * (2 ** attempt)))
        logger.warning(f"Retry {attempt}/{max_retries} dans {delay:.2f}s — {last_exc}")
        await asyncio.sleep(delay)

    raise last_exc


# ==========================================
# HELPERS
# ==========================================

def truncate_reason(reason: str) -> str:
    """FIX : tronque les raisons trop longues pour l'API Discord (max 512 chars)."""
    if len(reason) > MAX_REASON_LENGTH:
        return reason[:MAX_REASON_LENGTH - 3] + "..."
    return reason


def get_member(interaction: discord.Interaction) -> Optional[discord.Member]:
    """
    FIX bug #1 : interaction.user peut être discord.User en DM.
    Retourne None si on n'est pas dans un guild context.
    """
    user = interaction.user
    if isinstance(user, discord.Member):
        return user
    # Fallback : tenter de récupérer le Member depuis le cache de la guild
    if interaction.guild:
        return interaction.guild.get_member(user.id)
    return None


# ==========================================
# COG DE MODÉRATION V7
# ==========================================

class GlobalScaleModeration(commands.Cog):

    def __init__(self, bot: commands.Bot, db_pool: Optional[DatabasePoolInterface] = None):
        self.bot = bot
        self.db  = db_pool or DatabasePoolInterface()

        # Cache rôle Muted : {guild_id: discord.Role}
        self._muted_roles_cache:   Dict[int, discord.Role] = {}
        self._db_locks:            Dict[int, asyncio.Lock] = {}
        self._role_creation_locks: Dict[int, asyncio.Lock] = {}

        # Sémaphore strict — 6 appels API concurrents max
        self._api_semaphore = asyncio.Semaphore(6)

        # FIX V8-8 : file de retry pour les audit logs en échec (max 500 entrées)
        self._audit_retry_queue: asyncio.Queue[AuditLogEntry] = asyncio.Queue(maxsize=500)

        # FIX V8-10 : verrous par (guild_id, member_id) pour éviter les double-mutes
        self._member_action_locks: Dict[tuple, asyncio.Lock] = {}

        self.check_expired_mutes.start()
        self._flush_audit_retry_queue.start()

    def cog_unload(self):
        self.check_expired_mutes.cancel()
        self._flush_audit_retry_queue.cancel()

    # ── Verrous ───────────────────────────────────────────────────────────────

    def _get_db_lock(self, guild_id: int) -> asyncio.Lock:
        return self._db_locks.setdefault(guild_id, asyncio.Lock())

    def _get_creation_lock(self, guild_id: int) -> asyncio.Lock:
        return self._role_creation_locks.setdefault(guild_id, asyncio.Lock())

    def _get_member_lock(self, guild_id: int, member_id: int) -> asyncio.Lock:
        """FIX V8-10 : verrou par (guild_id, member_id) pour éviter les races."""
        key = (guild_id, member_id)
        return self._member_action_locks.setdefault(key, asyncio.Lock())

    def _cleanup_stale_locks(self):
        """
        FIX V8-9 : supprime les locks des guildes dont le bot n'est plus membre.
        Appelé périodiquement pour éviter la fuite mémoire.
        """
        active_guild_ids = {g.id for g in self.bot.guilds}
        for d in (self._db_locks, self._role_creation_locks, self._muted_roles_cache):
            stale = [k for k in d if k not in active_guild_ids]
            for k in stale:
                d.pop(k, None)
        # Nettoyage verrous membres (guild_id non actif)
        stale_member_keys = [k for k in self._member_action_locks if k[0] not in active_guild_ids]
        for k in stale_member_keys:
            self._member_action_locks.pop(k, None)
        if stale or stale_member_keys:
            logger.debug(f"_cleanup_stale_locks : {len(stale)} guildes + {len(stale_member_keys)} membres purgés.")

    # ── Audit log ─────────────────────────────────────────────────────────────

    # File d'attente locale pour les audit logs qui échouent
    _audit_retry_queue: "asyncio.Queue[AuditLogEntry]" = None  # initialisé dans __init__

    async def _write_audit_log(self, entry: AuditLogEntry):
        """
        FIX V8-8 : en cas d'échec DB, l'entrée est mise en file de retry
        plutôt que perdue silencieusement.
        """
        query = """
            INSERT INTO audit_logs
                (guild_id, moderator_id, target_id, action, reason, timestamp, shard_id, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """
        try:
            await self.db.execute(
                query,
                entry.guild_id, entry.moderator_id, entry.target_id,
                entry.action, entry.reason, entry.timestamp,
                entry.shard_id, entry.metadata
            )
        except Exception:
            logger.exception(
                f"CRITICAL: Échec Audit Log [Guild: {entry.guild_id}] "
                f"action={entry.action} — mise en file de retry."
            )
            if self._audit_retry_queue:
                try:
                    self._audit_retry_queue.put_nowait(entry)
                except asyncio.QueueFull:
                    logger.error("File audit saturée — entrée définitivement perdue.")

    @tasks.loop(seconds=60.0)
    async def _flush_audit_retry_queue(self):
        """Réessaie d'écrire les audit logs en échec, par batch."""
        if not self._audit_retry_queue or self._audit_retry_queue.empty():
            return
        batch: list[AuditLogEntry] = []
        while not self._audit_retry_queue.empty():
            try:
                batch.append(self._audit_retry_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        logger.info(f"Retry audit log — {len(batch)} entrée(s).")
        for entry in batch:
            try:
                await self.db.execute(
                    """INSERT INTO audit_logs
                       (guild_id, moderator_id, target_id, action, reason, timestamp, shard_id, metadata)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                    entry.guild_id, entry.moderator_id, entry.target_id,
                    entry.action, entry.reason, entry.timestamp,
                    entry.shard_id, entry.metadata
                )
            except Exception:
                # Remet en queue si ça échoue encore
                try: self._audit_retry_queue.put_nowait(entry)
                except asyncio.QueueFull: pass

    @_flush_audit_retry_queue.before_loop
    async def _before_flush_audit(self):
        await self.bot.wait_until_ready()

    # ── Réponse sécurisée ─────────────────────────────────────────────────────

    async def _reply(
        self,
        interaction: discord.Interaction,
        message: str,
        ephemeral: bool = True,
        embed: Optional[discord.Embed] = None
    ):
        kwargs: Dict[str, Any] = {"ephemeral": ephemeral}
        if embed:
            kwargs["embed"] = embed
        else:
            kwargs["content"] = message
        try:
            if interaction.response.is_done():
                await interaction.followup.send(**kwargs)
            else:
                await interaction.response.send_message(**kwargs)
        except discord.NotFound:
            # Interaction expirée (> 15 min) — on ne peut plus répondre
            logger.debug(f"_reply() interaction expirée (id={interaction.id}) — ignoré.")
        except discord.HTTPException as e:
            logger.warning(f"_reply() HTTPException (interaction={interaction.id}): {e}")

    # ── Vérification permissions bot + hiérarchie ─────────────────────────────

    async def _check_bot_perms(
        self,
        interaction: discord.Interaction,
        perms: Dict[str, bool],
        target: Optional[discord.Member] = None
    ) -> bool:
        if not interaction.guild:
            return False
        bot_member = interaction.guild.get_member(self.bot.user.id)
        if not bot_member:
            return False

        missing = [p for p, req in perms.items() if req and not getattr(bot_member.guild_permissions, p, False)]
        if missing:
            await self._reply(
                interaction,
                f"❌ Permissions manquantes : `{', '.join(p.replace('_',' ').title() for p in missing)}`"
            )
            return False

        if target:
            if bot_member.top_role <= target.top_role:
                await self._reply(interaction, "❌ Mon rôle est trop bas dans la hiérarchie.")
                return False
            if target.id == interaction.guild.owner_id:
                await self._reply(interaction, "❌ Impossible d'agir sur le propriétaire du serveur.")
                return False

        return True

    def _check_user_hierarchy(
        self,
        interaction: discord.Interaction,
        target: discord.Member
    ) -> bool:
        """
        FIX bug #1 : utilise get_member() pour garantir discord.Member.
        FIX bug #10 : le propriétaire du serveur est toujours autorisé.
        """
        moderator = get_member(interaction)  # Garantit discord.Member ou None
        if moderator is None:
            return False

        # Le propriétaire est toujours autorisé, peu importe son rôle
        if moderator.id == interaction.guild.owner_id:
            return True
        if moderator.guild_permissions.administrator:
            return True

        return moderator.top_role > target.top_role

    # ==========================================
    # CACHE MUTED ROLE — LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Purge mémoire complète quand le bot quitte un serveur."""
        self._muted_roles_cache.pop(guild.id, None)
        self._db_locks.pop(guild.id, None)
        self._role_creation_locks.pop(guild.id, None)
        logger.info(f"RAM purgée — guild {guild.id}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """FIX : invalidation exacte par ID (pas par nom)."""
        cached = self._muted_roles_cache.get(role.guild.id)
        if cached and cached.id == role.id:
            self._muted_roles_cache.pop(role.guild.id, None)
            logger.info(f"Cache Muted invalidé (suppression) — guild {role.guild.id}")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        """
        FIX V8-3 : si un admin crée manuellement un rôle "Muted" alors que le cache
        pointe vers un autre rôle, on invalide pour forcer la resynchronisation.
        """
        if role.name != MUTED_ROLE_NAME:
            return
        cached = self._muted_roles_cache.get(role.guild.id)
        if cached and cached.id != role.id:
            # Deux rôles "Muted" coexistent — on garde le plus récent (celui créé par Discord)
            # et on invalide le cache pour que le prochain appel rerésolve proprement.
            self._muted_roles_cache.pop(role.guild.id, None)
            logger.warning(
                f"Rôle Muted dupliqué détecté — cache invalidé (guild={role.guild.id}). "
                f"Ancien id={cached.id} | Nouveau id={role.id}"
            )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """
        FIX bug #7 : invalide aussi si les permissions changent (pas seulement le nom).
        """
        cached = self._muted_roles_cache.get(after.guild.id)
        if not cached or cached.id != before.id:
            return
        name_changed  = after.name != MUTED_ROLE_NAME
        perms_changed = before.permissions != after.permissions
        if name_changed or perms_changed:
            self._muted_roles_cache.pop(after.guild.id, None)
            logger.info(
                f"Cache Muted invalidé "
                f"({'nom' if name_changed else 'permissions'}) — guild {after.guild.id}"
            )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """
        FIX bug #8 : applique automatiquement les perms Muted aux nouveaux salons.
        FIX V8-1  : tâche supervisée — les exceptions sont loggées, jamais perdues.
        """
        muted_role = self._muted_roles_cache.get(channel.guild.id)
        if muted_role:
            asyncio.create_task(self._supervised_apply_perms(channel, muted_role))

    async def _supervised_apply_perms(
        self,
        channel: discord.abc.GuildChannel,
        muted_role: discord.Role
    ):
        """Wrapper supervisé autour de _apply_muted_perms — toute exception est loggée."""
        try:
            await self._apply_muted_perms(channel, muted_role)
        except Exception:
            logger.exception(
                f"_apply_muted_perms non géré — channel={channel.id} guild={channel.guild.id}"
            )

    # ── Application permissions Muted ─────────────────────────────────────────

    async def _apply_muted_perms(
        self,
        channel: discord.abc.GuildChannel,
        muted_role: discord.Role
    ):
        async with self._api_semaphore:
            try:
                ow = channel.overwrites_for(muted_role)
                already = all([
                    ow.send_messages            is False,
                    ow.add_reactions            is False,
                    ow.create_public_threads    is False,
                    ow.create_private_threads   is False,
                    ow.send_messages_in_threads is False,
                    ow.connect                  is False,
                ])
                if already:
                    return
                ow.send_messages            = False
                ow.add_reactions            = False
                ow.create_public_threads    = False
                ow.create_private_threads   = False
                ow.send_messages_in_threads = False
                ow.connect                  = False
                await run_with_retry(
                    channel.set_permissions, muted_role,
                    overwrite=ow, reason="Kryvoox — Alignement rôle Muted",
                    timeout=8.0
                )
            except discord.Forbidden:
                pass

    async def _get_or_create_muted_role(
        self,
        guild: discord.Guild
    ) -> Optional[discord.Role]:
        # Fast path — FIX V8-4 : on vérifie que le rôle en cache existe encore
        if guild.id in self._muted_roles_cache:
            cached = self._muted_roles_cache[guild.id]
            if guild.get_role(cached.id) is not None:
                return cached
            # Rôle disparu (supprimé sans événement reçu — ex: reconnexion)
            logger.warning(
                f"Rôle Muted en cache introuvable dans la guild {guild.id} "
                f"(id={cached.id}) — invalidation."
            )
            self._muted_roles_cache.pop(guild.id, None)

        # Double-checked locking
        async with self._get_creation_lock(guild.id):
            if guild.id in self._muted_roles_cache:
                return self._muted_roles_cache[guild.id]

            muted_role = discord.utils.get(guild.roles, name=MUTED_ROLE_NAME)

            if not muted_role:
                try:
                    muted_role = await run_with_retry(
                        guild.create_role,
                        name=MUTED_ROLE_NAME,
                        color=discord.Color.dark_gray(),
                        reason="Kryvoox — Création rôle Muted",
                        timeout=30.0   # Grosse guild — création peut être lente
                    )
                except discord.HTTPException:
                    logger.error(f"Impossible de créer le rôle Muted — guild {guild.id}")
                    return None

            # FIX #6 : réappliquer les perms même si le rôle existait déjà
            # (un admin peut avoir créé un rôle Muted sans les bonnes permissions)
            await asyncio.gather(
                *[self._apply_muted_perms(ch, muted_role) for ch in guild.channels],
                return_exceptions=True
            )

            # FIX bug #3 : on sauvegarde l'ID en DB pour éviter les doublons
            try:
                await self.db.execute(
                    "INSERT INTO guild_config (guild_id, muted_role_id) VALUES ($1, $2) "
                    "ON CONFLICT (guild_id) DO UPDATE SET muted_role_id = EXCLUDED.muted_role_id",
                    guild.id, muted_role.id
                )
            except Exception:
                pass  # Non bloquant — le cache reste valide

            self._muted_roles_cache[guild.id] = muted_role
            return muted_role

    async def _restore_muted_roles_on_startup(self):
        """
        FIX point fragile : recharge les rôles Muted depuis la DB au démarrage.
        Évite que les mutes créés pendant un downtime soient perdus.
        """
        try:
            rows = await self.db.fetch("SELECT guild_id, muted_role_id FROM guild_config")
            for row in rows:
                guild = self.bot.get_guild(row["guild_id"])
                if not guild:
                    continue
                role = guild.get_role(row["muted_role_id"])
                if role:
                    self._muted_roles_cache[guild.id] = role
            logger.info(f"Rôles Muted restaurés depuis DB ({len(rows)} guilds)")
        except Exception:
            logger.warning("Impossible de restaurer les rôles Muted depuis la DB (table absente ?)")

    # ==========================================
    # COMMANDES DE MODÉRATION
    # ==========================================

    @app_commands.command(name="ban", description="Bannit définitivement un membre")
    @app_commands.describe(
        member="Le membre à bannir",
        reason="Raison du bannissement",
        delete_messages_days="Jours de messages supprimés (0-7)"
    )
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.cooldown(1, 2.0, key=lambda i: i.user.id)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
        # FIX point fragile : validation d'arguments via Range
        delete_messages_days: app_commands.Range[int, 0, 7] = 0
    ):
        t0 = time.perf_counter()

        # FIX #3 : guard guild is None
        if interaction.guild is None:
            return await self._reply(interaction, "❌ Cette commande doit être utilisée dans un serveur.")

        if not await self._check_bot_perms(interaction, {"ban_members": True}, target=member):
            return
        if not self._check_user_hierarchy(interaction, member):
            return await self._reply(interaction, "❌ Ton rang est insuffisant pour bannir ce membre.")

        reason = truncate_reason(reason)
        metrics.increment("moderation_commands_total", {"action": "ban", "guild": str(interaction.guild_id)})

        try:
            async with self._api_semaphore:
                await run_with_retry(
                    member.ban,
                    delete_message_seconds=delete_messages_days * 86400,
                    reason=f"[Kryvoox] {interaction.user}: {reason}"
                )
            await self._write_audit_log(AuditLogEntry(
                interaction.guild_id, interaction.user.id, member.id,
                "BAN", reason,
                datetime.datetime.now(datetime.timezone.utc),
                interaction.guild.shard_id or 0
            ))
            await self._reply(
                interaction,
                f"🔨 **{member.display_name}** banni.\n**Raison :** {reason}",
                ephemeral=False
            )
        except discord.Forbidden:
            await self._reply(interaction, "❌ Permission refusée (403) — vérifie les permissions du bot.")
        except Exception as e:
            metrics.increment("moderation_errors_total", {"action": "ban"})
            logger.error(f"Erreur ban {member.id} / {interaction.guild_id}: {e}", exc_info=True)
            await self._reply(interaction, "⚠️ Bannissement échoué après plusieurs tentatives.")
        finally:
            metrics.observe("command_latency_seconds", time.perf_counter() - t0, {"action": "ban"})

    @app_commands.command(name="mute", description="Mute un membre temporairement ou définitivement")
    @app_commands.describe(
        member="Le membre",
        reason="Raison du mute",
        minutes="Durée en minutes (laisse vide = permanent)"
    )
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.checks.cooldown(1, 2.0, key=lambda i: i.user.id)
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
        # FIX point fragile : validation via Range
        minutes: Optional[app_commands.Range[int, 1, 525600]] = None  # max 1 an
    ):
        t0 = time.perf_counter()

        # FIX #3 : guard guild is None
        if interaction.guild is None:
            return await self._reply(interaction, "❌ Cette commande doit être utilisée dans un serveur.")

        # Check permissions bot SANS vérification hiérarchie avec la cible —
        # pour /mute on vérifie la hiérarchie APRÈS avoir le rôle Muted (plus bas dans la liste)
        if not await self._check_bot_perms(interaction, {"manage_roles": True}):
            return
        if not self._check_user_hierarchy(interaction, member):
            return await self._reply(interaction, "❌ Hiérarchie invalide.")

        await interaction.response.defer(ephemeral=True)

        muted_role = await self._get_or_create_muted_role(interaction.guild)
        if muted_role is None:
            return await self._reply(interaction, "❌ Impossible de créer le rôle Muted.")

        # Vérification hiérarchie bot vs cible APRÈS avoir le rôle Muted
        # Le rôle Muted doit être sous le rôle du bot mais au-dessus de @everyone
        bot_member = interaction.guild.get_member(self.bot.user.id)
        if bot_member and muted_role and bot_member.top_role <= muted_role:
            await self._reply(
                interaction,
                f"⚙️ Configuration requise : mon rôle doit être **au-dessus** du rôle `{MUTED_ROLE_NAME}` "
                f"dans **Paramètres du serveur → Rôles**."
            )
            return
        if not muted_role:
            return await self._reply(interaction, "❌ Impossible de créer ou trouver le rôle Muted.")

        reason = truncate_reason(reason)
        metrics.increment("moderation_commands_total", {"action": "mute", "guild": str(interaction.guild_id)})

        # FIX V8-10 : verrou unique par membre — le check ET l'action sont dans le même bloc
        try:
            async with self._get_member_lock(interaction.guild_id, member.id):
                # Rechargement frais après acquisition du verrou (sécurisé)
                try:
                    member = await interaction.guild.fetch_member(member.id)
                except discord.NotFound:
                    return await self._reply(interaction, "❌ Membre introuvable sur le serveur.")
                except discord.HTTPException:
                    member = interaction.guild.get_member(member.id) or member

                if muted_role in member.roles:
                    return await self._reply(interaction, f"⚠️ **{member.display_name}** est déjà muté.")

                async with self._api_semaphore:
                    await run_with_retry(
                        member.add_roles, muted_role,
                        reason=f"[Kryvoox] {interaction.user}: {reason}"
                    )

            expire_at = None
            if minutes:
                expire_at = (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(minutes=minutes)
                )

            async with self._get_db_lock(interaction.guild_id):
                async with self.db.transaction():
                    await self.db.execute(
                        """
                        INSERT INTO persistent_mutes (guild_id, member_id, role_id, expire_at)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (guild_id, member_id) DO UPDATE SET expire_at = EXCLUDED.expire_at
                        """,
                        interaction.guild_id, member.id, muted_role.id, expire_at
                    )

            await self._write_audit_log(AuditLogEntry(
                interaction.guild_id, interaction.user.id, member.id,
                "MUTE", f"{minutes or 'Permanent'} min | {reason}",
                datetime.datetime.now(datetime.timezone.utc),
                interaction.guild.shard_id or 0
            ))

            dur = f"**{minutes} minute{'s' if minutes > 1 else ''}**" if minutes else "**permanent**"
            await self._reply(
                interaction,
                f"🔇 **{member.display_name}** muté {dur}.\n**Raison :** {reason}",
                ephemeral=False
            )

        except discord.Forbidden:
            await self._reply(interaction, "❌ Permission refusée — mon rôle est peut-être sous le rôle Muted.")
        except Exception as e:
            metrics.increment("moderation_errors_total", {"action": "mute"})
            logger.error(f"Erreur mute {member.id}: {e}", exc_info=True)
            await self._reply(interaction, "⚠️ Le mute a échoué.")
        finally:
            metrics.observe("command_latency_seconds", time.perf_counter() - t0, {"action": "mute"})

    @app_commands.command(name="unmute", description="Retire le mute d'un membre")
    @app_commands.default_permissions(manage_roles=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        # FIX #3 : guard guild is None
        if interaction.guild is None:
            return await self._reply(interaction, "❌ Cette commande doit être utilisée dans un serveur.")
        # FIX #2 : vérification hiérarchie dans unmute
        if not await self._check_bot_perms(interaction, {"manage_roles": True}, target=member):
            return
        if not self._check_user_hierarchy(interaction, member):
            return await self._reply(interaction, "❌ Ton rang est insuffisant pour unmute ce membre.")

        muted_role = (
            self._muted_roles_cache.get(interaction.guild.id)
            or discord.utils.get(interaction.guild.roles, name=MUTED_ROLE_NAME)
        )
        if not muted_role or muted_role not in member.roles:
            return await self._reply(interaction, f"⚠️ **{member.display_name}** n'est pas muté.")
        try:
            async with self._api_semaphore:
                await run_with_retry(
                    member.remove_roles, muted_role,
                    reason=f"[Kryvoox] Unmute par {interaction.user}"
                )
            async with self._get_db_lock(interaction.guild_id):
                async with self.db.transaction():
                    await self.db.execute(
                        "DELETE FROM persistent_mutes WHERE guild_id=$1 AND member_id=$2",
                        interaction.guild_id, member.id
                    )
            await self._reply(
                interaction,
                f"🔊 **{member.display_name}** unmute.",
                ephemeral=False
            )
        except Exception as e:
            await self._reply(interaction, f"❌ Erreur : {e}")

    # ==========================================
    # BACKGROUND TASK — DÉMUTE AUTOMATIQUE
    # ==========================================

    async def _execute_single_unmute(
        self,
        guild_id: int,
        member_id: int,
        my_shard_ids: List[int]
    ):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            # FIX bug #9 : si la guild n'est pas en cache, on ne supprime PAS la ligne SQL.
            # Le mute sera retraité au prochain cycle ou à la reconnexion.
            return

        if guild.shard_id is not None and guild.shard_id not in my_shard_ids:
            return

        muted_role = (
            self._muted_roles_cache.get(guild.id)
            or discord.utils.get(guild.roles, name=MUTED_ROLE_NAME)
        )

        # FIX V8-7 : get_member rate le membre s'il n'est pas dans le cache Discord.
        # On tente fetch_member (appel API) avant de supprimer la ligne SQL.
        member = guild.get_member(member_id)
        if member is None:
            try:
                member = await guild.fetch_member(member_id)
            except discord.NotFound:
                # Le membre a quitté le serveur — on supprime la ligne proprement
                pass
            except discord.HTTPException:
                # Erreur API transitoire — on reporte à la prochaine itération
                logger.warning(f"fetch_member({member_id}) échoué — report au prochain cycle.")
                return

        if member and muted_role and muted_role in member.roles:
            try:
                async with self._api_semaphore:
                    await run_with_retry(
                        member.remove_roles, muted_role,
                        reason="[Kryvoox] Expiration du mute temporaire"
                    )
            except discord.HTTPException:
                pass

        # Suppression SQL — membre parti ou mute retiré avec succès
        async with self._get_db_lock(guild_id):
            async with self.db.transaction():
                await self.db.execute(
                    "DELETE FROM persistent_mutes WHERE guild_id=$1 AND member_id=$2",
                    guild_id, member_id
                )

    _cleanup_counter: int = 0

    @tasks.loop(seconds=15.0)
    async def check_expired_mutes(self):
        """Scan paginé index-friendly — batch de 100 entrées."""
        # FIX V8-9 : nettoyage mémoire toutes les ~150s (10 cycles)
        self._cleanup_counter = getattr(self, "_cleanup_counter", 0) + 1
        if self._cleanup_counter % 10 == 0:
            self._cleanup_stale_locks()

        now = datetime.datetime.now(datetime.timezone.utc)
        try:
            expired = await self.db.fetch(
                """
                SELECT guild_id, member_id FROM persistent_mutes
                WHERE expire_at IS NOT NULL AND expire_at <= $1
                ORDER BY expire_at ASC
                LIMIT 100
                """,
                now
            )
        except Exception:
            logger.error("Scan persistent_mutes échoué (DB surchargée ?)")
            return

        if not expired:
            return

        my_shard_ids = list(getattr(self.bot, "shard_ids", None) or [0])
        await asyncio.gather(
            *[self._execute_single_unmute(r["guild_id"], r["member_id"], my_shard_ids)
              for r in expired],
            return_exceptions=True
        )

    @check_expired_mutes.before_loop
    async def before_check_expired_mutes(self):
        await self.bot.wait_until_ready()
        await self._restore_muted_roles_on_startup()

    # ── Gestion globale des erreurs ───────────────────────────────────────────

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CommandOnCooldown):
            await self._reply(
                interaction,
                f"⏳ Cooldown. Réessaie dans `{error.retry_after:.1f}s`.",
                ephemeral=True
            )
        else:
            logger.error(f"Erreur commande: {error}", exc_info=error)
            await self._reply(interaction, "❌ Erreur interne du système de modération.")


# ── Setup ──────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot, db_pool: Optional[DatabasePoolInterface] = None):
    await bot.add_cog(GlobalScaleModeration(bot, db_pool))