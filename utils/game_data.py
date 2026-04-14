"""
Game data loader and active-session manager for Sigmoji.

Reads questions.csv once at startup; provides per-channel GameSession objects.
"""

import csv
import asyncio
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

QUESTIONS_PATH = Path(__file__).parent.parent / "data" / "questions.csv"


# ── Question loading ──────────────────────────────────────────────────────────

def _load_questions() -> list[dict]:
    questions = []
    with open(QUESTIONS_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            questions.append({
                "id":          int(row["id"]),
                "category":    row["category"].strip(),
                "answer":      row["answer"].strip(),
                "emojis":      row["emojis"].strip(),
                "answer_alts": [a.strip().lower() for a in row["answer_alts"].split("|") if a.strip()],
                "fact":        row["fact"].strip(),
                "difficulty":  row["difficulty"].strip().lower(),
            })
    return questions


class GameData:
    """Singleton-style question registry. Reload is cheap (CSV is tiny)."""

    def __init__(self) -> None:
        self._questions: list[dict] = _load_questions()
        self._by_category: dict[str, list[dict]] = {}
        for q in self._questions:
            self._by_category.setdefault(q["category"], []).append(q)

    def get_categories(self) -> list[str]:
        return sorted(self._by_category.keys())

    def get_question(self, category: str | None = None, exclude_ids: set[int] | None = None) -> dict | None:
        """
        Pick a random question, optionally filtered by category and excluding
        recently-asked question IDs (to avoid immediate repeats).
        """
        pool = (
            self._by_category.get(category, [])
            if category
            else self._questions
        )
        if exclude_ids:
            pool = [q for q in pool if q["id"] not in exclude_ids]
        if not pool:
            # If we've exhausted the exclusion list, reset and pick freely
            pool = self._by_category.get(category, []) if category else self._questions
        return random.choice(pool) if pool else None

    def category_exists(self, category: str) -> bool:
        # Case-insensitive lookup
        lower = category.strip().lower()
        return any(c.lower() == lower for c in self._by_category)

    def normalise_category(self, category: str) -> str | None:
        lower = category.strip().lower()
        for c in self._by_category:
            if c.lower() == lower:
                return c
        return None

    def reload(self) -> None:
        """Hot-reload questions.csv without restarting the bot."""
        self.__init__()


# ── Answer checking ───────────────────────────────────────────────────────────

def check_answer(user_input: str, question: dict) -> bool:
    """Case-insensitive, whitespace-stripped match against answer + alts."""
    normalised = user_input.strip().lower()
    if normalised == question["answer"].strip().lower():
        return True
    return normalised in question["answer_alts"]


# ── Scoring ───────────────────────────────────────────────────────────────────

BASE_POINTS = {"easy": 50, "medium": 100, "hard": 200}
HINT_PENALTY = 20   # Points lost per hint used


def calculate_points(elapsed: float, difficulty: str, hints_used: int) -> int:
    """
    Scoring formula:
      base          → depends on difficulty
      speed_bonus   → up to +100, dropping 2 pts/second (0 after 50s)
      hint_penalty  → -20 pts per hint used
      minimum       → always award at least 10 pts for guessing correctly
    """
    base        = BASE_POINTS.get(difficulty, 100)
    speed_bonus = max(0, 100 - int(elapsed * 2))
    penalty     = hints_used * HINT_PENALTY
    return max(10, base + speed_bonus - penalty)


# ── Hint system ───────────────────────────────────────────────────────────────

def build_hint_mask(answer: str, revealed: set[int]) -> str:
    """
    Build the hint display string.
    Spaces are always shown; letters are shown only if their index is in `revealed`.

    Example: answer="Lion King", revealed={0,5} → "L _ _ _   K _ _ _"
    """
    parts = []
    for i, ch in enumerate(answer):
        if ch == " ":
            parts.append("  ")   # double-space to visually separate words
        elif i in revealed:
            parts.append(ch.upper())
        else:
            parts.append("_")
    return " ".join(parts)


def reveal_random_letter(answer: str, revealed: set[int]) -> set[int]:
    """
    Pick a random unrevealed letter index and add it to `revealed`.
    Returns the updated set. Raises ValueError if all letters are already shown.
    """
    hidden = [i for i, ch in enumerate(answer) if ch != " " and i not in revealed]
    if not hidden:
        raise ValueError("All letters already revealed.")
    chosen = random.choice(hidden)
    return revealed | {chosen}


def max_hints(answer: str) -> int:
    """Maximum hints allowed = half the number of letters (rounded down), min 1."""
    letter_count = sum(1 for ch in answer if ch != " ")
    return max(1, letter_count // 2)


# ── Active game sessions ──────────────────────────────────────────────────────

@dataclass
class GameSession:
    question:      dict
    channel_id:    int
    started_by:    int                    # user_id of the player who ran /play
    start_time:    float = field(default_factory=time.time)
    hints_used:    int   = 0
    revealed:      set[int] = field(default_factory=set)
    timeout_task:  asyncio.Task | None = field(default=None, repr=False)
    is_active:     bool  = True

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    @property
    def hint_mask(self) -> str:
        return build_hint_mask(self.question["answer"], self.revealed)

    @property
    def hints_remaining(self) -> int:
        return max_hints(self.question["answer"]) - self.hints_used


# Per-channel active sessions: { channel_id -> GameSession }
# Accessed from the cog; kept here to avoid circular imports.
ACTIVE_GAMES: dict[int, GameSession] = {}

# Per-channel recently-asked question IDs (to avoid immediate repeats)
RECENT_IDS: dict[int, set[int]] = {}
MAX_RECENT = 20   # How many IDs to remember per channel
