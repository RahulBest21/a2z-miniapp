#!/usr/bin/env python3
"""
A2Z Database Module — SQLite backend for mock tracking, leaderboards,
user access, invites, editorials, and per-question analytics.
"""

import json
import logging
import os
import random
import sqlite3
import string
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("a2z.db")

DB_PATH = Path(__file__).parent / "a2z_data.db"

# ═══════════════════════════════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════════════════════════════
SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    telegram_id   INTEGER PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    last_name     TEXT,
    invited_by    INTEGER REFERENCES users(telegram_id),
    join_date     TEXT NOT NULL DEFAULT (date('now')),
    free_access_expiry TEXT,          -- NULL = no free access / expired
    premium_access_expiry TEXT,       -- NULL = no premium access
    premium_tier      TEXT DEFAULT 'free',  -- free / tier1 / tier2 / paid
    free_mocks_used   INTEGER DEFAULT 0,
    free_limit        INTEGER DEFAULT 5,
    total_mocks_taken INTEGER DEFAULT 0,
    auth_token     TEXT UNIQUE,        -- for mini app auth
    state_json     TEXT                -- JSON blob for mini-app↔bot roundtrip
);

CREATE TABLE IF NOT EXISTS admins (
    user_id     INTEGER PRIMARY KEY REFERENCES users(telegram_id),
    added_by    INTEGER REFERENCES users(telegram_id),
    added_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mocks (
    mock_id      TEXT PRIMARY KEY,         -- "MOCK-a3f2b1c0"
    uploader_id  INTEGER REFERENCES users(telegram_id),
    title        TEXT NOT NULL,
    topic        TEXT,
    section      TEXT DEFAULT 'General',
    source_file  TEXT,                     -- original filename
    question_count INTEGER DEFAULT 0,
    timer_minutes  INTEGER DEFAULT 10,
    file_hash    TEXT,                     -- SHA256 of the HTML content
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    total_attempts INTEGER DEFAULT 0,
    benchmark_score INTEGER,               -- AIR 209 target score
    scheduled_at   TEXT,                   -- YYYY-MM-DD when mock appears
    active_at      TEXT,                   -- YYYY-MM-DD HH:MM when mock unlocks
    expires_at     TEXT                    -- YYYY-MM-DD after which mock is hidden
);

CREATE TABLE IF NOT EXISTS questions (
    question_id  TEXT PRIMARY KEY,         -- "Q-a3f2b1c0-0001"
    mock_id      TEXT NOT NULL REFERENCES mocks(mock_id) ON DELETE CASCADE,
    q_number     INTEGER NOT NULL,         -- 1-based question number
    text         TEXT,
    text_hi      TEXT,
    options      TEXT,                     -- JSON array
    options_hi   TEXT,                     -- JSON array
    correct_index INTEGER,
    explanation  TEXT,
    explanation_hi TEXT,
    subject_id    INTEGER,                  -- FK → taxonomy.subjects
    chapter_id    INTEGER,                  -- FK → taxonomy.chapters
    topic_id      INTEGER,                  -- FK → taxonomy.topics
    subtopic_id   INTEGER,                  -- FK → taxonomy.subtopics
    difficulty_level TEXT DEFAULT 'medium', -- easy / medium / hard
    cognitive_level  TEXT DEFAULT 'knowledge', -- knowledge / application / analysis
    concept_tags  TEXT,                     -- JSON array of extra concept tags
    UNIQUE(mock_id, q_number)
);
CREATE INDEX IF NOT EXISTS idx_questions_mock ON questions(mock_id);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id   TEXT PRIMARY KEY,         -- UUID
    user_id      INTEGER NOT NULL REFERENCES users(telegram_id),
    mock_id      TEXT NOT NULL REFERENCES mocks(mock_id),
    username_at_attempt TEXT,
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    submitted_at TEXT,
    total_score  INTEGER DEFAULT 0,
    correct_count INTEGER DEFAULT 0,
    wrong_count  INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    accuracy     REAL DEFAULT 0.0,
    total_time_sec INTEGER DEFAULT 0,     -- total time taken
    avg_time_per_q  REAL DEFAULT 0.0,     -- average seconds per question
    best_time_correct REAL DEFAULT 0.0,   -- fastest time on a correct answer
    status       TEXT DEFAULT 'started'   -- started, submitted, abandoned
);
CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_attempts_mock ON attempts(mock_id);
CREATE INDEX IF NOT EXISTS idx_attempts_status ON attempts(status);

CREATE TABLE IF NOT EXISTS responses (
    response_id  TEXT PRIMARY KEY,         -- UUID
    attempt_id   TEXT NOT NULL REFERENCES attempts(attempt_id) ON DELETE CASCADE,
    question_id  TEXT NOT NULL REFERENCES questions(question_id),
    user_id      INTEGER NOT NULL REFERENCES users(telegram_id),
    q_number     INTEGER NOT NULL,
    selected_option INTEGER,               -- -1 = skipped/marked
    is_correct   INTEGER DEFAULT 0,        -- 0/1
    time_spent_sec REAL DEFAULT 0.0,       -- seconds spent on this question
    marked       INTEGER DEFAULT 0,        -- 0/1 marked for review
    answered_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_responses_attempt ON responses(attempt_id);
CREATE INDEX IF NOT EXISTS idx_responses_user ON responses(user_id);
CREATE INDEX IF NOT EXISTS idx_responses_question ON responses(question_id);

CREATE TABLE IF NOT EXISTS invites (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    inviter_id   INTEGER NOT NULL REFERENCES users(telegram_id),
    invited_id   INTEGER REFERENCES users(telegram_id),
    invite_token TEXT UNIQUE NOT NULL,     -- random token for tracking
    channel_verified INTEGER DEFAULT 0,   -- 0/1: is invited user in channel?
    action_verified  INTEGER DEFAULT 0,   -- 0/1: did invited user complete an action?
    month_key    TEXT NOT NULL,            -- "YYYY-MM" for monthly reset
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    verified_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_invites_inviter ON invites(inviter_id, month_key);

CREATE TABLE IF NOT EXISTS editorials (
    editorial_id TEXT PRIMARY KEY,         -- UUID
    uploader_id  INTEGER REFERENCES users(telegram_id),
    title        TEXT NOT NULL,
    source       TEXT,                     -- "The Hindu" / "Indian Express"
    article_date TEXT,
    filename     TEXT,
    file_hash    TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ═══ TAXONOMY (Subject → Chapter → Topic → Subtopic) ═══
CREATE TABLE IF NOT EXISTS subjects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    exam_category TEXT DEFAULT 'General'   -- SSC CGL / UPSC / Banking / etc.
);

CREATE TABLE IF NOT EXISTS chapters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id    INTEGER NOT NULL REFERENCES subjects(id),
    name          TEXT NOT NULL,
    order_index   INTEGER DEFAULT 0,
    UNIQUE(subject_id, name)
);

CREATE TABLE IF NOT EXISTS topics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id    INTEGER NOT NULL REFERENCES chapters(id),
    name          TEXT NOT NULL,
    weightage     REAL DEFAULT 0,          -- exam weightage 0-100
    order_index   INTEGER DEFAULT 0,
    UNIQUE(chapter_id, name)
);

