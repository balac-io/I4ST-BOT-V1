"""
Kryvoox Database — SQLite
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = "data/kryvoox.db"
OLD_JSON = "data/kryvoox.json"

def _get_conn() -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def _db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id         TEXT PRIMARY KEY,
        bio             TEXT,
        coins           INTEGER DEFAULT 0,
        bank            INTEGER DEFAULT 0,
        xp              INTEGER DEFAULT 0,
        level           INTEGER DEFAULT 1,
        inventory       TEXT DEFAULT '[]',
        last_daily      TEXT,
        last_work       TEXT,
        total_msgs      INTEGER DEFAULT 0,
        premium         INTEGER DEFAULT 0,
        premium_until   TEXT,
        premium_reminded TEXT,
        daily_streak    INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS guilds (
        guild_id        TEXT PRIMARY KEY,
        prefix          TEXT DEFAULT '/',
        log_channel     INTEGER,
        welcome_channel INTEGER,
        goodbye_channel INTEGER,
        welcome_msg     TEXT DEFAULT 'Bienvenue {user} sur {server} !',
        goodbye_msg     TEXT DEFAULT 'Au revoir {user}.',
        autorole        INTEGER,
        verify_role     INTEGER,
        antiinvite      INTEGER DEFAULT 0,
        antilink        INTEGER DEFAULT 0,
        antispam        INTEGER DEFAULT 0,
        antibot         INTEGER DEFAULT 0,
        antinuke        INTEGER DEFAULT 0,
        shop            TEXT DEFAULT '{}',
        counters        TEXT DEFAULT '{}',
        ticket_category INTEGER,
        level_roles     TEXT DEFAULT '{}',
        welcome_image   TEXT
    );

    CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL, user_id TEXT NOT NULL,
        reason TEXT, mod TEXT, date TEXT, warn_id INTEGER
    );

    CREATE TABLE IF NOT EXISTS tickets (
        guild_id TEXT NOT NULL, ticket_id TEXT NOT NULL,
        channel_id INTEGER, user_id INTEGER, category TEXT, status TEXT DEFAULT 'open',
        PRIMARY KEY (guild_id, ticket_id)
    );

    CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings(guild_id, user_id);
    CREATE INDEX IF NOT EXISTS idx_users_xp ON users(xp DESC);
    """)
    for sql in [
        "ALTER TABLE users ADD COLUMN premium INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN premium_until TEXT",
        "ALTER TABLE users ADD COLUMN premium_reminded TEXT",
        "ALTER TABLE users ADD COLUMN daily_streak INTEGER DEFAULT 0",
        "ALTER TABLE guilds ADD COLUMN level_roles TEXT DEFAULT '{}'",
        "ALTER TABLE guilds ADD COLUMN welcome_image TEXT",
    ]:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass

def _migrate_from_json(conn: sqlite3.Connection):
    if not os.path.exists(OLD_JSON):
        return
    try:
        with open(OLD_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    for uid, u in data.get("users", {}).items():
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, bio, coins, bank, xp, level, inventory, last_daily, last_work, total_msgs, premium, premium_until, premium_reminded, daily_streak) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(uid), u.get("bio"), u.get("coins", 0), u.get("bank", 0), u.get("xp", 0), u.get("level", 1),
             json.dumps(u.get("inventory", [])), u.get("last_daily"), u.get("last_work"), u.get("total_msgs", 0),
             1 if u.get("premium") else 0, u.get("premium_until"), u.get("premium_reminded"), u.get("daily_streak", 0))
        )
    try:
        os.rename(OLD_JSON, OLD_JSON + ".migrated")
    except Exception:
        pass

def _boot():
    with _db() as conn:
        _init_tables(conn)
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0 and os.path.exists(OLD_JSON):
            _migrate_from_json(conn)

_boot()

def _row_to_user(row: sqlite3.Row) -> dict:
    if row is None:
        return None
    keys = row.keys()
    return {
        "bio": row["bio"], "coins": row["coins"] or 0, "bank": row["bank"] or 0,
        "xp": row["xp"] or 0, "level": row["level"] or 1,
        "inventory": json.loads(row["inventory"] or "[]"),
        "last_daily": row["last_daily"], "last_work": row["last_work"],
        "total_msgs": row["total_msgs"] or 0,
        "premium": bool(row["premium"]) if "premium" in keys else False,
        "premium_until": row["premium_until"] if "premium_until" in keys else None,
        "premium_reminded": row["premium_reminded"] if "premium_reminded" in keys else None,
        "daily_streak": (row["daily_streak"] or 0) if "daily_streak" in keys else 0,
    }

