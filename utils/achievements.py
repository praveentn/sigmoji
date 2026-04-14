"""
Achievement definitions for Sigmoji.

Each achievement has:
  id         - used as the DB key
  name       - display name
  desc       - short description shown in /achievements
  emoji      - badge emoji shown in profile
  xp         - XP reward on first unlock
  tier       - bronze / silver / gold / diamond
"""

ACHIEVEMENTS: dict[str, dict] = {
    # ── Onboarding ────────────────────────────────────────────────────────────
    "first_win": {
        "name": "First Blood",
        "desc": "Win your very first round",
        "emoji": "🩸",
        "xp": 50,
        "tier": "bronze",
    },

    # ── Speed ─────────────────────────────────────────────────────────────────
    "speed_10": {
        "name": "Quick Draw",
        "desc": "Answer correctly in under 10 seconds",
        "emoji": "⚡",
        "xp": 75,
        "tier": "bronze",
    },
    "speed_5": {
        "name": "Lightning",
        "desc": "Answer correctly in under 5 seconds",
        "emoji": "🌩️",
        "xp": 200,
        "tier": "silver",
    },
    "speed_3": {
        "name": "Telepathic",
        "desc": "Answer correctly in under 3 seconds",
        "emoji": "🔮",
        "xp": 500,
        "tier": "gold",
    },

    # ── Win milestones ────────────────────────────────────────────────────────
    "wins_5": {
        "name": "Getting Started",
        "desc": "Win 5 total games",
        "emoji": "🌱",
        "xp": 75,
        "tier": "bronze",
    },
    "wins_25": {
        "name": "Hooked",
        "desc": "Win 25 total games",
        "emoji": "🪝",
        "xp": 150,
        "tier": "bronze",
    },
    "wins_100": {
        "name": "Centurion",
        "desc": "Win 100 total games",
        "emoji": "💯",
        "xp": 500,
        "tier": "silver",
    },
    "wins_500": {
        "name": "Unstoppable",
        "desc": "Win 500 total games",
        "emoji": "🌪️",
        "xp": 1500,
        "tier": "gold",
    },
    "wins_1000": {
        "name": "Legend",
        "desc": "Win 1000 total games",
        "emoji": "🏆",
        "xp": 5000,
        "tier": "diamond",
    },

    # ── Streaks ───────────────────────────────────────────────────────────────
    "streak_3": {
        "name": "On Fire",
        "desc": "Maintain a 3-day play streak",
        "emoji": "🔥",
        "xp": 75,
        "tier": "bronze",
    },
    "streak_7": {
        "name": "Committed",
        "desc": "Maintain a 7-day play streak",
        "emoji": "🔥🔥",
        "xp": 200,
        "tier": "silver",
    },
    "streak_30": {
        "name": "Inferno",
        "desc": "Maintain a 30-day play streak",
        "emoji": "🌋",
        "xp": 1000,
        "tier": "gold",
    },
    "streak_100": {
        "name": "Eternal Flame",
        "desc": "Maintain a 100-day play streak",
        "emoji": "♾️",
        "xp": 5000,
        "tier": "diamond",
    },

    # ── Categories ────────────────────────────────────────────────────────────
    "cat_master": {
        "name": "Category Lover",
        "desc": "Win 10 games in a single category",
        "emoji": "🎯",
        "xp": 150,
        "tier": "bronze",
    },
    "cat_expert": {
        "name": "Category Expert",
        "desc": "Win 50 games in a single category",
        "emoji": "🏅",
        "xp": 500,
        "tier": "silver",
    },
    "cat_all": {
        "name": "Jack of All Trades",
        "desc": "Win at least once in every category",
        "emoji": "🃏",
        "xp": 300,
        "tier": "silver",
    },

    # ── Skill / special ───────────────────────────────────────────────────────
    "no_hints_10": {
        "name": "No Peeking",
        "desc": "Win 10 games without using a single hint",
        "emoji": "🙈",
        "xp": 200,
        "tier": "silver",
    },
    "hint_free_hard": {
        "name": "Pure Genius",
        "desc": "Solve a hard question without any hints",
        "emoji": "🧠",
        "xp": 150,
        "tier": "silver",
    },
    "night_owl": {
        "name": "Night Owl",
        "desc": "Win a game between midnight and 4 AM",
        "emoji": "🦉",
        "xp": 75,
        "tier": "bronze",
    },
    "early_bird": {
        "name": "Early Bird",
        "desc": "Win a game before 7 AM",
        "emoji": "🐦",
        "xp": 75,
        "tier": "bronze",
    },

    # ── Level ─────────────────────────────────────────────────────────────────
    "level_5": {
        "name": "Halfway There",
        "desc": "Reach Level 5",
        "emoji": "⭐",
        "xp": 0,  # XP comes from levelling — don't double-count
        "tier": "silver",
    },
    "level_max": {
        "name": "SIGMOJI Master",
        "desc": "Reach the maximum level",
        "emoji": "💎",
        "xp": 0,
        "tier": "diamond",
    },
}

# ── Level system ──────────────────────────────────────────────────────────────
# (min_xp, label, colour_emoji)
LEVELS = [
    (0,     "Rookie",       "⬜"),
    (150,   "Explorer",     "🟦"),
    (400,   "Decoder",      "🟩"),
    (800,   "Cipher",       "🟨"),
    (1400,  "Mastermind",   "🟧"),
    (2200,  "Wizard",       "🟥"),
    (3400,  "Oracle",       "🟪"),
    (5000,  "Sage",         "🔵"),
    (7200,  "Virtuoso",     "🔴"),
    (10000, "Grandmaster",  "🌟"),
    (14000, "SIGMOJI",      "💎"),
]

MAX_LEVEL = len(LEVELS) - 1  # 10


def get_level(xp: int) -> tuple[int, str, str]:
    """Return (level_index, label, colour_emoji) for a given XP total."""
    level = 0
    for i, (threshold, _, _) in enumerate(LEVELS):
        if xp >= threshold:
            level = i
    idx, label, colour = LEVELS[level]
    return level, label, colour


def xp_progress(xp: int) -> tuple[int, int, int]:
    """Return (current_level_xp, next_level_xp, level_index).
    current_level_xp  = XP earned since the current level threshold.
    next_level_xp     = XP needed to reach the next level (0 if max).
    """
    level, _, _ = get_level(xp)
    current_threshold = LEVELS[level][0]
    if level >= MAX_LEVEL:
        return xp - current_threshold, 0, level
    next_threshold = LEVELS[level + 1][0]
    return xp - current_threshold, next_threshold - current_threshold, level


def xp_bar(xp: int, length: int = 12) -> str:
    """Return a visual XP progress bar string."""
    earned, needed, level = xp_progress(xp)
    if needed == 0:
        return "█" * length + " MAX"
    filled = min(length, int((earned / needed) * length))
    return "█" * filled + "░" * (length - filled)


# Tier display colours (for embed side-bars)
TIER_COLOURS = {
    "bronze":  0xCD7F32,
    "silver":  0xC0C0C0,
    "gold":    0xFFD700,
    "diamond": 0xB9F2FF,
}