CREATE TABLE IF NOT EXISTS subtopics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id      INTEGER NOT NULL REFERENCES topics(id),
    name          TEXT NOT NULL,
    order_index   INTEGER DEFAULT 0,
    UNIQUE(topic_id, name)
);

-- ═══ USER ANALYTICS AGGREGATION (updated on mock submit) ═══
CREATE TABLE IF NOT EXISTS user_subject_stats (
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    subject_id    INTEGER NOT NULL REFERENCES subjects(id),
    total_attempts INTEGER DEFAULT 0,
    correct_count INTEGER DEFAULT 0,
    wrong_count   INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    accuracy      REAL DEFAULT 0,
    last_attempted_at TEXT,
    PRIMARY KEY (user_id, subject_id)
);

CREATE TABLE IF NOT EXISTS user_chapter_stats (
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    chapter_id    INTEGER NOT NULL REFERENCES chapters(id),
    subject_id    INTEGER NOT NULL REFERENCES subjects(id),
    total_attempts INTEGER DEFAULT 0,
    correct_count INTEGER DEFAULT 0,
    wrong_count   INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    accuracy      REAL DEFAULT 0,
    last_attempted_at TEXT,
    PRIMARY KEY (user_id, chapter_id)
);

CREATE TABLE IF NOT EXISTS user_topic_stats (
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    topic_id      INTEGER NOT NULL REFERENCES topics(id),
    chapter_id    INTEGER NOT NULL REFERENCES chapters(id),
    subject_id    INTEGER NOT NULL REFERENCES subjects(id),
    total_attempts INTEGER DEFAULT 0,
    correct_count INTEGER DEFAULT 0,
    wrong_count   INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    accuracy      REAL DEFAULT 0,
    last_attempted_at TEXT,
    PRIMARY KEY (user_id, topic_id)
);

CREATE TABLE IF NOT EXISTS user_mock_group_stats (
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    group_id      TEXT NOT NULL,            -- "SSC_CGL_Maths" etc.
    mocks_attempted INTEGER DEFAULT 0,
    avg_score     REAL DEFAULT 0,
    best_score    REAL DEFAULT 0,
    latest_score  REAL DEFAULT 0,
    trend_json    TEXT,                     -- last N scores as JSON
    last_attempted_at TEXT,
    PRIMARY KEY (user_id, group_id)
);

