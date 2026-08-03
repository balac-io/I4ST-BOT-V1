"""
Persistance JSON simple — remplaçable par SQLite/PostgreSQL en prod SaaS.
"""

import json
import os
from datetime import datetime

DB_FILE = "data/kryvoox.json"

_DEFAULT = {
    "guilds": {},      # config par serveur
    "users": {},       # profils, niveaux, économie
    "warnings": {},    # warnings par serveur/user
    "tickets": {},     # tickets par serveur
    "backups": {},     # backups serveur
}

def _load() -> dict:
    os.makedirs("data", exist_ok=True)
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return _DEFAULT.copy()

def _save(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

_db = _load()

# ─── Accès guilds ─────────────────────────────────────────────────────────────

def get_guild(guild_id: int) -> dict:
    gid = str(guild_id)
    if gid not in _db["guilds"]:
        _db["guilds"][gid] = {
            "prefix": "/",
            "log_channel": None,
            "welcome_channel": None,
            "goodbye_channel": None,
            "welcome_msg": "Bienvenue {user} sur {server} !",
            "goodbye_msg": "Au revoir {user}.",
            "autorole": None,
            "verify_role": None,
            "antiinvite": False,
            "antilink": False,
            "antispam": False,
            "antibot": False,
            "antinuke": False,
            "shop": {},
            "counters": {},
        }
        _save(_db)
    return _db["guilds"][gid]

def save_guild(guild_id: int, data: dict):
    _db["guilds"][str(guild_id)] = data
    _save(_db)

# ─── Accès users ──────────────────────────────────────────────────────────────

def get_user(user_id: int) -> dict:
    uid = str(user_id)
    if uid not in _db["users"]:
        _db["users"][uid] = {
            "bio": None,
            "coins": 0,
            "bank": 0,
            "xp": 0,
            "level": 1,
            "inventory": [],
            "last_daily": None,
            "last_work": None,
            "total_msgs": 0,
        }
        _save(_db)
    return _db["users"][uid]

def save_user(user_id: int, data: dict):
    _db["users"][str(user_id)] = data
    _save(_db)

# ─── Warnings ─────────────────────────────────────────────────────────────────

def add_warning(guild_id: int, user_id: int, reason: str, mod: str) -> int:
    key = f"{guild_id}:{user_id}"
    if key not in _db["warnings"]:
        _db["warnings"][key] = []
    _db["warnings"][key].append({
        "reason": reason,
        "mod": mod,
        "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "id": len(_db["warnings"][key]) + 1
    })
    _save(_db)
    return len(_db["warnings"][key])

def get_warnings(guild_id: int, user_id: int) -> list:
    return _db["warnings"].get(f"{guild_id}:{user_id}", [])

def clear_warnings(guild_id: int, user_id: int):
    _db["warnings"].pop(f"{guild_id}:{user_id}", None)
    _save(_db)

# ─── Tickets ──────────────────────────────────────────────────────────────────

def get_tickets(guild_id: int) -> dict:
    return _db["tickets"].get(str(guild_id), {})

def save_ticket(guild_id: int, ticket_id: str, data: dict):
    gid = str(guild_id)
    if gid not in _db["tickets"]:
        _db["tickets"][gid] = {}
    _db["tickets"][gid][ticket_id] = data
    _save(_db)

def delete_ticket(guild_id: int, ticket_id: str):
    gid = str(guild_id)
    if gid in _db["tickets"]:
        _db["tickets"][gid].pop(ticket_id, None)
        _save(_db)

# ─── Leaderboard ──────────────────────────────────────────────────────────────

def get_leaderboard_economy(limit=10) -> list:
    sorted_u = sorted(_db["users"].items(), key=lambda x: x[1].get("coins", 0) + x[1].get("bank", 0), reverse=True)
    return sorted_u[:limit]

def get_leaderboard_xp(limit=10) -> list:
    sorted_u = sorted(_db["users"].items(), key=lambda x: x[1].get("xp", 0), reverse=True)
    return sorted_u[:limit]

def raw() -> dict:
    return _db
