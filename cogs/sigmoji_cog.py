"""
SigmojiCog — core game loop for the Sigmoji emoji-guessing game.

Commands
────────
/play   [category]  – Start a round (random category if omitted)
/hint               – Reveal one letter of the current answer
/skip               – Give up and reveal the answer
/categories         – List all available categories

Message listener
────────────────
Listens to every message in channels with an active game. First correct
plain-text answer wins the round.
"""

import asyncio
import time
import logging

import discord
from discord.ext import commands

from utils.game_data import (
    ACTIVE_GAMES, RECENT_IDS, MAX_RECENT,
    GameSession, GameData,
    check_answer, calculate_points,
    reveal_random_letter, max_hints,
)
from utils import database as db
from utils.achievements import ACHIEVEMENTS, get_level, xp_bar, xp_progress, LEVELS, MAX_LEVEL

log = logging.getLogger("sigmoji.game")

# How long (seconds) before the bot reveals the answer automatically
ROUND_TIMEOUT = 60

# ── Embed colour constants ─────────────────────────────────────────────────────
COL_GAME    = 0x7289DA   # Blurple  – game start
COL_WIN     = 0x43B581   # Green    – winner
COL_TIMEOUT = 0xF04747   # Red      – time up / skip
COL_HINT    = 0xFAA61A   # Gold     – hint

# Difficulty display helpers
DIFF_EMOJI  = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}
DIFF_LABEL  = {"easy": "Easy",  "medium": "Medium",  "hard": "Hard"}


# ── Achievement check helper ──────────────────────────────────────────────────

async def _check_achievements(
    user_id: int,
    player: dict,
    elapsed: float,
    hints_used: int,
    category: str,
    difficulty: str,
    channel: discord.TextChannel,
) -> None:
    """Evaluate all win-triggered achievements and announce any new unlocks."""

    earned_achievements = await db.get_achievements(user_id)
    newly_unlocked: list[dict] = []

    async def try_unlock(achievement_id: str) -> None:
        if achievement_id not in earned_achievements:
            newly = await db.unlock_achievement(user_id, achievement_id)
            if newly:
                newly_unlocked.append(ACHIEVEMENTS[achievement_id])

    total_wins    = player["total_wins"]
    streak        = player["current_streak"]
    hint_free     = player["hint_free_wins"]
    hour          = time.localtime().tm_hour

    # Win milestones
    if total_wins >= 1:   await try_unlock("first_win")
    if total_wins >= 5:   await try_unlock("wins_5")
    if total_wins >= 25:  await try_unlock("wins_25")
    if total_wins >= 100: await try_unlock("wins_100")
    if total_wins >= 500: await try_unlock("wins_500")
    if total_wins >= 1000: await try_unlock("wins_1000")

    # Speed
    if elapsed < 10: await try_unlock("speed_10")
    if elapsed < 5:  await try_unlock("speed_5")
    if elapsed < 3:  await try_unlock("speed_3")

    # Streak
    if streak >= 3:   await try_unlock("streak_3")
    if streak >= 7:   await try_unlock("streak_7")
    if streak >= 30:  await try_unlock("streak_30")
    if streak >= 100: await try_unlock("streak_100")

    # Category mastery
    cat_stats = await db.get_category_stats(user_id)
    cat_wins  = cat_stats.get(category, 0)
    if cat_wins >= 10:  await try_unlock("cat_master")
    if cat_wins >= 50:  await try_unlock("cat_expert")

    # All categories
    all_cats = set(GameData().get_categories())
    played_cats = set(cat_stats.keys())
    if all_cats and all_cats.issubset(played_cats):
        await try_unlock("cat_all")

    # Hint-free wins
    if hint_free >= 10:           await try_unlock("no_hints_10")
    if hints_used == 0 and difficulty == "hard":
        await try_unlock("hint_free_hard")

    # Time of day
    if 0 <= hour < 4:  await try_unlock("night_owl")
    if hour < 7:       await try_unlock("early_bird")

    # Level achievements
    level_idx, _, _ = get_level(player["xp"])
    if level_idx >= 5:         await try_unlock("level_5")
    if level_idx >= MAX_LEVEL: await try_unlock("level_max")

    # ── Announce new achievements ─────────────────────────────────────────────
    for ach in newly_unlocked:
        tier_colour = {"bronze": 0xCD7F32, "silver": 0xC0C0C0,
                       "gold": 0xFFD700, "diamond": 0xB9F2FF}.get(ach["tier"], 0x7289DA)
        embed = discord.Embed(
            title=f"{ach['emoji']}  Achievement Unlocked!",
            description=(
                f"**{ach['name']}**\n"
                f"{ach['desc']}\n\n"
                f"{'✨ +' + str(ach['xp']) + ' XP' if ach['xp'] else ''}"
            ),
            colour=tier_colour,
        )
        try:
            await channel.send(embed=embed, delete_after=20)
        except Exception:
            pass