-- ═══ PvP Challenges ═══
CREATE TABLE IF NOT EXISTS challenges (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id      TEXT UNIQUE NOT NULL,       -- random 8-char ID
    challenger_id INTEGER NOT NULL REFERENCES users(telegram_id),
    rival_id      INTEGER REFERENCES users(telegram_id),
    mock_id       TEXT NOT NULL REFERENCES mocks(mock_id),
    challenger_score INTEGER,
    challenger_attempt_id TEXT,
    rival_score   INTEGER,
    rival_attempt_id TEXT,
    status        TEXT DEFAULT 'pending',     -- pending / accepted / completed
    winner_id     INTEGER REFERENCES users(telegram_id),
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at  TEXT
);
"""

# ═══════════════════════════════════════════════════════════════════════════
# CONNECTION
# ═══════════════════════════════════════════════════════════════════════════
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
        log.info("Database initialised at %s", DB_PATH)
    return _conn


def db_execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    return _get_conn().execute(sql, params)


def db_commit():
    _get_conn().commit()


def db_fetchone(sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    return _get_conn().execute(sql, params).fetchone()


def db_fetchall(sql: str, params: tuple = ()) -> List[sqlite3.Row]:
    return _get_conn().execute(sql, params).fetchall()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _gen_mock_id() -> str:
    """Generate a unique mock ID: MOCK-xxxxxxxx"""
    return "MOCK-" + ''.join(random.choices(string.hexdigits.lower(), k=8))


def _gen_short_hex(mock_id: str) -> str:
    """Extract the 8-char hex portion from mock_id."""
    return mock_id.replace("MOCK-", "")


def _gen_question_id(mock_id: str, q_number: int) -> str:
    """Q-{mock_hex}-{q_number:04d}"""
    return f"Q-{_gen_short_hex(mock_id)}-{q_number:04d}"


def _gen_token(length: int = 16) -> str:
    """Random hex token for invites/auth."""
    return ''.join(random.choices(string.hexdigits.lower(), k=length))


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _month_key() -> str:
    return datetime.now().strftime("%Y-%m")


# ═══════════════════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════════════════

def get_or_create_user(telegram_id: int, username: str = "", first_name: str = "", last_name: str = "") -> sqlite3.Row:
    """Get existing user or create a new one."""
    user = db_fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    if user:
        # Update name info
        db_execute(
            "UPDATE users SET username = ?, first_name = ?, last_name = ? WHERE telegram_id = ?",
            (username or "", first_name or "", last_name or "", telegram_id),
        )
        db_commit()
        return db_fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    db_execute(
        "INSERT INTO users (telegram_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
        (telegram_id, username or "", first_name or "", last_name or ""),
    )
    db_commit()
    return db_fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))


def add_admin(user_id: int, added_by: int) -> bool:
    try:
        db_execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)", (user_id, added_by))
        db_commit()
        return True
    except Exception:
        return False


def is_admin(user_id: int) -> bool:
    return db_fetchone("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)) is not None


def get_user_auth_token(user_id: int) -> str:
    """Get or create an auth token for mini app."""
    user = db_fetchone("SELECT auth_token FROM users WHERE telegram_id = ?", (user_id,))
    if user and user["auth_token"]:
        return user["auth_token"]
    token = _gen_token(32)
    db_execute("UPDATE users SET auth_token = ? WHERE telegram_id = ?", (token, user_id))
    db_commit()
    return token


def verify_auth_token(token: str) -> Optional[sqlite3.Row]:
    return db_fetchone("SELECT * FROM users WHERE auth_token = ?", (token,))


def store_state(user_id: int, json_data: str) -> bool:
    """Store JSON state blob in users.state_json column for mini-app data pipeline."""
    try:
        db_execute("UPDATE users SET state_json = ? WHERE telegram_id = ?", (json_data, user_id))
        db_commit()
        return True
    except Exception:
        return False


def get_stored_state(user_id: int) -> Optional[str]:
    """Retrieve stored JSON state blob for mini-app roundtrip."""
    row = db_fetchone("SELECT state_json FROM users WHERE telegram_id = ?", (user_id,))
    if row and row["state_json"]:
        return row["state_json"]
    return None


def has_free_access(user_id: int) -> Tuple[bool, int, int]:
    """Returns (has_access, days_remaining, free_mocks_remaining).
    Checks both free_access_expiry and premium_access_expiry."""
    user = db_fetchone(
        "SELECT free_access_expiry, premium_access_expiry, free_mocks_used, free_limit FROM users WHERE telegram_id = ?",
        (user_id,),
    )
    if not user:
        return False, 0, 5
    max_days = 0
    for expiry_col in ["free_access_expiry", "premium_access_expiry"]:
        if user[expiry_col]:
            try:
                exp = datetime.strptime(user[expiry_col], "%Y-%m-%d")
                days = (exp - datetime.now()).days
                if days > max_days:
                    max_days = days
            except Exception:
                pass
    if max_days <= 0:
        free_left = max(0, user["free_limit"] - user["free_mocks_used"])
        return False, 0, free_left
    free_left = max(0, user["free_limit"] - user["free_mocks_used"])
    return True, max_days, free_left


def grant_premium_access(user_id: int, days: int, tier: str = "tier1"):
    """Grant premium access with tier tracking."""
    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    db_execute(
        "UPDATE users SET premium_access_expiry = ?, premium_tier = ? WHERE telegram_id = ?",
        (expiry, tier, user_id),
    )
    db_commit()


def use_free_mock(user_id: int) -> bool:
    """Increment free_mocks_used. Returns True if within limit."""
    user = db_fetchone("SELECT free_mocks_used, free_limit FROM users WHERE telegram_id = ?", (user_id,))
    if not user:
        return False
    used = user["free_mocks_used"] + 1
    if used > user["free_limit"]:
        return False
    db_execute("UPDATE users SET free_mocks_used = ? WHERE telegram_id = ?", (used, user_id))
    db_commit()
    return True


def grant_free_access(user_id: int, days: int = 30):
    """Grant free access for N days."""
    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    db_execute(
        "UPDATE users SET free_access_expiry = ?, free_mocks_used = 0 WHERE telegram_id = ?",
        (expiry, user_id),
    )
    db_commit()


# ═══════════════════════════════════════════════════════════════════════════
# INVITES
# ═══════════════════════════════════════════════════════════════════════════

INVITES_REQUIRED = 3
ACCESS_DAYS = 30


def create_invite(inviter_id: int) -> str:
    """Create an invite token. Returns the token."""
    token = _gen_token(12)
    db_execute(
        "INSERT INTO invites (inviter_id, invite_token, month_key) VALUES (?, ?, ?)",
        (inviter_id, token, _month_key()),
    )
    db_commit()
    return token


def record_invite_join(invite_token: str, invited_id: int):
    """Called when a new user joins via an invite link."""
    invite = db_fetchone("SELECT * FROM invites WHERE invite_token = ? AND invited_id IS NULL", (invite_token,))
    if not invite:
        return
    db_execute(
        "UPDATE invites SET invited_id = ? WHERE invite_token = ?",
        (invited_id, invite_token),
    )
    # Also update the invited user's invited_by field
    db_execute("UPDATE users SET invited_by = ? WHERE telegram_id = ?", (invite["inviter_id"], invited_id))
    db_commit()


def verify_channel_membership(user_id: int, channel_id: str, bot_token: str) -> bool:
    """Check if user is a member of the channel using Telegram API."""
    try:
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/getChatMember"
        resp = requests.get(url, params={"chat_id": channel_id, "user_id": user_id}, timeout=10)
        data = resp.json()
        if data.get("ok"):
            status = data["result"]["status"]
            return status in ("member", "administrator", "creator")
        return False
    except Exception as e:
        log.warning("Channel membership check failed for %s: %s", user_id, e)
        return False


def mark_invite_verified(invited_id: int):
    """Mark all pending invites for this user as verified (channel)."""
    db_execute(
        "UPDATE invites SET channel_verified = 1, verified_at = ? WHERE invited_id = ? AND channel_verified = 0",
        (_now(), invited_id),
    )
    db_commit()


def verify_referral_by_action(invited_id: int) -> Optional[int]:
    """When invited user completes an action, mark invite as action-verified.
    Returns inviter_id if a new verification happened, else None."""
    invite = db_fetchone(
        "SELECT * FROM invites WHERE invited_id = ? AND action_verified = 0 ORDER BY created_at ASC LIMIT 1",
        (invited_id,),
    )
    if not invite:
        return None
    db_execute(
        "UPDATE invites SET action_verified = 1, verified_at = COALESCE(verified_at, ?) WHERE id = ?",
        (_now(), invite["id"]),
    )
    db_commit()
    return invite["inviter_id"]


def get_monthly_invite_count(inviter_id: int) -> int:
    """Count verified invites (channel OR action) this month."""
    row = db_fetchone(
        "SELECT COUNT(*) as cnt FROM invites WHERE inviter_id = ? AND month_key = ? AND (channel_verified = 1 OR action_verified = 1)",
        (inviter_id, _month_key()),
    )
    return row["cnt"] if row else 0


def get_monthly_action_verified_count(inviter_id: int) -> int:
    """Count action-verified invites this month."""
    row = db_fetchone(
        "SELECT COUNT(*) as cnt FROM invites WHERE inviter_id = ? AND month_key = ? AND action_verified = 1",
        (inviter_id, _month_key()),
    )
    return row["cnt"] if row else 0


def check_and_grant_access(user_id: int, channel_id: str, bot_token: str) -> Tuple[bool, str]:
    """Verify invites and grant tiered access.
    Tier 1: 3 verified = 15 days free access
    Tier 2: 5 verified = 30 days premium access"""
    invites = db_fetchall(
        "SELECT * FROM invites WHERE inviter_id = ? AND month_key = ?",
        (user_id, _month_key()),
    )
    verified = 0
    for inv in invites:
        if inv["invited_id"]:
            if inv["action_verified"] or inv["channel_verified"]:
                verified += 1
            elif channel_id and bot_token:
                is_member = verify_channel_membership(inv["invited_id"], channel_id, bot_token)
                if is_member:
                    mark_invite_verified(inv["invited_id"])
                    verified += 1

    if verified >= 5:
        grant_premium_access(user_id, 30, "tier2")
        return True, f"✅ {verified}/5 verified — 30 days PREMIUM access granted! (Tier 2)"
    elif verified >= 3:
        grant_free_access(user_id, 15)
        return True, f"✅ {verified}/3 verified — 15 days free access granted! (Tier 1)"
    elif verified >= 1:
        grant_free_access(user_id, 7)
        return True, f"✅ {verified} verified — 7 days trial access granted!"
    return False, f"⏳ {verified} verified — need {INVITES_REQUIRED - verified} more invites."


# ═══════════════════════════════════════════════════════════════════════════
# MOCKS
# ═══════════════════════════════════════════════════════════════════════════

def register_mock(uploader_id: int, title: str, topic: str = "", section: str = "General",
                  source_file: str = "", question_count: int = 0, timer_minutes: int = 10,
                  file_hash: str = "") -> str:
    """Register a new mock in the DB. Returns mock_id."""
    mock_id = _gen_mock_id()
    db_execute(
        """INSERT INTO mocks (mock_id, uploader_id, title, topic, section, source_file,
           question_count, timer_minutes, file_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (mock_id, uploader_id, title, topic, section, source_file, question_count, timer_minutes, file_hash),
    )
    db_commit()
    return mock_id


