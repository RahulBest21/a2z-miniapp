#!/usr/bin/env python3
"""
A2Z Gamification Engine — RPG Awakening System
XP, Ranks, Daily Quests, Guilds, Raid Bosses, Hidden Quests
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import random
import logging

log = logging.getLogger("a2z.game")

# ═══════════════════════════════════════════════════════════════════════════
# RANK SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

RANK_THRESHOLDS = {
    'E': 0,      # Novice
    'C': 300,    # Awakened Aspirant — 15 days access
    'A': 1000,   # Elite — 45 days access + elite tag
    'S': 2500,   # The Monarch — lifetime access + VIP
}

RANK_NAMES = {
    'E': '🔰 Novice',
    'C': '⚡ Awakened Aspirant',
    'A': '💎 Elite',
    'S': '👑 The Monarch',
}

RANK_COLORS = {
    'E': '#9ca3af',   # gray
    'C': '#22c55e',   # green
    'A': '#8b5cf6',   # purple
    'S': '#f59e0b',   # gold
}

ACCESS_DAYS = 15  # Changed from 30 — more FOMO
INVITES_REQUIRED = 3
DECAY_XP = 50
DECAY_DAYS = 5
STREAK_XP = 50
INVITE_XP = 100
QUIZ_XP = 10  # >80% on daily quiz
DAILY_QUEST_XP = 20

# ═══════════════════════════════════════════════════════════════════════════
# SQL MIGRATIONS (call once after DB init)
# ═══════════════════════════════════════════════════════════════════════════

GAMIFICATION_SCHEMA = """
-- XP columns on users
ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN rank TEXT DEFAULT 'E';
ALTER TABLE users ADD COLUMN streak_days INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN last_active_date TEXT;
ALTER TABLE users ADD COLUMN guild_id TEXT;
ALTER TABLE users ADD COLUMN legacy_tag INTEGER DEFAULT 0;

-- XP audit trail
CREATE TABLE IF NOT EXISTS xp_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(telegram_id),
    amount      INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    source      TEXT,          -- invite_id, attempt_id, quest_id, etc.
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_xp_log_user ON xp_log(user_id);

