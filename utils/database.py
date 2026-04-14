"""
SQLite persistence layer for Sigmoji (via aiosqlite).

All public coroutines accept/return plain Python dicts or primitives so that
callers never need to import aiosqlite themselves.
"""

import os
import aiosqlite
from datetime import date, timedelta

DB_PATH = os.getenv("DATABASE_PATH", "sigmoji.db")


# ── Schema ────────────────────────────────────────────────────────────────────

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                user_id         INTEGER PRIMARY KEY,
                username        TEXT    NOT NULL,
                xp              INTEGER DEFAULT 0,
                total_wins      INTEGER DEFAULT 0,
                total_games     INTEGER DEFAULT 0,
                current_streak  INTEGER DEFAULT 0,
                best_streak     INTEGER DEFAULT 0,
                hint_free_wins  INTEGER DEFAULT 0,
                last_played     TEXT,
                created_at      TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS category_stats (
                user_id  INTEGER NOT NULL,
                category TEXT    NOT NULL,
                wins     INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, category)
            );

            CREATE TABLE IF NOT EXISTS achievements (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                achievement_id TEXT    NOT NULL,
                unlocked_at    TEXT    DEFAULT (datetime('now')),
                UNIQUE(user_id, achievement_id)
            );

            CREATE TABLE IF NOT EXISTS game_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                category   TEXT    NOT NULL,
                answer     TEXT    NOT NULL,
                elapsed    REAL    NOT NULL,
                points     INTEGER NOT NULL,
                hints_used INTEGER DEFAULT 0,
                difficulty TEXT    NOT NULL,
                played_at  TEXT    DEFAULT (datetime('now'))
            );
        """)
        await db.commit()


# ── Player helpers ────────────────────────────────────────────────────────────

async def get_player(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def ensure_player(user_id: int, username: str) -> dict:
    """Fetch player, creating a fresh row if they don't exist yet."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR IGNORE INTO players (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        await db.execute(
            "UPDATE players SET username = ? WHERE user_id = ?",
            (username, user_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM players WHERE user_id = ?", (user_id,)
        ) as cur:
            return dict(await cur.fetchone())


# ── Win recording ─────────────────────────────────────────────────────────────

async def record_win(
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
    today       = str(date.today())
    yesterday   = str(date.today() - timedelta(days=1))

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Ensure row exists
        await db.execute(
            "INSERT OR IGNORE INTO players (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        await db.execute(
            "UPDATE players SET username = ? WHERE user_id = ?",
            (username, user_id),
        )

        async with db.execute(
            "SELECT * FROM players WHERE user_id = ?", (user_id,)
        ) as cur:
            player = dict(await cur.fetchone())

        # ── Streak logic ──────────────────────────────────────────────────────
        last_played   = player.get("last_played")
        daily_bonus   = 0

        if last_played == today:
            # Already played today — streak doesn't change, no daily bonus
            new_streak  = player["current_streak"]
        elif last_played == yesterday:
            # Consecutive day — streak grows
            new_streak  = player["current_streak"] + 1
            daily_bonus = min(new_streak, 10) * 5  # +5 to +50
        else:
            # First time or streak broken
            new_streak  = 1
            daily_bonus = 5

        total_xp   = points + daily_bonus
        new_best   = max(new_streak, player["best_streak"])
        new_hint_free = (
            player["hint_free_wins"] + 1 if hints_used == 0
            else player["hint_free_wins"]
        )

        # ── Update player row ─────────────────────────────────────────────────
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
            WHERE user_id = ?
            """,
            (total_xp, new_streak, new_best, new_hint_free, today, user_id),
        )

        # ── Category stats ────────────────────────────────────────────────────
        await db.execute(
            """
            INSERT INTO category_stats (user_id, category, wins) VALUES (?, ?, 1)
            ON CONFLICT(user_id, category) DO UPDATE SET wins = wins + 1
            """,
            (user_id, category),
        )

        # ── Game history ──────────────────────────────────────────────────────
        await db.execute(
            """
            INSERT INTO game_history
                (user_id, category, answer, elapsed, points, hints_used, difficulty)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, category, answer, round(elapsed, 2), total_xp, hints_used, difficulty),
        )

        await db.commit()

        # Return fresh player data
        async with db.execute(
            "SELECT * FROM players WHERE user_id = ?", (user_id,)
        ) as cur:
            updated = dict(await cur.fetchone())

        return updated, daily_bonus


async def record_timeout(user_id: int, username: str) -> None:
    """Increment total_games for a player who didn't answer (timeout)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO players (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        await db.execute(
            "UPDATE players SET total_games = total_games + 1 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


# ── Achievements ──────────────────────────────────────────────────────────────

async def get_achievements(user_id: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT achievement_id FROM achievements WHERE user_id = ? ORDER BY unlocked_at",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [r[0] for r in rows]


async def unlock_achievement(user_id: int, achievement_id: str) -> bool:
    """
    Try to unlock an achievement. Returns True if newly unlocked (first time),
    False if the player already had it.
    """
    from utils.achievements import ACHIEVEMENTS

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO achievements (user_id, achievement_id) VALUES (?, ?)",
                (user_id, achievement_id),
            )
            xp_reward = ACHIEVEMENTS.get(achievement_id, {}).get("xp", 0)
            if xp_reward:
                await db.execute(
                    "UPDATE players SET xp = xp + ? WHERE user_id = ?",
                    (xp_reward, user_id),
                )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False  # Already unlocked


# ── Leaderboard ───────────────────────────────────────────────────────────────

async def get_leaderboard(category: str | None = None, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if category:
            async with db.execute(
                """
                SELECT p.user_id, p.username, cs.wins AS total_wins, p.xp
                FROM   category_stats cs
                JOIN   players p ON p.user_id = cs.user_id
                WHERE  cs.category = ?
                ORDER  BY cs.wins DESC, p.xp DESC
                LIMIT  ?
                """,
                (category, limit),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                """
                SELECT user_id, username, total_wins, xp
                FROM   players
                ORDER  BY total_wins DESC, xp DESC
                LIMIT  ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_player_rank(user_id: int, category: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        if category:
            async with db.execute(
                """
                SELECT COUNT(*) + 1 FROM category_stats
                WHERE  wins > COALESCE(
                    (SELECT wins FROM category_stats WHERE user_id = ? AND category = ?),
                    -1
                )
                AND category = ?
                """,
                (user_id, category, category),
            ) as cur:
                row = await cur.fetchone()
        else:
            async with db.execute(
                """
                SELECT COUNT(*) + 1 FROM players
                WHERE  total_wins > COALESCE(
                    (SELECT total_wins FROM players WHERE user_id = ?),
                    -1
                )
                """,
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else 1


async def get_category_stats(user_id: int) -> dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT category, wins FROM category_stats WHERE user_id = ? ORDER BY wins DESC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return {r[0]: r[1] for r in rows}