def register_questions(mock_id: str, questions: List[Dict]):
    """Bulk insert questions for a mock. Stores taxonomy tags if present."""
    for i, q in enumerate(questions):
        qid = _gen_question_id(mock_id, i + 1)
        # Resolve taxonomy tags from Gemini output
        subj_id = None; chap_id = None; top_id = None; subtop_id = None
        subj_name = q.get("subject", "")
        chap_name = q.get("chapter", "")
        topic_name = q.get("topic", "")
        subtopic_name = q.get("subtopic", "")
        if subj_name:
            tags = resolve_tags(subj_name, chap_name, topic_name, subtopic_name)
            if tags:
                subj_id = tags.get("subject_id")
                chap_id = tags.get("chapter_id")
                top_id = tags.get("topic_id")
                subtop_id = tags.get("subtopic_id")
        db_execute(
            """INSERT OR REPLACE INTO questions
               (question_id, mock_id, q_number, text, text_hi, options, options_hi,
                correct_index, explanation, explanation_hi,
                subject_id, chapter_id, topic_id, subtopic_id,
                difficulty_level, cognitive_level, concept_tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                qid, mock_id, i + 1,
                q.get("text", ""),
                q.get("text_hi", ""),
                json.dumps(q.get("options", [])),
                json.dumps(q.get("options_hi", [])),
                q.get("correctIndex", -1),
                q.get("explanation", ""),
                q.get("explanation_hi", ""),
                subj_id, chap_id, top_id, subtop_id,
                q.get("difficulty", "medium"),
                q.get("cognitive", "knowledge"),
                json.dumps(q.get("tags", [])),
            ),
        )
    db_commit()


def get_mock(mock_id: str) -> Optional[sqlite3.Row]:
    return db_fetchone("SELECT * FROM mocks WHERE mock_id = ?", (mock_id,))


def get_mock_questions(mock_id: str) -> List[sqlite3.Row]:
    return db_fetchall("SELECT * FROM questions WHERE mock_id = ? ORDER BY q_number", (mock_id,))


def list_mocks(limit: int = 20) -> List[sqlite3.Row]:
    return db_fetchall("SELECT * FROM mocks ORDER BY created_at DESC LIMIT ?", (limit,))


def increment_mock_attempts(mock_id: str):
    db_execute("UPDATE mocks SET total_attempts = total_attempts + 1 WHERE mock_id = ?", (mock_id,))
    db_commit()


# ═══════════════════════════════════════════════════════════════════════════
# ATTEMPTS & RESPONSES
# ═══════════════════════════════════════════════════════════════════════════

def start_attempt(user_id: int, mock_id: str, username: str = "") -> str:
    """Begin a new attempt. Returns attempt_id."""
    attempt_id = str(uuid.uuid4())[:12]
    db_execute(
        "INSERT INTO attempts (attempt_id, user_id, mock_id, username_at_attempt, status) VALUES (?, ?, ?, ?, 'started')",
        (attempt_id, user_id, mock_id, username),
    )
    db_commit()
    return attempt_id


def save_response(attempt_id: str, user_id: int, question_id: str, q_number: int,
                  selected: int, is_correct: int, time_spent: float, marked: int = 0):
    """Save individual question response."""
    response_id = str(uuid.uuid4())[:12]
    db_execute(
        """INSERT OR REPLACE INTO responses
           (response_id, attempt_id, question_id, user_id, q_number,
            selected_option, is_correct, time_spent_sec, marked, answered_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (response_id, attempt_id, question_id, user_id, q_number, selected, is_correct, time_spent, marked, _now()),
    )
    db_commit()


def submit_attempt(attempt_id: str, score: int, correct: int, wrong: int, skipped: int,
                   accuracy: float, total_time: float, best_time_correct: float = 0.0):
    """Finalise an attempt with results."""
    avg_time = (total_time / max(correct + wrong + skipped, 1))
    db_execute(
        """UPDATE attempts SET status = 'submitted', submitted_at = ?,
           total_score = ?, correct_count = ?, wrong_count = ?, skipped_count = ?,
           accuracy = ?, total_time_sec = ?, avg_time_per_q = ?, best_time_correct = ?
           WHERE attempt_id = ?""",
        (_now(), score, correct, wrong, skipped, accuracy, total_time, avg_time, best_time_correct, attempt_id),
    )
    db_commit()


def get_attempt(attempt_id: str) -> Optional[sqlite3.Row]:
    return db_fetchone("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,))


def get_user_attempts(user_id: int, limit: int = 20) -> List[sqlite3.Row]:
    return db_fetchall(
        "SELECT a.*, m.title as mock_title FROM attempts a JOIN mocks m ON a.mock_id = m.mock_id WHERE a.user_id = ? ORDER BY a.submitted_at DESC LIMIT ?",
        (user_id, limit),
    )


def get_attempt_responses(attempt_id: str) -> List[sqlite3.Row]:
    return db_fetchall("SELECT * FROM responses WHERE attempt_id = ? ORDER BY q_number", (attempt_id,))


# ═══════════════════════════════════════════════════════════════════════════
# LEADERBOARD
# ═══════════════════════════════════════════════════════════════════════════

def get_leaderboard(mock_id: str, limit: int = 50) -> List[Dict]:
    """Get ranked leaderboard for a mock. Returns percentile + rank for each."""
    rows = db_fetchall(
        """SELECT a.*, u.first_name, u.username
           FROM attempts a JOIN users u ON a.user_id = u.telegram_id
           WHERE a.mock_id = ? AND a.status = 'submitted'
           ORDER BY a.total_score DESC, a.total_time_sec ASC
           LIMIT ?""",
        (mock_id, limit),
    )
    total = db_fetchone(
        "SELECT COUNT(*) as cnt FROM attempts WHERE mock_id = ? AND status = 'submitted'",
        (mock_id,),
    )
    total_count = total["cnt"] if total else 1
    result = []
    for rank, r in enumerate(rows, 1):
        percentile = round((1 - (rank / total_count)) * 100, 1)
        result.append({
            "rank": rank,
            "percentile": percentile,
            "name": r["first_name"] or r["username"] or str(r["user_id"]),
            "score": r["total_score"],
            "correct": r["correct_count"],
            "wrong": r["wrong_count"],
            "accuracy": round(r["accuracy"], 1),
            "time_sec": round(r["total_time_sec"]),
            "avg_time_q": round(r["avg_time_per_q"], 1) if r["avg_time_per_q"] else 0,
            "best_time": round(r["best_time_correct"], 1) if r["best_time_correct"] else 0,
            "date": r["submitted_at"][:10] if r["submitted_at"] else "",
        })
    return result


def get_user_rank(mock_id: str, attempt_id: str) -> Tuple[int, int, float]:
    """Get rank, total participants, and percentile for a specific attempt."""
    attempt = get_attempt(attempt_id)
    if not attempt:
        return 0, 0, 0.0
    better = db_fetchone(
        """SELECT COUNT(*) as cnt FROM attempts
           WHERE mock_id = ? AND status = 'submitted'
           AND (total_score > ? OR (total_score = ? AND total_time_sec < ?))""",
        (mock_id, attempt["total_score"], attempt["total_score"], attempt["total_time_sec"]),
    )
    total = db_fetchone(
        "SELECT COUNT(*) as cnt FROM attempts WHERE mock_id = ? AND status = 'submitted'",
        (mock_id,),
    )
    rank = (better["cnt"] or 0) + 1
    total_n = total["cnt"] or 1
    percentile = round((1 - (rank / total_n)) * 100, 1)
    return rank, total_n, percentile


# ═══════════════════════════════════════════════════════════════════════════
# TAXONOMY SEED
# ═══════════════════════════════════════════════════════════════════════════

TAXONOMY_SEED = {
    "Quantitative Aptitude": {
        "exam": "SSC CGL",
        "chapters": {
            "Arithmetic": ["Percentage", "Ratio & Proportion", "Profit & Loss", "Simple & Compound Interest", "Time & Work", "Time Speed Distance", "Average", "Mixture & Alligation"],
            "Algebra": ["Basic Algebra", "Linear Equations", "Quadratic Equations", "Polynomials"],
            "Geometry": ["Lines & Angles", "Triangles", "Circles", "Quadrilaterals", "Mensuration 2D", "Mensuration 3D", "Coordinate Geometry"],
            "Trigonometry": ["Trigonometric Ratios", "Heights & Distances", "Identities"],
            "Data Interpretation": ["Bar Graph", "Pie Chart", "Line Graph", "Table", "Mixed DI"],
            "Number System": ["LCM & HCF", "Divisibility", "Remainders", "Unit Digit", "Simplification"],
        }
    },
    "English Language": {
        "exam": "SSC CGL",
        "chapters": {
            "Vocabulary": ["Synonyms", "Antonyms", "One Word Substitution", "Idioms & Phrases", "Spelling"],
            "Grammar": ["Parts of Speech", "Tenses", "Active/Passive Voice", "Direct/Indirect Speech", "Articles", "Prepositions"],
            "Comprehension": ["Reading Comprehension", "Cloze Test", "Para Jumble", "Sentence Arrangement"],
            "Error Detection": ["Spotting Errors", "Sentence Improvement", "Fill in the Blanks"],
        }
    },
    "General Awareness": {
        "exam": "SSC CGL",
        "chapters": {
            "History": ["Ancient India", "Medieval India", "Modern India", "World History"],
            "Geography": ["Physical Geography", "Indian Geography", "World Geography"],
            "Polity": ["Constitution", "Parliament", "President & Governor", "Fundamental Rights", "DPSP"],
            "Economics": ["Micro Economics", "Macro Economics", "Indian Economy", "Budget", "Five Year Plans"],
            "Science": ["Physics", "Chemistry", "Biology", "Computer Science"],
            "Current Affairs": ["National", "International", "Sports", "Awards", "Science & Tech"],
        }
    },
    "Reasoning": {
        "exam": "SSC CGL",
        "chapters": {
            "Verbal Reasoning": ["Analogy", "Classification", "Coding-Decoding", "Blood Relations", "Direction Sense", "Ranking", "Syllogism", "Venn Diagrams"],
            "Non-Verbal Reasoning": ["Series", "Mirror Images", "Water Images", "Paper Cutting", "Cube & Dice", "Counting Figures"],
        }
    },
}


def _seed_taxonomy(conn: sqlite3.Connection):
    """Insert taxonomy seed data (idempotent — skips existing)."""
    for subject_name, data in TAXONOMY_SEED.items():
        conn.execute(
            "INSERT OR IGNORE INTO subjects (name, exam_category) VALUES (?, ?)",
            (subject_name, data["exam"]),
        )
        subject_id = conn.execute(
            "SELECT id FROM subjects WHERE name = ?", (subject_name,)
        ).fetchone()[0]
        for ci, (chapter_name, topic_names) in enumerate(data["chapters"].items()):
            conn.execute(
                "INSERT OR IGNORE INTO chapters (subject_id, name, order_index) VALUES (?, ?, ?)",
                (subject_id, chapter_name, ci),
            )
            chapter_id = conn.execute(
                "SELECT id FROM chapters WHERE subject_id = ? AND name = ?",
                (subject_id, chapter_name),
            ).fetchone()[0]
            for ti, topic_name in enumerate(topic_names):
                conn.execute(
                    "INSERT OR IGNORE INTO topics (chapter_id, name, weightage, order_index) VALUES (?, ?, ?, ?)",
                    (chapter_id, topic_name, 0, ti),
                )
    conn.commit()
    log.info("Taxonomy seeded: %d subjects", len(TAXONOMY_SEED))


# ═══════════════════════════════════════════════════════════════════════════
# TAXONOMY QUERIES
# ═══════════════════════════════════════════════════════════════════════════

def get_taxonomy_tree() -> List[Dict]:
    """Return full taxonomy as nested JSON for mini app."""
    subjects = db_fetchall("SELECT * FROM subjects ORDER BY id")
    result = []
    for s in (subjects or []):
        subj = dict(s)
        chapters = db_fetchall("SELECT * FROM chapters WHERE subject_id = ? ORDER BY order_index", (s["id"],))
        subj["chapters"] = []
        for c in (chapters or []):
            ch = dict(c)
            topics = db_fetchall("SELECT * FROM topics WHERE chapter_id = ? ORDER BY order_index", (c["id"],))
            ch["topics"] = [dict(t) for t in (topics or [])]
            subj["chapters"].append(ch)
        result.append(subj)
    return result


def resolve_tags(subject_name: str, chapter_name: str = "", topic_name: str = "",
                  subtopic_name: str = "") -> Optional[Dict]:
    """Resolve tag names to IDs. Creates missing entries if needed."""
    subj = db_fetchone("SELECT id FROM subjects WHERE name = ?", (subject_name,))
    if not subj:
        return None
    result = {"subject_id": subj["id"]}

    if chapter_name:
        ch = db_fetchone("SELECT id FROM chapters WHERE subject_id = ? AND name = ?",
                         (subj["id"], chapter_name))
        if not ch:
            db_execute("INSERT INTO chapters (subject_id, name) VALUES (?, ?)",
                       (subj["id"], chapter_name))
            db_commit()
            ch = db_fetchone("SELECT id FROM chapters WHERE subject_id = ? AND name = ?",
                             (subj["id"], chapter_name))
        result["chapter_id"] = ch["id"]

        if topic_name and ch:
            tp = db_fetchone("SELECT id FROM topics WHERE chapter_id = ? AND name = ?",
                             (ch["id"], topic_name))
            if not tp:
                db_execute("INSERT INTO topics (chapter_id, name) VALUES (?, ?)",
                           (ch["id"], topic_name))
                db_commit()
                tp = db_fetchone("SELECT id FROM topics WHERE chapter_id = ? AND name = ?",
                                 (ch["id"], topic_name))
            result["topic_id"] = tp["id"]

            if subtopic_name and tp:
                st = db_fetchone("SELECT id FROM subtopics WHERE topic_id = ? AND name = ?",
                                 (tp["id"], subtopic_name))
                if not st:
                    db_execute("INSERT INTO subtopics (topic_id, name) VALUES (?, ?)",
                               (tp["id"], subtopic_name))
                    db_commit()
                    st = db_fetchone("SELECT id FROM subtopics WHERE topic_id = ? AND name = ?",
                                     (tp["id"], subtopic_name))
                result["subtopic_id"] = st["id"]
    return result

def get_mock_stats(mock_id: str) -> Dict:
    """Aggregate stats for a mock: avg score, accuracy, time, distribution."""
    stats = db_fetchone(
        """SELECT COUNT(*) as total_attempts,
                  AVG(total_score) as avg_score,
                  AVG(accuracy) as avg_accuracy,
                  AVG(total_time_sec) as avg_time,
                  MAX(total_score) as best_score,
                  MIN(total_time_sec) as best_time
           FROM attempts WHERE mock_id = ? AND status = 'submitted'""",
        (mock_id,),
    )
    if not stats:
        return {}
    return {
        "total_attempts": stats["total_attempts"],
        "avg_score": round(stats["avg_score"] or 0, 1),
        "avg_accuracy": round(stats["avg_accuracy"] or 0, 1),
        "avg_time_sec": round(stats["avg_time"] or 0, 0),
        "best_score": stats["best_score"] or 0,
        "best_time_sec": round(stats["best_time"] or 0, 0),
    }


def get_question_stats(mock_id: str) -> List[Dict]:
    """Per-question difficulty: % correct, avg time."""
    return db_fetchall(
        """SELECT q.q_number, q.text,
                  COUNT(r.response_id) as total_responses,
                  SUM(r.is_correct) as correct_count,
                  AVG(r.time_spent_sec) as avg_time
           FROM questions q
           LEFT JOIN responses r ON q.question_id = r.question_id
           WHERE q.mock_id = ?
           GROUP BY q.q_number
           ORDER BY q.q_number""",
        (mock_id,),
    )


def get_user_stats(user_id: int) -> Dict:
    """Overall user stats."""
    stats = db_fetchone(
        """SELECT COUNT(*) as total_mocks,
                  AVG(accuracy) as avg_accuracy,
                  SUM(total_score) as total_score,
                  MAX(total_score) as best_score,
                  COUNT(DISTINCT mock_id) as unique_mocks
           FROM attempts WHERE user_id = ? AND status = 'submitted'""",
        (user_id,),
    )
    return dict(stats) if stats else {}


# ═══════════════════════════════════════════════════════════════════════════
# EDITORIALS
# ═══════════════════════════════════════════════════════════════════════════

def register_editorial(uploader_id: int, title: str, source: str = "", article_date: str = "",
                       filename: str = "", file_hash: str = "") -> str:
    editorial_id = str(uuid.uuid4())[:12]
    db_execute(
        "INSERT INTO editorials (editorial_id, uploader_id, title, source, article_date, filename, file_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (editorial_id, uploader_id, title, source, article_date, filename, file_hash),
    )
    db_commit()
    return editorial_id


def list_editorials(limit: int = 30) -> List[sqlite3.Row]:
    return db_fetchall("SELECT * FROM editorials ORDER BY created_at DESC LIMIT ?", (limit,))


# ═══════════════════════════════════════════════════════════════════════════
# ANALYTICS AGGREGATION
# ═══════════════════════════════════════════════════════════════════════════

def update_user_stats_after_attempt(user_id: int, mock_id: str):
    """Aggregate per-question responses into subject/chapter/topic stats."""
    # Get all responses for this attempt with question tags
    responses = db_fetchall(
        """SELECT r.is_correct, r.is_skipped,
                  q.subject_id, q.chapter_id, q.topic_id
           FROM responses r
           JOIN questions q ON r.question_id = q.question_id
           WHERE r.user_id = ? AND r.attempt_id IN
               (SELECT attempt_id FROM attempts WHERE mock_id = ? ORDER BY submitted_at DESC LIMIT 1)""",
        (user_id, mock_id),
    )
    if not responses:
        return
    # Aggregate by subject
    for row in responses:
        sid = row["subject_id"]; cid = row["chapter_id"]; tid = row["topic_id"]
        if not sid:
            continue
        is_correct = row["is_correct"] or 0
        is_skipped = 1 if row.get("is_skipped") else 0
        wrong = 0 if is_correct or is_skipped else 1
        for table, id_col, id_val in [
            ("user_subject_stats", "subject_id", sid),
            ("user_chapter_stats", "chapter_id", cid),
            ("user_topic_stats", "topic_id", tid),
        ]:
            if not id_val:
                continue
            existing = db_fetchone(
                f"SELECT * FROM {table} WHERE user_id = ? AND {id_col} = ?",
                (user_id, id_val),
            )
            if existing:
                total = (existing["total_attempts"] or 0) + 1
                new_acc = round(
                    ((existing["correct_count"] or 0) + (1 if is_correct else 0)) / total * 100, 1
                )
                db_execute(
                    f"""UPDATE {table} SET total_attempts = ?, correct_count = correct_count + ?,
                        wrong_count = wrong_count + ?, skipped_count = skipped_count + ?,
                        accuracy = ?, last_attempted_at = ?
                        WHERE user_id = ? AND {id_col} = ?""",
                    (total, 1 if is_correct else 0, wrong, 1 if is_skipped else 0,
                     new_acc, _now(), user_id, id_val),
                )
            else:
                db_execute(
                    f"""INSERT INTO {table}
                        (user_id, {id_col}, total_attempts, correct_count, wrong_count,
                         skipped_count, accuracy, last_attempted_at)
                        VALUES (?, ?, 1, ?, ?, ?, ?, ?)""",
                    (user_id, id_val, 1 if is_correct else 0, wrong,
                     1 if is_skipped else 0,
                     round((1 if is_correct else 0) * 100, 1), _now()),
                )
    db_commit()


def get_user_subject_summary(user_id: int) -> List[Dict]:
    """Returns subject-wise accuracy + attempts for analytics."""
    return db_fetchall(
        """SELECT s.name as subject, s.id as subject_id,
                  COALESCE(uss.total_attempts, 0) as attempts,
                  COALESCE(uss.correct_count, 0) as correct,
                  COALESCE(uss.wrong_count, 0) as wrong,
                  COALESCE(uss.skipped_count, 0) as skipped,
                  COALESCE(uss.accuracy, 0) as accuracy
           FROM subjects s
           LEFT JOIN user_subject_stats uss ON s.id = uss.subject_id AND uss.user_id = ?
           WHERE COALESCE(uss.total_attempts, 0) > 0
           ORDER BY accuracy ASC""",
        (user_id,),
    )


def get_user_topic_breakdown(user_id: int, subject_id: int = None) -> List[Dict]:
    """Returns topic-wise breakdown for a subject."""
    q = """SELECT t.name as topic, t.id as topic_id,
                  c.name as chapter, s.name as subject,
                  COALESCE(uts.total_attempts, 0) as attempts,
                  COALESCE(uts.correct_count, 0) as correct,
                  COALESCE(uts.wrong_count, 0) as wrong,
                  COALESCE(uts.skipped_count, 0) as skipped,
                  COALESCE(uts.accuracy, 0) as accuracy
           FROM user_topic_stats uts
           JOIN topics t ON uts.topic_id = t.id
           JOIN chapters c ON t.chapter_id = c.id
           JOIN subjects s ON c.subject_id = s.id
           WHERE uts.user_id = ?"""
    params = [user_id]
    if subject_id:
        q += " AND uts.subject_id = ?"
        params.append(subject_id)
    q += " ORDER BY accuracy ASC"
    return db_fetchall(q, params)


def get_user_score_trend(user_id: int, limit: int = 10) -> List[Dict]:
    """Returns score history across mocks."""
    return db_fetchall(
        """SELECT a.total_score, a.correct_count, a.wrong_count, a.skipped_count,
                  a.accuracy, a.submitted_at, m.title as mock_title, m.section
           FROM attempts a
           LEFT JOIN mocks m ON a.mock_id = m.mock_id
           WHERE a.user_id = ? AND a.status = 'submitted'
           ORDER BY a.submitted_at DESC LIMIT ?""",
        (user_id, limit),
    )


def get_user_weak_areas(user_id: int, min_attempts: int = 3, top_n: int = 5) -> List[Dict]:
    """Returns weakest topics by accuracy, where user has min_attempts."""
    return db_fetchall(
        """SELECT t.name as topic, c.name as chapter, s.name as subject,
                  uts.accuracy, uts.total_attempts as attempts,
                  uts.correct_count as correct, uts.wrong_count as wrong
           FROM user_topic_stats uts
           JOIN topics t ON uts.topic_id = t.id
           JOIN chapters c ON t.chapter_id = c.id
           JOIN subjects s ON c.subject_id = s.id
           WHERE uts.user_id = ? AND uts.total_attempts >= ?
           ORDER BY uts.accuracy ASC LIMIT ?""",
        (user_id, min_attempts, top_n),
    )


def get_user_silly_mistakes(user_id: int, limit: int = 5) -> List[Dict]:
    """Detect easy questions answered wrong."""
    return db_fetchall(
        """SELECT q.text, q.q_number, r.time_spent_sec, m.title as mock_title
           FROM responses r
           JOIN questions q ON r.question_id = q.question_id
           JOIN attempts a ON r.attempt_id = a.attempt_id
           LEFT JOIN mocks m ON a.mock_id = m.mock_id
           WHERE r.user_id = ? AND r.is_correct = 0
             AND q.difficulty_level = 'easy'
           ORDER BY a.submitted_at DESC LIMIT ?""",
        (user_id, limit),
    )


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN QUERIES
# ═══════════════════════════════════════════════════════════════════════════

def get_admin_overview() -> Dict:
    """Return overview stats for /admin dashboard."""
    total_users = db_fetchone("SELECT COUNT(*) as cnt FROM users WHERE telegram_id != 0")
    active_today = db_fetchone(
        "SELECT COUNT(*) as cnt FROM users WHERE telegram_id != 0 AND last_active_date >= date('now')"
    )
    total_mocks = db_fetchone("SELECT COUNT(*) as cnt FROM mocks")
    total_attempts = db_fetchone("SELECT COUNT(*) as cnt FROM attempts")
    total_invites = db_fetchone("SELECT COUNT(*) as cnt FROM invites")
    verify_inv = db_fetchone("SELECT COUNT(*) as cnt FROM invites WHERE channel_verified = 1")
    paid_users = db_fetchone(
        "SELECT COUNT(*) as cnt FROM users WHERE free_access_expiry IS NOT NULL AND telegram_id != 0"
    )
    return {
        "total_users": (total_users["cnt"] if total_users else 0),
        "active_today": (active_today["cnt"] if active_today else 0),
        "total_mocks": (total_mocks["cnt"] if total_mocks else 0),
        "total_attempts": (total_attempts["cnt"] if total_attempts else 0),
        "total_invites": (total_invites["cnt"] if total_invites else 0),
        "verified_invites": (verify_inv["cnt"] if verify_inv else 0),
        "paid_users": (paid_users["cnt"] if paid_users else 0),
    }


def get_admin_users_list(limit: int = 30) -> List[sqlite3.Row]:
    """List all users with key stats."""
    return db_fetchall(
        """SELECT telegram_id, first_name, username,
                  COALESCE(xp,0) as xp, COALESCE(rank,'E') as rank,
                  free_access_expiry, invited_by,
                  (SELECT COUNT(*) FROM invites WHERE inviter_id = u.telegram_id) as invites_sent,
                  (SELECT COUNT(*) FROM attempts WHERE user_id = u.telegram_id) as mocks_taken
           FROM users u WHERE telegram_id != 0
           ORDER BY COALESCE(xp,0) DESC LIMIT ?""",
        (limit,),
    )


def get_admin_mocks_list(limit: int = 50) -> List[sqlite3.Row]:
    """List all mocks with stats."""
    return db_fetchall(
        """SELECT m.mock_id, m.title, m.section, m.question_count, m.created_at,
                  m.total_attempts,
                  (SELECT COUNT(*) FROM attempts a WHERE a.mock_id = m.mock_id) as actual_attempts,
                  (SELECT ROUND(AVG(a.total_score),1) FROM attempts a WHERE a.mock_id = m.mock_id) as avg_score,
                  (SELECT ROUND(AVG(a.accuracy),1) FROM attempts a WHERE a.mock_id = m.mock_id) as avg_accuracy
           FROM mocks m
           ORDER BY m.created_at DESC LIMIT ?""",
        (limit,),
    )


def get_user_deep_stats(user_id: int) -> Optional[Dict]:
    """Deep view of one user: all attempts, invites chain, access history."""
    user = db_fetchone("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    if not user:
        return None
    attempts = db_fetchall(
        """SELECT a.*, m.title as mock_title FROM attempts a
           LEFT JOIN mocks m ON a.mock_id = m.mock_id
           WHERE a.user_id = ? ORDER BY a.submitted_at DESC LIMIT 30""",
        (user_id,),
    )
    invites_sent = db_fetchall(
        """SELECT iv.*, u2.first_name as invited_name, u2.username as invited_username
           FROM invites iv LEFT JOIN users u2 ON iv.invited_id = u2.telegram_id
           WHERE iv.inviter_id = ? ORDER BY iv.created_at DESC LIMIT 20""",
        (user_id,),
    )
    invite_used = db_fetchone(
        "SELECT u2.first_name, u2.telegram_id FROM users u JOIN users u2 ON u.invited_by = u2.telegram_id WHERE u.telegram_id = ?",
        (user_id,),
    )
    return {
        "user": dict(user),
        "attempts": [dict(a) for a in (attempts or [])],
        "invites_sent": [dict(i) for i in (invites_sent or [])],
        "invited_by": dict(invite_used) if invite_used else None,
    }


def get_admin_invite_network(limit: int = 30) -> List[sqlite3.Row]:
    """Invite leaderboard with verification status."""
    return db_fetchall(
        """SELECT iv.inviter_id, u.first_name as inviter_name,
                  COUNT(iv.id) as total_invites,
                  SUM(CASE WHEN iv.channel_verified = 1 THEN 1 ELSE 0 END) as verified,
                  SUM(CASE WHEN iv.channel_verified = 0 THEN 1 ELSE 0 END) as unverified
           FROM invites iv
           JOIN users u ON iv.inviter_id = u.telegram_id
           GROUP BY iv.inviter_id
           ORDER BY total_invites DESC LIMIT ?""",
        (limit,),
    )


def get_admin_all_user_ids() -> List[int]:
    """Return all non-system user IDs for broadcast."""
    rows = db_fetchall("SELECT telegram_id FROM users WHERE telegram_id != 0")
    return [r["telegram_id"] for r in (rows or [])]


def log_admin_action(admin_id: int, action: str, target_id: Optional[int] = None,
                     detail: str = ""):
    """Log admin actions to a dedicated log table."""
    try:
        db_execute(
            "CREATE TABLE IF NOT EXISTS admin_log (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, target_id INTEGER, detail TEXT, timestamp TEXT DEFAULT (datetime('now')))"
        )
        db_commit()
        db_execute(
            "INSERT INTO admin_log (admin_id, action, target_id, detail) VALUES (?, ?, ?, ?)",
            (admin_id, action, target_id, detail),
        )
        db_commit()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# PvP CHALLENGES
# ═══════════════════════════════════════════════════════════════════════════

def create_challenge(challenger_id: int, mock_id: str) -> str:
    """Create a PvP challenge. Returns match_id for deep link."""
    import secrets
    match_id = secrets.token_hex(4)
    db_execute(
        "INSERT INTO challenges (match_id, challenger_id, mock_id) VALUES (?, ?, ?)",
        (match_id, challenger_id, mock_id),
    )
    db_commit()
    return match_id


def accept_challenge(match_id: str, rival_id: int) -> Optional[Dict]:
    """Rival accepts a challenge. Returns challenge dict or None."""
    ch = db_fetchone("SELECT * FROM challenges WHERE match_id = ? AND status = 'pending'", (match_id,))
    if not ch:
        return None
    db_execute(
        "UPDATE challenges SET rival_id = ?, status = 'accepted' WHERE match_id = ?",
        (rival_id, match_id),
    )
    db_commit()
    return dict(ch)


def complete_challenge(match_id: str, user_id: int, score: int, attempt_id: str) -> Optional[Dict]:
    """Record a player's score. If both done, determine winner and mark completed."""
    ch = db_fetchone("SELECT * FROM challenges WHERE match_id = ?", (match_id,))
    if not ch:
        return None
    if user_id == ch["challenger_id"] and not ch["challenger_score"]:
        db_execute("UPDATE challenges SET challenger_score = ?, challenger_attempt_id = ? WHERE match_id = ?",
                   (score, attempt_id, match_id))
    elif user_id == ch["rival_id"] and not ch["rival_score"]:
        db_execute("UPDATE challenges SET rival_score = ?, rival_attempt_id = ? WHERE match_id = ?",
                   (score, attempt_id, match_id))
    else:
        return dict(ch)
    db_commit()

    # Re-read after update
    ch = db_fetchone("SELECT * FROM challenges WHERE match_id = ?", (match_id,))
    # Check if both have scored
    if ch["challenger_score"] is not None and ch["rival_score"] is not None:
        winner = ch["challenger_id"] if (ch["challenger_score"] or 0) >= (ch["rival_score"] or 0) else ch["rival_id"]
        db_execute(
            "UPDATE challenges SET status = 'completed', winner_id = ?, completed_at = ? WHERE match_id = ?",
            (winner, _now(), match_id),
        )
        db_commit()
        ch = db_fetchone("SELECT * FROM challenges WHERE match_id = ?", (match_id,))
    return dict(ch) if ch else None


# ═══════════════════════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════════════════════

def init_db(admin_ids: Optional[List[int]] = None, added_by: int = 0):
    """Initialise DB and seed admin users + system user."""
    conn = _get_conn()
    # Ensure system user (ID 0) exists for CLI/automated uploads
    conn.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (0, 'system')")
    conn.commit()
    conn.executescript(SCHEMA)
    conn.commit()
    # Migrations for existing DBs
    try: conn.execute("ALTER TABLE users ADD COLUMN state_json TEXT"); conn.commit()
    except: pass
    try: conn.execute("ALTER TABLE invites ADD COLUMN action_verified INTEGER DEFAULT 0"); conn.commit()
    except: pass
    try: conn.execute("ALTER TABLE users ADD COLUMN premium_access_expiry TEXT"); conn.commit()
    except: pass
    try: conn.execute("ALTER TABLE users ADD COLUMN premium_tier TEXT DEFAULT 'free'"); conn.commit()
    except: pass
    # Taxonomy columns on questions
    for col in ["subject_id INTEGER", "chapter_id INTEGER", "topic_id INTEGER",
                "subtopic_id INTEGER", "difficulty_level TEXT DEFAULT 'medium'",
                "cognitive_level TEXT DEFAULT 'knowledge'", "concept_tags TEXT"]:
        try: conn.execute(f"ALTER TABLE questions ADD COLUMN {col}"); conn.commit()
        except: pass
    # Seed taxonomy
    _seed_taxonomy(conn)
    # Seed admins
    if admin_ids:
        for aid in admin_ids:
            get_or_create_user(aid)
            add_admin(aid, added_by)
    log.info("Database ready. Admins: %s", admin_ids)


def close_db():
    global _conn
    if _conn:
        _conn.close()
        _conn = None
