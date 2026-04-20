"""
SQLite persistence layer for Sigmoji (via aiosqlite).

All public coroutines accept/return plain Python dicts or primitives so that
callers never need to import aiosqlite themselves.

Every function takes guild_id as its first parameter — all data is strictly
scoped to the Discord server it originates from.
"""

import logging
import os
import aiosqlite
from datetime import date, timedelta

DB_PATH = os.getenv("DATABASE_PATH", "sigmoji.db")

log = logging.getLogger("sigmoji.db")

# ── DDL ───────────────────────────────────────────────────────────────────────

_CREATE_TABLES_DDL = """
    CREATE TABLE IF NOT EXISTS players (
        guild_id        INTEGER NOT NULL,
        user_id         INTEGER NOT NULL,
        username        TEXT    NOT NULL,
        xp              INTEGER DEFAULT 0,
        total_wins      INTEGER DEFAULT 0,
        total_games     INTEGER DEFAULT 0,
        current_streak  INTEGER DEFAULT 0,
        best_streak     INTEGER DEFAULT 0,
        hint_free_wins  INTEGER DEFAULT 0,
        last_played     TEXT,
        created_at      TEXT    DEFAULT (datetime('now')),
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS category_stats (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        category TEXT    NOT NULL,
        wins     INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, category)
    );

    CREATE TABLE IF NOT EXISTS achievements (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id       INTEGER NOT NULL,
        user_id        INTEGER NOT NULL,
        achievement_id TEXT    NOT NULL,
        unlocked_at    TEXT    DEFAULT (datetime('now')),
        UNIQUE(guild_id, user_id, achievement_id)
    );

    CREATE TABLE IF NOT EXISTS game_history (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        category   TEXT    NOT NULL,
        answer     TEXT    NOT NULL,
        elapsed    REAL    NOT NULL,
        points     INTEGER NOT NULL,
        hints_used INTEGER DEFAULT 0,
        difficulty TEXT    NOT NULL,
        played_at  TEXT    DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_players_guild     ON players(guild_id);
    CREATE INDEX IF NOT EXISTS idx_cat_stats_guild   ON category_stats(guild_id);
    CREATE INDEX IF NOT EXISTS idx_achievements_guild ON achievements(guild_id);
    CREATE INDEX IF NOT EXISTS idx_game_history_guild ON game_history(guild_id);
"""

# Migration: old schema had no guild_id column. Existing data is preserved
# under guild_id=0 (a sentinel; no real Discord guild has ID 0).
_MIGRATION_DDL = """
    ALTER TABLE players       RENAME TO _bak_players;
    ALTER TABLE category_stats RENAME TO _bak_category_stats;
    ALTER TABLE achievements   RENAME TO _bak_achievements;
    ALTER TABLE game_history   RENAME TO _bak_game_history;

    CREATE TABLE players (
        guild_id        INTEGER NOT NULL,
        user_id         INTEGER NOT NULL,
        username        TEXT    NOT NULL,
        xp              INTEGER DEFAULT 0,
        total_wins      INTEGER DEFAULT 0,
        total_games     INTEGER DEFAULT 0,
        current_streak  INTEGER DEFAULT 0,
        best_streak     INTEGER DEFAULT 0,
        hint_free_wins  INTEGER DEFAULT 0,
        last_played     TEXT,
        created_at      TEXT    DEFAULT (datetime('now')),
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE category_stats (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        category TEXT    NOT NULL,
        wins     INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, category)
    );

    CREATE TABLE achievements (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id       INTEGER NOT NULL,
        user_id        INTEGER NOT NULL,
        achievement_id TEXT    NOT NULL,
        unlocked_at    TEXT    DEFAULT (datetime('now')),
        UNIQUE(guild_id, user_id, achievement_id)
    );

    CREATE TABLE game_history (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        category   TEXT    NOT NULL,
        answer     TEXT    NOT NULL,
        elapsed    REAL    NOT NULL,
        points     INTEGER NOT NULL,
        hints_used INTEGER DEFAULT 0,
        difficulty TEXT    NOT NULL,
        played_at  TEXT    DEFAULT (datetime('now'))
    );

    INSERT INTO players
        (guild_id, user_id, username, xp, total_wins, total_games,
         current_streak, best_streak, hint_free_wins, last_played, created_at)
        SELECT 0, user_id, username, xp, total_wins, total_games,
               current_streak, best_streak, hint_free_wins, last_played, created_at
        FROM _bak_players;

    INSERT INTO category_stats (guild_id, user_id, category, wins)
        SELECT 0, user_id, category, wins
        FROM _bak_category_stats;

    INSERT INTO achievements (guild_id, user_id, achievement_id, unlocked_at)
        SELECT 0, user_id, achievement_id, unlocked_at
        FROM _bak_achievements;

    INSERT INTO game_history
        (guild_id, user_id, category, answer, elapsed, points, hints_used, difficulty, played_at)
        SELECT 0, user_id, category, answer, elapsed, points, hints_used, difficulty, played_at
        FROM _bak_game_history;

    DROP TABLE _bak_players;
    DROP TABLE _bak_category_stats;
    DROP TABLE _bak_achievements;
    DROP TABLE _bak_game_history;
"""


