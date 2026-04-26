"""
PostgreSQL persistence layer for Sigmoji (via asyncpg).

All public coroutines accept/return plain Python dicts or primitives so that
callers never need to import asyncpg themselves.

Every function takes guild_id as its first parameter — all data is strictly
scoped to the Discord server it originates from.
"""

import logging
import os
import asyncpg
from datetime import date, timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "")

log = logging.getLogger("sigmoji.db")

# ── Connection pool ───────────────────────────────────────────────────────────

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ── DDL ───────────────────────────────────────────────────────────────────────

_CREATE_TABLES_DDL = [
    """
    CREATE TABLE IF NOT EXISTS players (
        guild_id        BIGINT  NOT NULL,
        user_id         BIGINT  NOT NULL,
        username        TEXT    NOT NULL,
        xp              INTEGER DEFAULT 0,
        total_wins      INTEGER DEFAULT 0,
        total_games     INTEGER DEFAULT 0,
        current_streak  INTEGER DEFAULT 0,
        best_streak     INTEGER DEFAULT 0,
        hint_free_wins  INTEGER DEFAULT 0,
        last_played     TEXT,
        created_at      TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS category_stats (
        guild_id BIGINT  NOT NULL,
        user_id  BIGINT  NOT NULL,
        category TEXT    NOT NULL,
        wins     INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, category)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS achievements (
        id             SERIAL PRIMARY KEY,
        guild_id       BIGINT NOT NULL,
        user_id        BIGINT NOT NULL,
        achievement_id TEXT   NOT NULL,
        unlocked_at    TIMESTAMP DEFAULT NOW(),
        UNIQUE(guild_id, user_id, achievement_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_history (
        id         SERIAL  PRIMARY KEY,
        guild_id   BIGINT  NOT NULL,
        user_id    BIGINT  NOT NULL,
        category   TEXT    NOT NULL,
        answer     TEXT    NOT NULL,
        elapsed    DOUBLE PRECISION NOT NULL,
        points     INTEGER NOT NULL,
        hints_used INTEGER DEFAULT 0,
        difficulty TEXT    NOT NULL,
        played_at  TIMESTAMP DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_players_guild      ON players(guild_id)",
    "CREATE INDEX IF NOT EXISTS idx_cat_stats_guild    ON category_stats(guild_id)",
    "CREATE INDEX IF NOT EXISTS idx_achievements_guild ON achievements(guild_id)",
    "CREATE INDEX IF NOT EXISTS idx_game_history_guild ON game_history(guild_id)",
]


# ── Schema init ───────────────────────────────────────────────────────────────

async def init_db() -> None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        for stmt in _CREATE_TABLES_DDL:
            await conn.execute(stmt)
    log.info("PostgreSQL schema initialised.")


# ── Player helpers ────────────────────────────────────────────────────────────

async def get_player(guild_id: int, user_id: int) -> dict | None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM players WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
        return dict(row) if row else None


async def ensure_player(guild_id: int, user_id: int, username: str) -> dict:
    """Fetch player, creating a fresh row if they don't exist yet."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO players (guild_id, user_id, username)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET username = $3
            """,
            guild_id, user_id, username,
        )
        row = await conn.fetchrow(
            "SELECT * FROM players WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
        return dict(row)


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

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO players (guild_id, user_id, username)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET username = $3
                """,
                guild_id, user_id, username,
            )

            player = dict(await conn.fetchrow(
                "SELECT * FROM players WHERE guild_id = $1 AND user_id = $2",
                guild_id, user_id,
            ))

            # ── Streak logic ──────────────────────────────────────────────────
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

            await conn.execute(
                """
                UPDATE players SET
                    xp             = xp + $1,
                    total_wins     = total_wins + 1,
                    total_games    = total_games + 1,
                    current_streak = $2,
                    best_streak    = $3,
                    hint_free_wins = $4,
                    last_played    = $5
                WHERE guild_id = $6 AND user_id = $7
                """,
                total_xp, new_streak, new_best, new_hint_free, today,
                guild_id, user_id,
            )

            await conn.execute(
                """
                INSERT INTO category_stats (guild_id, user_id, category, wins)
                VALUES ($1, $2, $3, 1)
                ON CONFLICT (guild_id, user_id, category)
                DO UPDATE SET wins = category_stats.wins + 1
                """,
                guild_id, user_id, category,
            )

            await conn.execute(
                """
                INSERT INTO game_history
                    (guild_id, user_id, category, answer, elapsed, points, hints_used, difficulty)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                guild_id, user_id, category, answer,
                round(elapsed, 2), total_xp, hints_used, difficulty,
            )

            updated = dict(await conn.fetchrow(
                "SELECT * FROM players WHERE guild_id = $1 AND user_id = $2",
                guild_id, user_id,
            ))

        return updated, daily_bonus


async def record_timeout(guild_id: int, user_id: int, username: str) -> None:
    """Increment total_games for a player who didn't answer (timeout)."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO players (guild_id, user_id, username)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, user_id) DO NOTHING
            """,
            guild_id, user_id, username,
        )
        await conn.execute(
            "UPDATE players SET total_games = total_games + 1 WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )


# ── Achievements ──────────────────────────────────────────────────────────────

async def get_achievements(guild_id: int, user_id: int) -> list[str]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT achievement_id FROM achievements WHERE guild_id = $1 AND user_id = $2 ORDER BY unlocked_at",
            guild_id, user_id,
        )
        return [r["achievement_id"] for r in rows]


async def unlock_achievement(guild_id: int, user_id: int, achievement_id: str) -> bool:
    """
    Try to unlock an achievement. Returns True if newly unlocked,
    False if the player already had it.
    """
    from utils.achievements import ACHIEVEMENTS

    pool = await _get_pool()
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO achievements (guild_id, user_id, achievement_id) VALUES ($1, $2, $3)",
                    guild_id, user_id, achievement_id,
                )
                xp_reward = ACHIEVEMENTS.get(achievement_id, {}).get("xp", 0)
                if xp_reward:
                    await conn.execute(
                        "UPDATE players SET xp = xp + $1 WHERE guild_id = $2 AND user_id = $3",
                        xp_reward, guild_id, user_id,
                    )
            return True
        except asyncpg.UniqueViolationError:
            return False


# ── Leaderboard ───────────────────────────────────────────────────────────────

async def get_leaderboard(guild_id: int, category: str | None = None, limit: int = 10) -> list[dict]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        if category:
            rows = await conn.fetch(
                """
                SELECT p.user_id, p.username, cs.wins AS total_wins, p.xp
                FROM   category_stats cs
                JOIN   players p ON p.guild_id = cs.guild_id AND p.user_id = cs.user_id
                WHERE  cs.guild_id = $1 AND cs.category = $2
                ORDER  BY cs.wins DESC, p.xp DESC
                LIMIT  $3
                """,
                guild_id, category, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT user_id, username, total_wins, xp
                FROM   players
                WHERE  guild_id = $1
                ORDER  BY total_wins DESC, xp DESC
                LIMIT  $2
                """,
                guild_id, limit,
            )
        return [dict(r) for r in rows]


async def get_player_rank(guild_id: int, user_id: int, category: str | None = None) -> int:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        if category:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) + 1 AS rank FROM category_stats
                WHERE  guild_id = $1
                AND    wins > COALESCE(
                    (SELECT wins FROM category_stats
                     WHERE guild_id = $1 AND user_id = $2 AND category = $3),
                    -1
                )
                AND category = $3
                """,
                guild_id, user_id, category,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) + 1 AS rank FROM players
                WHERE  guild_id = $1
                AND    total_wins > COALESCE(
                    (SELECT total_wins FROM players WHERE guild_id = $1 AND user_id = $2),
                    -1
                )
                """,
                guild_id, user_id,
            )
        return row["rank"] if row else 1


async def get_category_stats(guild_id: int, user_id: int) -> dict[str, int]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT category, wins FROM category_stats WHERE guild_id = $1 AND user_id = $2 ORDER BY wins DESC",
            guild_id, user_id,
        )
        return {r["category"]: r["wins"] for r in rows}


async def get_all_guild_players(guild_id: int) -> list[dict]:
    """Return every player row for a guild (used by the daily reminder)."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM players WHERE guild_id = $1 ORDER BY xp DESC",
            guild_id,
        )
        return [dict(r) for r in rows]
