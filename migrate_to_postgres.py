"""
One-time migration script: SQLite (sigmoji.db) → Railway PostgreSQL.

Usage:
    pip install aiosqlite asyncpg python-dotenv
    python migrate_to_postgres.py

Reads DATABASE_URL from .env (or env var) for the Postgres target.
Reads the SQLite file from data/sigmoji.db (or DATABASE_PATH env var).
"""

import asyncio
import os
import sys
from pathlib import Path

import aiosqlite
import asyncpg
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH  = os.getenv("DATABASE_PATH", str(Path(__file__).parent / "data" / "sigmoji.db"))
DATABASE_URL = os.getenv("DATABASE_URL", "")


async def migrate():

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set. Check your .env file.")
        sys.exit(1)

    if not Path(SQLITE_PATH).exists():
        print(f"WARNING: SQLite file not found at {SQLITE_PATH}")
        print("No legacy data will be migrated. Starting fresh with Postgres.")
        # Optionally, create empty tables in Postgres if needed
        pg = await asyncpg.connect(DATABASE_URL)
        try:
            await pg.execute("""
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
                );
                CREATE TABLE IF NOT EXISTS category_stats (
                    guild_id    BIGINT  NOT NULL,
                    user_id     BIGINT  NOT NULL,
                    category    TEXT    NOT NULL,
                    wins        INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id, category)
                );
                CREATE TABLE IF NOT EXISTS achievements (
                    guild_id        BIGINT  NOT NULL,
                    user_id         BIGINT  NOT NULL,
                    achievement_id  TEXT    NOT NULL,
                    unlocked_at     TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (guild_id, user_id, achievement_id)
                );
                CREATE TABLE IF NOT EXISTS game_history (
                    guild_id    BIGINT  NOT NULL,
                    user_id     BIGINT  NOT NULL,
                    category    TEXT    NOT NULL,
                    answer      TEXT    NOT NULL,
                    elapsed     INTEGER DEFAULT 0,
                    points      INTEGER DEFAULT 0,
                    hints_used  INTEGER DEFAULT 0,
                    difficulty  TEXT    NOT NULL,
                    played_at   TIMESTAMP DEFAULT NOW()
                );
            """)
            print("✅ Postgres tables ensured. Fresh start complete.")
        finally:
            await pg.close()
        return

    print(f"SQLite source : {SQLITE_PATH}")
    print(f"Postgres target: {DATABASE_URL[:40]}...")
    print()

    # ── Connect to both ──────────────────────────────────────────────────────
    pg = await asyncpg.connect(DATABASE_URL)
    sq = await aiosqlite.connect(SQLITE_PATH)
    sq.row_factory = aiosqlite.Row

    try:
        # ── Create tables in Postgres ─────────────────────────────────────────
        await pg.execute("""
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
        """)
        await pg.execute("""
            CREATE TABLE IF NOT EXISTS category_stats (
                guild_id BIGINT  NOT NULL,
                user_id  BIGINT  NOT NULL,
                category TEXT    NOT NULL,
                wins     INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, category)
            )
        """)
        await pg.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                id             SERIAL PRIMARY KEY,
                guild_id       BIGINT NOT NULL,
                user_id        BIGINT NOT NULL,
                achievement_id TEXT   NOT NULL,
                unlocked_at    TIMESTAMP DEFAULT NOW(),
                UNIQUE(guild_id, user_id, achievement_id)
            )
        """)
        await pg.execute("""
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
        """)
        await pg.execute("CREATE INDEX IF NOT EXISTS idx_players_guild      ON players(guild_id)")
        await pg.execute("CREATE INDEX IF NOT EXISTS idx_cat_stats_guild    ON category_stats(guild_id)")
        await pg.execute("CREATE INDEX IF NOT EXISTS idx_achievements_guild ON achievements(guild_id)")
        await pg.execute("CREATE INDEX IF NOT EXISTS idx_game_history_guild ON game_history(guild_id)")
        print("✅ Postgres tables created.")

        # ── Migrate players ───────────────────────────────────────────────────
        async with sq.execute("SELECT * FROM players") as cur:
            rows = [dict(r) for r in await cur.fetchall()]
        if rows:
            await pg.executemany(
                """
                INSERT INTO players (guild_id, user_id, username, xp, total_wins, total_games,
                                     current_streak, best_streak, hint_free_wins, last_played)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (guild_id, user_id) DO NOTHING
                """,
                [
                    (r["guild_id"], r["user_id"], r["username"], r["xp"],
                     r["total_wins"], r["total_games"], r["current_streak"],
                     r["best_streak"], r["hint_free_wins"], r["last_played"])
                    for r in rows
                ],
            )
        print(f"   players: {len(rows)} rows migrated.")

        # ── Migrate category_stats ────────────────────────────────────────────
        async with sq.execute("SELECT * FROM category_stats") as cur:
            rows = [dict(r) for r in await cur.fetchall()]
        if rows:
            await pg.executemany(
                """
                INSERT INTO category_stats (guild_id, user_id, category, wins)
                VALUES ($1,$2,$3,$4)
                ON CONFLICT (guild_id, user_id, category) DO NOTHING
                """,
                [(r["guild_id"], r["user_id"], r["category"], r["wins"]) for r in rows],
            )
        print(f"   category_stats: {len(rows)} rows migrated.")

        # ── Migrate achievements ──────────────────────────────────────────────
        async with sq.execute("SELECT * FROM achievements") as cur:
            rows = [dict(r) for r in await cur.fetchall()]
        if rows:
            await pg.executemany(
                """
                INSERT INTO achievements (guild_id, user_id, achievement_id)
                VALUES ($1,$2,$3)
                ON CONFLICT (guild_id, user_id, achievement_id) DO NOTHING
                """,
                [(r["guild_id"], r["user_id"], r["achievement_id"]) for r in rows],
            )
        print(f"   achievements: {len(rows)} rows migrated.")

        # ── Migrate game_history ──────────────────────────────────────────────
        async with sq.execute("SELECT * FROM game_history") as cur:
            rows = [dict(r) for r in await cur.fetchall()]
        if rows:
            await pg.executemany(
                """
                INSERT INTO game_history (guild_id, user_id, category, answer, elapsed, points, hints_used, difficulty)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                [
                    (r["guild_id"], r["user_id"], r["category"], r["answer"],
                     r["elapsed"], r["points"], r["hints_used"], r["difficulty"])
                    for r in rows
                ],
            )
        print(f"   game_history: {len(rows)} rows migrated.")

        print()
        print("🎉 Migration complete! All data has been transferred to PostgreSQL.")

    finally:
        await pg.close()
        await sq.close()


if __name__ == "__main__":
    asyncio.run(migrate())