def _row_to_guild(row: sqlite3.Row) -> dict:
    if row is None:
        return None
    keys = row.keys()
    return {
        "prefix": row["prefix"] or "/", "log_channel": row["log_channel"],
        "welcome_channel": row["welcome_channel"], "goodbye_channel": row["goodbye_channel"],
        "welcome_msg": row["welcome_msg"] or "Bienvenue {user} sur {server} !",
        "goodbye_msg": row["goodbye_msg"] or "Au revoir {user}.",
        "autorole": row["autorole"], "verify_role": row["verify_role"],
        "antiinvite": bool(row["antiinvite"]), "antilink": bool(row["antilink"]),
        "antispam": bool(row["antispam"]), "antibot": bool(row["antibot"]),
        "antinuke": bool(row["antinuke"]),
        "shop": json.loads(row["shop"] or "{}"), "counters": json.loads(row["counters"] or "{}"),
        "ticket_category": row["ticket_category"],
        "level_roles": json.loads(row["level_roles"] or "{}") if "level_roles" in keys else {},
        "welcome_image": row["welcome_image"] if "welcome_image" in keys else None,
    }

def get_user(user_id: int) -> dict:
    uid = str(user_id)
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()
        if row:
            return _row_to_user(row)
        default = {"bio": None, "coins": 0, "bank": 0, "xp": 0, "level": 1, "inventory": [],
                   "last_daily": None, "last_work": None, "total_msgs": 0, "premium": False,
                   "premium_until": None, "premium_reminded": None, "daily_streak": 0}
        conn.execute(
            "INSERT INTO users (user_id, bio, coins, bank, xp, level, inventory, last_daily, last_work, total_msgs, premium, premium_until, premium_reminded, daily_streak) VALUES (?, NULL, 0, 0, 0, 1, '[]', NULL, NULL, 0, 0, NULL, NULL, 0)",
            (uid,))
        return default

def save_user(user_id: int, data: dict):
    uid = str(user_id)
    with _db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO users
            (user_id, bio, coins, bank, xp, level, inventory, last_daily, last_work, total_msgs, premium, premium_until, premium_reminded, daily_streak)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            uid, data.get("bio"), data.get("coins", 0), data.get("bank", 0),
            data.get("xp", 0), data.get("level", 1), json.dumps(data.get("inventory", [])),
            data.get("last_daily"), data.get("last_work"), data.get("total_msgs", 0),
            1 if data.get("premium") else 0, data.get("premium_until"), data.get("premium_reminded"),
            data.get("daily_streak", 0),
        ))

def is_premium(user_id: int) -> bool:
    u = get_user(user_id)
    if not u.get("premium"):
        return False
    until = u.get("premium_until")
    if not until:
        return True
    try:
        exp = datetime.fromisoformat(until)
        if datetime.utcnow() > exp:
            u["premium"] = False
            u["premium_until"] = None
            u["premium_reminded"] = None
            save_user(user_id, u)
            return False
        return True
    except Exception:
        return bool(u.get("premium"))

def set_premium(user_id: int, days: int | None = None):
    u = get_user(user_id)
    u["premium"] = True
    u["premium_reminded"] = None
    u["premium_until"] = None if days is None else (datetime.utcnow() + timedelta(days=days)).isoformat()
    save_user(user_id, u)

def renew_premium(user_id: int, days: int):
    u = get_user(user_id)
    now = datetime.utcnow()
    if u.get("premium") and not u.get("premium_until"):
        return None
    base = now
    if u.get("premium") and u.get("premium_until"):
        try:
            current_exp = datetime.fromisoformat(u["premium_until"])
            if current_exp > now:
                base = current_exp
        except Exception:
            pass
    new_exp = base + timedelta(days=days)
    u["premium"] = True
    u["premium_until"] = new_exp.isoformat()
    u["premium_reminded"] = None
    save_user(user_id, u)
    return new_exp

def remove_premium(user_id: int):
    u = get_user(user_id)
    u["premium"] = False
    u["premium_until"] = None
    u["premium_reminded"] = None
    save_user(user_id, u)

def get_expiring_premiums(within_days: int = 3) -> list:
    now = datetime.utcnow()
    limit = now + timedelta(days=within_days)
    results = []
    with _db() as conn:
        rows = conn.execute("SELECT user_id, premium_until, premium_reminded FROM users WHERE premium = 1 AND premium_until IS NOT NULL").fetchall()
        for r in rows:
            try:
                exp = datetime.fromisoformat(r["premium_until"])
                if now < exp <= limit:
                    results.append((r["user_id"], r["premium_until"], (exp - now).days, r["premium_reminded"]))
            except Exception:
                continue
    return results

def get_expired_premiums() -> list:
    now = datetime.utcnow()
    results = []
    with _db() as conn:
        rows = conn.execute("SELECT user_id, premium_until FROM users WHERE premium = 1 AND premium_until IS NOT NULL").fetchall()
        for r in rows:
            try:
                if datetime.fromisoformat(r["premium_until"]) <= now:
                    results.append(r["user_id"])
            except Exception:
                continue
    return results

def mark_premium_reminded(user_id: int, tag: str):
    u = get_user(user_id)
    u["premium_reminded"] = tag
    save_user(user_id, u)