# ── Schema init / migration ───────────────────────────────────────────────────

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        # Detect whether an old (guild-unaware) schema exists and migrate it.
        async with db.execute("PRAGMA table_info(players)") as cur:
            player_cols = {row[1] for row in await cur.fetchall()}

        if player_cols and "guild_id" not in player_cols:
            log.info("Migrating schema to guild-scoped tables…")
            await db.executescript(_MIGRATION_DDL)
            log.info("Schema migration complete — pre-existing data lives under guild_id=0.")

        await db.executescript(_CREATE_TABLES_DDL)
        await db.commit()


# ── Player helpers ────────────────────────────────────────────────────────────

async def get_player(guild_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def ensure_player(guild_id: int, user_id: int, username: str) -> dict:
    """Fetch player, creating a fresh row if they don't exist yet."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR IGNORE INTO players (guild_id, user_id, username) VALUES (?, ?, ?)",
            (guild_id, user_id, username),
        )
        await db.execute(
            "UPDATE players SET username = ? WHERE guild_id = ? AND user_id = ?",
            (username, guild_id, user_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM players WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            return dict(await cur.fetchone())


# ── Win recording ─────────────────────────────────────────────────────────────

async def record_win(
    guild_id: int,
    user_id: int,
    username: str,
    category: str,
    answer: str,
    elapsed: float,
    points: int,
    hints_used: int,
    difficulty: str,
) -> tuple[dict, int]:
    """
    Persist a win and update all derived counters.

    Returns: (updated_player_dict, daily_streak_bonus_awarded)
    """
    today     = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        await db.execute(
            "INSERT OR IGNORE INTO players (guild_id, user_id, username) VALUES (?, ?, ?)",
            (guild_id, user_id, username),
        )
        await db.execute(
            "UPDATE players SET username = ? WHERE guild_id = ? AND user_id = ?",
            (username, guild_id, user_id),
        )

        async with db.execute(
            "SELECT * FROM players WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            player = dict(await cur.fetchone())

        # ── Streak logic ──────────────────────────────────────────────────────
        last_played = player.get("last_played")
        daily_bonus = 0

        if last_played == today:
            new_streak = player["current_streak"]
        elif last_played == yesterday:
            new_streak  = player["current_streak"] + 1
            daily_bonus = min(new_streak, 10) * 5
        else:
            new_streak  = 1
            daily_bonus = 5

        total_xp      = points + daily_bonus
        new_best      = max(new_streak, player["best_streak"])
        new_hint_free = (
            player["hint_free_wins"] + 1 if hints_used == 0
            else player["hint_free_wins"]
        )

        await db.execute(
            """
            UPDATE players SET
                xp             = xp + ?,
                total_wins     = total_wins + 1,
                total_games    = total_games + 1,
                current_streak = ?,
                best_streak    = ?,
                hint_free_wins = ?,
                last_played    = ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (total_xp, new_streak, new_best, new_hint_free, today, guild_id, user_id),
        )

        await db.execute(
            """
            INSERT INTO category_stats (guild_id, user_id, category, wins) VALUES (?, ?, ?, 1)
            ON CONFLICT(guild_id, user_id, category) DO UPDATE SET wins = wins + 1
            """,
            (guild_id, user_id, category),
        )

        await db.execute(
            """
            INSERT INTO game_history
                (guild_id, user_id, category, answer, elapsed, points, hints_used, difficulty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, category, answer, round(elapsed, 2), total_xp, hints_used, difficulty),
        )

        await db.commit()

        async with db.execute(
            "SELECT * FROM players WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            updated = dict(await cur.fetchone())

        return updated, daily_bonus


async def record_timeout(guild_id: int, user_id: int, username: str) -> None:
    """Increment total_games for a player who didn't answer (timeout)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO players (guild_id, user_id, username) VALUES (?, ?, ?)",
            (guild_id, user_id, username),
        )
        await db.execute(
            "UPDATE players SET total_games = total_games + 1 WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()


# ── Achievements ──────────────────────────────────────────────────────────────

async def get_achievements(guild_id: int, user_id: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT achievement_id FROM achievements WHERE guild_id = ? AND user_id = ? ORDER BY unlocked_at",
            (guild_id, user_id),
        ) as cur:
            rows = await cur.fetchall()
        return [r[0] for r in rows]


async def unlock_achievement(guild_id: int, user_id: int, achievement_id: str) -> bool:
    """
    Try to unlock an achievement. Returns True if newly unlocked,
    False if the player already had it.
    """
    from utils.achievements import ACHIEVEMENTS

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO achievements (guild_id, user_id, achievement_id) VALUES (?, ?, ?)",
                (guild_id, user_id, achievement_id),
            )
            xp_reward = ACHIEVEMENTS.get(achievement_id, {}).get("xp", 0)
            if xp_reward:
                await db.execute(
                    "UPDATE players SET xp = xp + ? WHERE guild_id = ? AND user_id = ?",
                    (xp_reward, guild_id, user_id),
                )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