-- Daily quests
CREATE TABLE IF NOT EXISTS daily_quests (
    quest_id    TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(telegram_id),
    quest_date  TEXT NOT NULL,     -- YYYY-MM-DD
    quest_type  TEXT DEFAULT 'quiz',
    completed   INTEGER DEFAULT 0,
    xp_earned   INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Guilds
CREATE TABLE IF NOT EXISTS guilds (
    guild_id    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    leader_id   INTEGER NOT NULL REFERENCES users(telegram_id),
    combined_xp INTEGER DEFAULT 0,
    multiplier  REAL DEFAULT 1.0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS guild_members (
    guild_id    TEXT NOT NULL REFERENCES guilds(guild_id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(telegram_id),
    joined_at   TEXT NOT NULL DEFAULT (datetime('now')),
    quest_done_today INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

-- Raid boss events
CREATE TABLE IF NOT EXISTS raid_events (
    raid_id     TEXT PRIMARY KEY,
    boss_name   TEXT NOT NULL,
    hp_total    INTEGER NOT NULL,
    hp_current  INTEGER NOT NULL,
    reward      TEXT,
    deadline    TEXT NOT NULL,     -- YYYY-MM-DD HH:MM
    channel_id  TEXT,
    message_id  TEXT,              -- pinned progress message
    completed   INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS raid_damage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    raid_id     TEXT NOT NULL REFERENCES raid_events(raid_id),
    user_id     INTEGER NOT NULL REFERENCES users(telegram_id),
    damage      INTEGER NOT NULL,
    source      TEXT,              -- invite, quiz
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Hidden quests tracking
CREATE TABLE IF NOT EXISTS hidden_quests (
    quest_name  TEXT NOT NULL,     -- speedrunner, first_blood
    user_id     INTEGER NOT NULL REFERENCES users(telegram_id),
    mock_id     TEXT,              -- for first_blood
    claimed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    xp_bonus    INTEGER DEFAULT 0,
    PRIMARY KEY (quest_name, user_id)
);
"""


def apply_gamification_migration(db_execute, db_commit):
    """Apply gamification schema to existing DB (idempotent)."""
    for stmt in GAMIFICATION_SCHEMA.split(';'):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            db_execute(stmt)
        except Exception:
            pass  # ALTER TABLE fails if column exists — safe to skip
    db_commit()
    log.info("Gamification schema applied")


# ═══════════════════════════════════════════════════════════════════════════
# XP & RANK FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def calculate_rank(xp: int) -> str:
    """Get rank letter from XP."""
    current = 'E'
    for rank, threshold in sorted(RANK_THRESHOLDS.items(), key=lambda x: x[1]):
        if xp >= threshold:
            current = rank
    return current


def xp_to_next_rank(xp: int) -> Tuple[str, int, int]:
    """Returns (next_rank, xp_needed, xp_progress_pct)."""
    current = calculate_rank(xp)
    ranks = sorted(RANK_THRESHOLDS.items(), key=lambda x: x[1])
    for i, (rank, threshold) in enumerate(ranks):
        if rank == current:
            if i + 1 < len(ranks):
                next_rank = ranks[i + 1][0]
                next_threshold = ranks[i + 1][1]
                needed = next_threshold - xp
                progress = int(((xp - threshold) / (next_threshold - threshold)) * 100) if (next_threshold - threshold) > 0 else 100
                return next_rank, max(0, needed), progress
    return 'MAX', 0, 100


def award_xp(db_execute, db_commit, user_id: int, amount: int, reason: str, source: str = "") -> Tuple[str, int, bool]:
    """Award XP. Returns (rank, xp_total, rank_changed)."""
    # Get current XP
    row = db_execute("SELECT xp, rank FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
    old_xp = row["xp"] if row else 0
    old_rank = row["rank"] if row else 'E'
    new_xp = old_xp + amount

    # Update user
    db_execute(
        "UPDATE users SET xp = ?, rank = ?, last_active_date = date('now') WHERE telegram_id = ?",
        (new_xp, calculate_rank(new_xp), user_id),
    )
    # Log
    db_execute(
        "INSERT INTO xp_log (user_id, amount, reason, source) VALUES (?, ?, ?, ?)",
        (user_id, amount, reason, source or ""),
    )
    db_commit()

    new_rank = calculate_rank(new_xp)
    rank_changed = new_rank != old_rank and new_rank != old_rank  # fixed: simple comparison
    rank_changed = new_rank != old_rank

    # Speedrunner hidden quest: Rank E → C in under 2 hours
    if rank_changed and old_rank == 'E' and new_rank >= 'C':
        # Check if within 2 hours of first XP
        first_xp = db_execute(
            "SELECT created_at FROM xp_log WHERE user_id = ? ORDER BY id ASC LIMIT 1",
            (user_id,),
        ).fetchone()
        if first_xp:
            try:
                first_time = datetime.strptime(first_xp["created_at"], "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - first_time).total_seconds() < 7200:
                    # Speedrunner bonus!
                    already_claimed = db_execute(
                        "SELECT 1 FROM hidden_quests WHERE quest_name = 'speedrunner' AND user_id = ?",
                        (user_id,),
                    ).fetchone()
                    if not already_claimed:
                        db_execute(
                            "INSERT OR IGNORE INTO hidden_quests (quest_name, user_id, xp_bonus) VALUES ('speedrunner', ?, 30)",
                            (user_id,),
                        )
                        db_execute("UPDATE users SET xp = xp + 30 WHERE telegram_id = ?", (user_id,))
                        db_execute(
                            "INSERT INTO xp_log (user_id, amount, reason) VALUES (?, 30, 'Speedrunner Bonus (E→C in <2h)')",
                            (user_id,),
                        )
                        db_commit()
                        new_xp += 30
            except Exception:
                pass

    # Grant access based on rank
    _grant_rank_access(db_execute, db_commit, user_id, new_rank)

    return new_rank, new_xp, rank_changed


def _grant_rank_access(db_execute, db_commit, user_id: int, rank: str):
    """Grant free access based on rank level."""
    days = {'C': 15, 'A': 45, 'S': 365}.get(rank, 0)
    if days > 0:
        expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        db_execute(
            "UPDATE users SET free_access_expiry = MAX(COALESCE(free_access_expiry, date('now')), ?), free_mocks_used = 0 WHERE telegram_id = ?",
            (expiry, user_id),
        )
        db_commit()


def apply_rank_decay(db_execute, db_commit, user_id: int) -> Tuple[bool, int]:
    """Apply XP decay for inactive users. Returns (decayed, xp_lost)."""
    row = db_execute(
        "SELECT xp, rank, last_active_date, free_access_expiry FROM users WHERE telegram_id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        return False, 0
    if row["rank"] in ('E',):
        return False, 0  # Novices don't decay
    if not row["last_active_date"]:
        return False, 0

    try:
        last_active = datetime.strptime(row["last_active_date"], "%Y-%m-%d")
        days_inactive = (datetime.now() - last_active).days
        if days_inactive >= DECAY_DAYS:
            decay_xp = DECAY_XP * (days_inactive // DECAY_DAYS)
            new_xp = max(0, row["xp"] - decay_xp)
            new_rank = calculate_rank(new_xp)
            db_execute("UPDATE users SET xp = ?, rank = ? WHERE telegram_id = ?", (new_xp, new_rank, user_id))
            if decay_xp > 0:
                db_execute(
                    "INSERT INTO xp_log (user_id, amount, reason) VALUES (?, ?, ?)",
                    (user_id, -decay_xp, f"Rank Decay ({days_inactive} days inactive)"),
                )
            # Revoke access if dropped below rank threshold
            if row["rank"] != new_rank:
                if new_rank == 'E':
                    db_execute("UPDATE users SET free_access_expiry = NULL WHERE telegram_id = ?", (user_id,))
            db_commit()
            return True, decay_xp
    except Exception:
        pass
    return False, 0


# ═══════════════════════════════════════════════════════════════════════════
# DAILY QUESTS
# ═══════════════════════════════════════════════════════════════════════════

def get_today_quest(db_execute, user_id: int) -> Optional[Dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    row = db_execute(
        "SELECT * FROM daily_quests WHERE user_id = ? AND quest_date = ?",
        (user_id, today),
    ).fetchone()
    return dict(row) if row else None


def create_daily_quest(db_execute, db_commit, user_id: int) -> str:
    """Create today's daily quest. Returns quest_id."""
    import uuid
    quest_id = str(uuid.uuid4())[:12]
    today = datetime.now().strftime("%Y-%m-%d")
    db_execute(
        "INSERT OR IGNORE INTO daily_quests (quest_id, user_id, quest_date) VALUES (?, ?, ?)",
        (quest_id, user_id, today),
    )
    db_commit()
    return quest_id


def complete_daily_quest(db_execute, db_commit, user_id: int, xp_base: int = 20) -> int:
    """Complete quest, award XP with guild multiplier. Returns XP awarded."""
    today = datetime.now().strftime("%Y-%m-%d")
    quest = db_execute(
        "SELECT * FROM daily_quests WHERE user_id = ? AND quest_date = ? AND completed = 0",
        (user_id, today),
    ).fetchone()
    if not quest:
        return 0

    # Apply guild multiplier
    multiplier = _get_guild_multiplier(db_execute, user_id)
    xp_awarded = int(xp_base * multiplier)

    db_execute(
        "UPDATE daily_quests SET completed = 1, xp_earned = ? WHERE quest_id = ?",
        (xp_awarded, quest["quest_id"]),
    )
    award_xp(db_execute, db_commit, user_id, xp_awarded, f"Daily Quest ({xp_awarded} XP, {multiplier}x multiplier)", quest["quest_id"])

    # Update streak
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_quest = db_execute(
        "SELECT 1 FROM daily_quests WHERE user_id = ? AND quest_date = ? AND completed = 1",
        (user_id, yesterday),
    ).fetchone()
    if yesterday_quest:
        db_execute("UPDATE users SET streak_days = streak_days + 1 WHERE telegram_id = ?", (user_id,))
    else:
        db_execute("UPDATE users SET streak_days = 1 WHERE telegram_id = ?", (user_id,))

    # Streak bonus
    streak = db_execute("SELECT streak_days FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
    if streak and streak["streak_days"] >= 7:
        award_xp(db_execute, db_commit, user_id, STREAK_XP, f"7-Day Streak Bonus ({STREAK_XP} XP)")
        db_execute("UPDATE users SET streak_days = 0 WHERE telegram_id = ?", (user_id,))

    # Mark guild quest done today
    db_execute(
        "UPDATE guild_members SET quest_done_today = 1 WHERE user_id = ?",
        (user_id,),
    )
    db_commit()

    return xp_awarded


# ═══════════════════════════════════════════════════════════════════════════
# GUILDS
# ═══════════════════════════════════════════════════════════════════════════

def create_guild(db_execute, db_commit, leader_id: int, name: str) -> Tuple[bool, str]:
    """Create a new guild. Returns (success, guild_id or error)."""
    import uuid
    # Check if leader already in a guild
    existing = db_execute("SELECT guild_id FROM users WHERE telegram_id = ?", (leader_id,)).fetchone()
    if existing and existing["guild_id"]:
        return False, "You're already in a guild. Leave it first."

    guild_id = str(uuid.uuid4())[:8]
    db_execute(
        "INSERT INTO guilds (guild_id, name, leader_id) VALUES (?, ?, ?)",
        (guild_id, name, leader_id),
    )
    db_execute("INSERT INTO guild_members (guild_id, user_id) VALUES (?, ?)", (guild_id, leader_id))
    db_execute("UPDATE users SET guild_id = ? WHERE telegram_id = ?", (guild_id, leader_id))
    db_commit()
    return True, guild_id


def join_guild(db_execute, db_commit, user_id: int, guild_id: str) -> Tuple[bool, str]:
    """Join an existing guild."""
    guild = db_execute("SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)).fetchone()
    if not guild:
        return False, "Guild not found."

    # Check capacity (4 members max)
    members = db_execute("SELECT COUNT(*) as cnt FROM guild_members WHERE guild_id = ?", (guild_id,)).fetchone()
    if members and members["cnt"] >= 4:
        return False, "Guild is full (max 4 members)."

    existing = db_execute("SELECT guild_id FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
    if existing and existing["guild_id"]:
        return False, "You're already in a guild."

    db_execute("INSERT OR IGNORE INTO guild_members (guild_id, user_id) VALUES (?, ?)", (guild_id, user_id))
    db_execute("UPDATE users SET guild_id = ? WHERE telegram_id = ?", (guild_id, user_id))
    db_commit()
    return True, f"Joined guild: {guild['name']}"


def leave_guild(db_execute, db_commit, user_id: int):
    db_execute("DELETE FROM guild_members WHERE user_id = ?", (user_id,))
    db_execute("UPDATE users SET guild_id = NULL WHERE telegram_id = ?", (user_id,))
    db_commit()


def _get_guild_multiplier(db_execute, user_id: int) -> float:
    """Check if all guild members completed daily quest — 1.5x if yes."""
    row = db_execute("SELECT guild_id FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
    if not row or not row["guild_id"]:
        return 1.0
    guild_id = row["guild_id"]
    members = db_execute("SELECT user_id, quest_done_today FROM guild_members WHERE guild_id = ?", (guild_id,)).fetchall()
    if not members or len(members) < 2:
        return 1.0
    all_done = all(m["quest_done_today"] for m in members)
    if all_done:
        db_execute("UPDATE guilds SET multiplier = 1.5 WHERE guild_id = ?", (guild_id,))
        db_commit()
        return 1.5
    return 1.0


def get_guild_info(db_execute, user_id: int) -> Optional[Dict]:
    row = db_execute("SELECT guild_id FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
    if not row or not row["guild_id"]:
        return None
    guild = db_execute("SELECT * FROM guilds WHERE guild_id = ?", (row["guild_id"],)).fetchone()
    if not guild:
        return None
    members = db_execute(
        "SELECT u.telegram_id, u.first_name, u.username, u.xp, u.rank, gm.quest_done_today "
        "FROM guild_members gm JOIN users u ON gm.user_id = u.telegram_id WHERE gm.guild_id = ?",
        (row["guild_id"],),
    ).fetchall()
    return {
        "guild_id": guild["guild_id"],
        "name": guild["name"],
        "multiplier": guild["multiplier"],
        "members": [dict(m) for m in members],
    }


# ═══════════════════════════════════════════════════════════════════════════
# RAID BOSS
# ═══════════════════════════════════════════════════════════════════════════

def create_raid(db_execute, db_commit, boss_name: str, hp: int, hours: int, reward: str, channel_id: str = "") -> str:
    import uuid
    raid_id = str(uuid.uuid4())[:8]
    deadline = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
    db_execute(
        "INSERT INTO raid_events (raid_id, boss_name, hp_total, hp_current, reward, deadline, channel_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (raid_id, boss_name, hp, hp, reward, deadline, channel_id),
    )
    db_commit()
    return raid_id


def deal_raid_damage(db_execute, db_commit, raid_id: str, user_id: int, damage: int, source: str) -> Tuple[bool, int]:
    """Deal damage to current raid. Returns (boss_defeated, hp_remaining)."""
    raid = db_execute("SELECT * FROM raid_events WHERE raid_id = ? AND completed = 0", (raid_id,)).fetchone()
    if not raid:
        return False, 0
    new_hp = max(0, raid["hp_current"] - damage)
    db_execute("UPDATE raid_events SET hp_current = ? WHERE raid_id = ?", (new_hp, raid_id))
    db_execute("INSERT INTO raid_damage (raid_id, user_id, damage, source) VALUES (?, ?, ?, ?)", (raid_id, user_id, damage, source))
    if new_hp <= 0:
        db_execute("UPDATE raid_events SET completed = 1 WHERE raid_id = ?", (raid_id,))
        db_commit()
        return True, 0
    db_commit()
    return False, new_hp


def get_active_raid(db_execute) -> Optional[Dict]:
    row = db_execute("SELECT * FROM raid_events WHERE completed = 0 ORDER BY created_at DESC LIMIT 1").fetchone()
    return dict(row) if row else None


# ═══════════════════════════════════════════════════════════════════════════
# HIDDEN QUESTS
# ═══════════════════════════════════════════════════════════════════════════

def check_first_blood(db_execute, db_commit, mock_id: str, user_id: int) -> bool:
    """Check if this user is the first to score 100% on a mock."""
    already = db_execute(
        "SELECT 1 FROM hidden_quests WHERE quest_name = 'first_blood' AND mock_id = ?",
        (mock_id,),
    ).fetchone()
    if already:
        return False
    db_execute(
        "INSERT INTO hidden_quests (quest_name, user_id, mock_id, xp_bonus) VALUES ('first_blood', ?, ?, 500)",
        (user_id, mock_id),
    )
    award_xp(db_execute, db_commit, user_id, 500, f"🏆 First Blood: 100% on {mock_id}")
    db_commit()
    return True


# ═══════════════════════════════════════════════════════════════════════════
# HUNTER LICENSE CARD (HTML image generation via bot message)
# ═══════════════════════════════════════════════════════════════════════════

def hunter_license_html(user: Dict) -> str:
    """Generate a cool Hunter License HTML card for /mystats."""
    xp = user.get("xp", 0)
    rank = user.get("rank", "E")
    next_rank, needed, progress = xp_to_next_rank(xp)
    rank_name = RANK_NAMES.get(rank, "Unknown")
    rank_color = RANK_COLORS.get(rank, "#9ca3af")
    streak = user.get("streak_days", 0)
    mocks = user.get("total_mocks_taken", 0)

    ranks_display = ""
    for r, t in RANK_THRESHOLDS.items():
        active = "★" if r == rank else "☆"
        name = RANK_NAMES.get(r, "")
        ranks_display += f'<span style="color:{RANK_COLORS.get(r, "#999")};margin:0 4px;">{active} {name}</span>'

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
body{{font-family:Inter,sans-serif;background:linear-gradient(135deg,#0a0a1a,#1a1a2e);color:#fff;width:420px;padding:0;margin:0}}
.card{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);border:2px solid {rank_color};border-radius:16px;padding:24px;margin:0;box-shadow:0 0 30px {rank_color}44;position:relative;overflow:hidden}}
.card::before{{content:'';position:absolute;top:-40%;right:-20%;width:200px;height:200px;background:radial-gradient(circle,{rank_color}22,transparent 70%)}}
.rank-badge{{font-size:2.2rem;font-weight:900;color:{rank_color};text-shadow:0 0 20px {rank_color}}}
.name{{font-size:1.2rem;font-weight:600;margin:4px 0;color:#e2e8f0}}
.xp-value{{font-size:2.8rem;font-weight:900;color:{rank_color};text-shadow:0 0 15px {rank_color}66}}
.xp-label{{font-size:.7rem;color:#94a3b8;text-transform:uppercase;letter-spacing:2px}}
.bar-bg{{height:12px;background:rgba(255,255,255,.1);border-radius:6px;overflow:hidden;margin:12px 0 6px}}
.bar-fill{{height:100%;background:linear-gradient(90deg,{rank_color},#f59e0b);border-radius:6px;transition:width .5s;box-shadow:0 0 10px {rank_color}66}}
.progress-text{{font-size:.7rem;color:#94a3b8;text-align:right}}
.stats-row{{display:flex;justify-content:space-between;margin:16px 0;gap:8px}}
.stat{{flex:1;text-align:center;background:rgba(255,255,255,.05);border-radius:10px;padding:10px 6px;border:1px solid rgba(255,255,255,.08)}}
.stat-val{{font-size:1.1rem;font-weight:700;color:#e2e8f0}}
.stat-lbl{{font-size:.6rem;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:2px}}
.ranks-row{{font-size:.65rem;margin-top:14px;text-align:center;opacity:.8}}
.footer{{text-align:center;font-size:.55rem;color:#475569;margin-top:14px;letter-spacing:2px;text-transform:uppercase}}
</style></head><body><div class="card">
<div class="rank-badge">{rank_name}</div>
<div class="name">{user.get("first_name", user.get("username", "Aspirant"))}</div>
<div class="xp-value">{xp:,} <span style="font-size:1rem;color:#94a3b8">XP</span></div>
<div class="xp-label">Power Level</div>
<div class="bar-bg"><div class="bar-fill" style="width:{progress}%"></div></div>
<div class="progress-text">Next: {next_rank} ({needed:,} XP needed)</div>
<div class="stats-row">
<div class="stat"><div class="stat-val">{streak}🔥</div><div class="stat-lbl">Day Streak</div></div>
<div class="stat"><div class="stat-val">{mocks}</div><div class="stat-lbl">Mocks Done</div></div>
<div class="stat"><div class="stat-val">{len(user.get("guild_id","") or "")>0 and '⚔️ Guild' or 'Solo'}</div><div class="stat-lbl">Status</div></div>
</div>
<div class="ranks-row">{ranks_display}</div>
<div class="footer">A2Z Updates4U • Hunter License</div>
</div></body></html>"""
    return html


# ═══════════════════════════════════════════════════════════════════════════
# FOMO MESSAGING
# ═══════════════════════════════════════════════════════════════════════════

def get_fomo_message(user: Dict, has_access: bool, days_left: int) -> str:
    """Generate urgency/FOMO messaging based on user state."""
    rank = user.get("rank", "E")
    if has_access and days_left <= 3:
        return (
            f"🚨 *⚠️ ACCESS EXPIRING IN {days_left} DAYS!*\n"
            f"_Your {RANK_NAMES.get(rank, '')} access ends soon. "
            f"Complete daily quests to maintain your rank or invite friends to secure lifetime access._\n"
            f"_This is a limited beta — premium pricing will be announced soon. "
            f"Lock in your free access NOW before it's too late._"
        )
    if not has_access and rank == 'E':
        return (
            "\U0001f512 *FREE TIER - Limited Access*\n"
            "_You have only 5 free mocks. Unlock unlimited access by inviting 3 friends "
            "and reaching Rank C (300 XP). Premium launch is imminent - "
            "secure your spot FREE while you still can._"
        )
    return ""