def get_guild(guild_id: int) -> dict:
    gid = str(guild_id)
    with _db() as conn:
        row = conn.execute("SELECT * FROM guilds WHERE guild_id = ?", (gid,)).fetchone()
        if row:
            return _row_to_guild(row)
        default = {"prefix": "/", "log_channel": None, "welcome_channel": None, "goodbye_channel": None,
                   "welcome_msg": "Bienvenue {user} sur {server} !", "goodbye_msg": "Au revoir {user}.",
                   "autorole": None, "verify_role": None, "antiinvite": False, "antilink": False,
                   "antispam": False, "antibot": False, "antinuke": False, "shop": {}, "counters": {},
                   "ticket_category": None, "level_roles": {}, "welcome_image": None}
        conn.execute("INSERT INTO guilds (guild_id, prefix, welcome_msg, goodbye_msg, antiinvite, antilink, antispam, antibot, antinuke, shop, counters, level_roles) VALUES (?, '/', ?, ?, 0, 0, 0, 0, 0, '{}', '{}', '{}')",
                     (gid, default["welcome_msg"], default["goodbye_msg"]))
        return default

def save_guild(guild_id: int, data: dict):
    gid = str(guild_id)
    with _db() as conn:
        conn.execute("""INSERT OR REPLACE INTO guilds
            (guild_id, prefix, log_channel, welcome_channel, goodbye_channel, welcome_msg, goodbye_msg,
             autorole, verify_role, antiinvite, antilink, antispam, antibot, antinuke,
             shop, counters, ticket_category, level_roles, welcome_image)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (gid, data.get("prefix", "/"), data.get("log_channel"), data.get("welcome_channel"),
             data.get("goodbye_channel"), data.get("welcome_msg", "Bienvenue {user} sur {server} !"),
             data.get("goodbye_msg", "Au revoir {user}."), data.get("autorole"), data.get("verify_role"),
             1 if data.get("antiinvite") else 0, 1 if data.get("antilink") else 0,
             1 if data.get("antispam") else 0, 1 if data.get("antibot") else 0,
             1 if data.get("antinuke") else 0, json.dumps(data.get("shop", {})),
             json.dumps(data.get("counters", {})), data.get("ticket_category"),
             json.dumps(data.get("level_roles", {})), data.get("welcome_image")))

def add_warning(guild_id: int, user_id: int, reason: str, mod: str) -> int:
    with _db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id))).fetchone()[0]
        new_id = count + 1
        conn.execute("INSERT INTO warnings (guild_id, user_id, reason, mod, date, warn_id) VALUES (?,?,?,?,?,?)",
                     (str(guild_id), str(user_id), reason, mod, datetime.now().strftime("%d/%m/%Y %H:%M"), new_id))
        return new_id

def get_warnings(guild_id: int, user_id: int) -> list:
    with _db() as conn:
        rows = conn.execute("SELECT reason, mod, date, warn_id as id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id", (str(guild_id), str(user_id))).fetchall()
        return [dict(r) for r in rows]

def clear_warnings(guild_id: int, user_id: int):
    with _db() as conn:
        conn.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id)))

def get_tickets(guild_id: int) -> dict:
    with _db() as conn:
        rows = conn.execute("SELECT ticket_id, channel_id, user_id, category, status FROM tickets WHERE guild_id = ?", (str(guild_id),)).fetchall()
        return {r["ticket_id"]: {"channel_id": r["channel_id"], "user_id": r["user_id"], "category": r["category"], "status": r["status"]} for r in rows}

def save_ticket(guild_id: int, ticket_id: str, data: dict):
    with _db() as conn:
        conn.execute("INSERT OR REPLACE INTO tickets (guild_id, ticket_id, channel_id, user_id, category, status) VALUES (?,?,?,?,?,?)",
                     (str(guild_id), str(ticket_id), data.get("channel_id"), data.get("user_id"), data.get("category"), data.get("status", "open")))

def delete_ticket(guild_id: int, ticket_id: str):
    with _db() as conn:
        conn.execute("DELETE FROM tickets WHERE guild_id = ? AND ticket_id = ?", (str(guild_id), str(ticket_id)))

def get_leaderboard_economy(limit: int = 10) -> list:
    with _db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY (coins + bank) DESC LIMIT ?", (limit,)).fetchall()
        return [(r["user_id"], _row_to_user(r)) for r in rows]

def get_leaderboard_xp(limit: int = 10) -> list:
    with _db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY xp DESC LIMIT ?", (limit,)).fetchall()
        return [(r["user_id"], _row_to_user(r)) for r in rows]

def raw() -> dict:
    with _db() as conn:
        return {
            "users": {r["user_id"]: _row_to_user(r) for r in conn.execute("SELECT * FROM users").fetchall()},
            "guilds": {r["guild_id"]: _row_to_guild(r) for r in conn.execute("SELECT * FROM guilds").fetchall()},
        }