# ── Cog ───────────────────────────────────────────────────────────────────────

class SigmojiCog(commands.Cog):

    def __init__(self, bot: discord.Bot) -> None:
        self.bot       = bot
        self.game_data = GameData()
        self._lock     = asyncio.Lock()   # prevents double-wins on fast answers

    # ── Autocomplete ──────────────────────────────────────────────────────────

    async def _autocomplete_category(self, ctx: discord.AutocompleteContext):
        typed = ctx.value.strip().lower()
        return [
            c for c in self.game_data.get_categories()
            if typed in c.lower()
        ][:25]

    # ── /play ─────────────────────────────────────────────────────────────────

    @discord.slash_command(name="play", description="🎮 Start a Sigmoji emoji guessing game!")
    async def play(
        self,
        ctx: discord.ApplicationContext,
        category: discord.Option(
            str,
            "Pick a category — or leave blank for a random one",
            autocomplete=_autocomplete_category,
            required=False,
            default=None,
        ),
    ) -> None:
        cid = ctx.channel_id

        if cid in ACTIVE_GAMES:
            await ctx.respond(
                "⚠️ A game is already running here! "
                "Type your guess, use `/hint`, or `/skip` to end it.",
                ephemeral=True,
            )
            return

        # Resolve category
        resolved_cat = None
        if category:
            resolved_cat = self.game_data.normalise_category(category)
            if resolved_cat is None:
                cats = "\n".join(f"• {c}" for c in self.game_data.get_categories())
                await ctx.respond(
                    f"❌ Unknown category **{category}**. Available:\n{cats}",
                    ephemeral=True,
                )
                return

        # Pick question (avoid recent repeats in this channel)
        recent = RECENT_IDS.get(cid, set())
        question = self.game_data.get_question(resolved_cat, exclude_ids=recent)
        if question is None:
            await ctx.respond("😬 No questions found. The CSV might be empty!", ephemeral=True)
            return

        # Track recently asked
        recent.add(question["id"])
        if len(recent) > MAX_RECENT:
            recent.pop()
        RECENT_IDS[cid] = recent

        # Create session
        session = GameSession(
            question=question,
            channel_id=cid,
            started_by=ctx.author.id,
        )
        ACTIVE_GAMES[cid] = session

        # Build embed
        diff = question["difficulty"]
        embed = discord.Embed(
            title="🎮  Sigmoji — Decode the Emojis!",
            colour=COL_GAME,
        )
        embed.add_field(
            name="Category",
            value=f"**{question['category']}**",
            inline=True,
        )
        embed.add_field(
            name="Difficulty",
            value=f"{DIFF_EMOJI[diff]} {DIFF_LABEL[diff]}",
            inline=True,
        )
        embed.add_field(
            name="\u200b",
            value="\u200b",
            inline=False,
        )
        embed.add_field(
            name="🔡  The Clue",
            value=f"# {question['emojis']}",
            inline=False,
        )
        embed.set_footer(
            text=(
                f"⏱️ {ROUND_TIMEOUT}s to answer  •  "
                f"💡 /hint ({max_hints(question['answer'])} available)  •  "
                f"⏭️ /skip to give up"
            )
        )

        await ctx.respond(embed=embed)
        log.info(
            "Game started | channel=%d | category=%s | answer=%s",
            cid, question["category"], question["answer"],
        )

        # Arm timeout
        session.timeout_task = asyncio.create_task(
            self._timeout(cid, ctx.channel)
        )

    # ── /hint ─────────────────────────────────────────────────────────────────

    @discord.slash_command(name="hint", description="💡 Reveal one letter of the answer")
    async def hint(self, ctx: discord.ApplicationContext) -> None:
        cid = ctx.channel_id
        session = ACTIVE_GAMES.get(cid)

        if not session or not session.is_active:
            await ctx.respond("No active game here! Start one with `/play`.", ephemeral=True)
            return

        q = session.question
        if session.hints_used >= max_hints(q["answer"]):
            await ctx.respond(
                f"💡 You've used all **{max_hints(q['answer'])}** hints for this round!",
                ephemeral=True,
            )
            return

        try:
            session.revealed = reveal_random_letter(q["answer"], session.revealed)
        except ValueError:
            await ctx.respond("🤔 All letters are already revealed!", ephemeral=True)
            return

        session.hints_used += 1
        remaining = session.hints_remaining

        embed = discord.Embed(
            title="💡  Hint",
            colour=COL_HINT,
        )
        embed.add_field(name="Answer so far", value=f"```{session.hint_mask}```", inline=False)
        embed.set_footer(
            text=f"−{20} pts this round  •  {remaining} hint(s) remaining"
        )
        await ctx.respond(embed=embed)

    # ── /skip ─────────────────────────────────────────────────────────────────

    @discord.slash_command(name="skip", description="⏭️ Give up and reveal the answer")
    async def skip(self, ctx: discord.ApplicationContext) -> None:
        cid = ctx.channel_id

        async with self._lock:
            session = ACTIVE_GAMES.pop(cid, None)

        if not session:
            await ctx.respond("No active game here! Start one with `/play`.", ephemeral=True)
            return

        session.is_active = False
        if session.timeout_task:
            session.timeout_task.cancel()

        embed = self._build_reveal_embed(
            session.question, title="⏭️  Skipped!", colour=COL_TIMEOUT,
            footer=f"Skipped by {ctx.author.display_name}",
        )
        await ctx.respond(embed=embed)

    # ── /categories ───────────────────────────────────────────────────────────

    @discord.slash_command(name="categories", description="📋 List all available game categories")
    async def categories(self, ctx: discord.ApplicationContext) -> None:
        cats = self.game_data.get_categories()
        if not cats:
            await ctx.respond("No categories loaded yet.", ephemeral=True)
            return

        lines = []
        for cat in cats:
            count = len(self.game_data._by_category.get(cat, []))
            lines.append(f"• **{cat}** — {count} questions")

        embed = discord.Embed(
            title="📋  Sigmoji Categories",
            description="\n".join(lines),
            colour=COL_GAME,
        )
        embed.set_footer(text="Use /play <category> to start · Leave blank for a surprise!")
        await ctx.respond(embed=embed)

    # ── Message listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Skip bots and slash-command interactions
        if message.author.bot:
            return
        if message.content.startswith("/"):
            return

        cid = message.channel.id
        session = ACTIVE_GAMES.get(cid)
        if not session or not session.is_active:
            return

        if not check_answer(message.content, session.question):
            # Optionally react with ❌ to confirm the bot noticed (non-spammy)
            try:
                await message.add_reaction("❌")
            except Exception:
                pass
            return

        # ── Correct answer! ───────────────────────────────────────────────────
        async with self._lock:
            # Re-check: another message may have won in the same instant
            if not ACTIVE_GAMES.get(cid) or not ACTIVE_GAMES[cid].is_active:
                return
            won_session = ACTIVE_GAMES.pop(cid)
            won_session.is_active = False

        if won_session.timeout_task:
            won_session.timeout_task.cancel()

        elapsed = won_session.elapsed
        points  = calculate_points(elapsed, won_session.question["difficulty"], won_session.hints_used)

        # Persist win
        updated_player, daily_bonus = await db.record_win(
            user_id    = message.author.id,
            username   = message.author.display_name,
            category   = won_session.question["category"],
            answer     = won_session.question["answer"],
            elapsed    = elapsed,
            points     = points,
            hints_used = won_session.hints_used,
            difficulty = won_session.question["difficulty"],
        )

        # React with ✅
        try:
            await message.add_reaction("✅")
        except Exception:
            pass

        # Build winner embed
        embed = await self._build_winner_embed(
            message.author, won_session, elapsed, points, daily_bonus, updated_player
        )
        await message.channel.send(embed=embed)

        log.info(
            "Round won | user=%s | answer=%s | elapsed=%.1fs | pts=%d",
            message.author, won_session.question["answer"], elapsed, points,
        )

        # Check achievements (fire-and-forget to keep latency low)
        asyncio.create_task(
            _check_achievements(
                user_id    = message.author.id,
                player     = updated_player,
                elapsed    = elapsed,
                hints_used = won_session.hints_used,
                category   = won_session.question["category"],
                difficulty = won_session.question["difficulty"],
                channel    = message.channel,
            )
        )

    # ── Timeout coroutine ─────────────────────────────────────────────────────

    async def _timeout(self, channel_id: int, channel: discord.abc.Messageable) -> None:
        await asyncio.sleep(ROUND_TIMEOUT)

        async with self._lock:
            session = ACTIVE_GAMES.pop(channel_id, None)

        if not session:
            return   # Already won

        session.is_active = False
        embed = self._build_reveal_embed(
            session.question,
            title="⏰  Time's up!",
            colour=COL_TIMEOUT,
            footer="Nobody got it this round. Better luck next time!",
        )
        try:
            await channel.send(embed=embed)
        except Exception as exc:
            log.warning("Could not send timeout message: %s", exc)

    # ── Embed builders ─────────────────────────────────────────────────────────

    @staticmethod
    def _build_reveal_embed(
        question: dict,
        *,
        title: str,
        colour: int,
        footer: str = "",
    ) -> discord.Embed:
        embed = discord.Embed(title=title, colour=colour)
        embed.add_field(
            name="The answer was…",
            value=f"## {question['answer']}",
            inline=False,
        )
        embed.add_field(
            name="📖 Fun Fact",
            value=question["fact"],
            inline=False,
        )
        embed.add_field(name="Clue was", value=question["emojis"], inline=True)
        embed.add_field(name="Category", value=question["category"], inline=True)
        if footer:
            embed.set_footer(text=footer)
        return embed

    @staticmethod
    async def _build_winner_embed(
        author: discord.Member,
        session: "GameSession",
        elapsed: float,
        points: int,
        daily_bonus: int,
        updated_player: dict,
    ) -> discord.Embed:
        q = session.question

        # Speed tier label
        if elapsed < 5:
            speed_label = "⚡ LIGHTNING!"
        elif elapsed < 10:
            speed_label = "🚀 Very Fast"
        elif elapsed < 20:
            speed_label = "💨 Fast"
        elif elapsed < 40:
            speed_label = "👍 Good"
        else:
            speed_label = "🐢 Steady"

        # Level info for this player
        xp_total  = updated_player["xp"]
        lvl_idx, lvl_name, lvl_colour = get_level(xp_total)
        earned, needed, _ = xp_progress(xp_total)
        bar = xp_bar(xp_total)

        streak = updated_player["current_streak"]
        streak_str = f"🔥 {streak}-day streak!" if streak > 1 else ""

        embed = discord.Embed(
            title=f"🎉  {author.display_name} got it!",
            colour=COL_WIN,
        )
        embed.add_field(name="Answer", value=f"## {q['answer']}", inline=False)
        embed.add_field(name="⏱️ Time",    value=f"{elapsed:.1f}s  {speed_label}", inline=True)
        embed.add_field(name="💰 Points", value=f"+{points}" + (f"  (+{daily_bonus} streak bonus)" if daily_bonus else ""), inline=True)
        embed.add_field(name="\u200b",    value="\u200b", inline=True)
        embed.add_field(name="📖 Did you know?", value=q["fact"], inline=False)
        embed.add_field(
            name=f"📊 {lvl_name}  (Lv {lvl_idx})",
            value=(
                f"`{bar}` {earned}/{needed if needed else '—'} XP\n"
                + (streak_str if streak_str else "")
            ),
            inline=False,
        )
        embed.set_thumbnail(url=author.display_avatar.url)
        embed.set_footer(text="Start another round · /play")
        return embed


def setup(bot: discord.Bot) -> None:
    bot.add_cog(SigmojiCog(bot))