# ── Leaderboard ───────────────────────────────────────────────────────────────

async def get_leaderboard(guild_id: int, category: str | None = None, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if category:
            async with db.execute(
                """
                SELECT p.user_id, p.username, cs.wins AS total_wins, p.xp
                FROM   category_stats cs
                JOIN   players p ON p.guild_id = cs.guild_id AND p.user_id = cs.user_id
                WHERE  cs.guild_id = ? AND cs.category = ?
                ORDER  BY cs.wins DESC, p.xp DESC
                LIMIT  ?
                """,
                (guild_id, category, limit),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                """
                SELECT user_id, username, total_wins, xp
                FROM   players
                WHERE  guild_id = ?
                ORDER  BY total_wins DESC, xp DESC
                LIMIT  ?
                """,
                (guild_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_player_rank(guild_id: int, user_id: int, category: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        if category:
            async with db.execute(
                """
                SELECT COUNT(*) + 1 FROM category_stats
                WHERE  guild_id = ?
                AND    wins > COALESCE(
                    (SELECT wins FROM category_stats
                     WHERE guild_id = ? AND user_id = ? AND category = ?),
                    -1
                )
                AND category = ?
                """,
                (guild_id, guild_id, user_id, category, category),
            ) as cur:
                row = await cur.fetchone()
        else:
            async with db.execute(
                """
                SELECT COUNT(*) + 1 FROM players
                WHERE  guild_id = ?
                AND    total_wins > COALESCE(
                    (SELECT total_wins FROM players WHERE guild_id = ? AND user_id = ?),
                    -1
                )
                """,
                (guild_id, guild_id, user_id),
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else 1


async def get_category_stats(guild_id: int, user_id: int) -> dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT category, wins FROM category_stats WHERE guild_id = ? AND user_id = ? ORDER BY wins DESC",
            (guild_id, user_id),
        ) as cur:
            rows = await cur.fetchall()
        return {r[0]: r[1] for r in rows}
