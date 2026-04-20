"""
ProfileCog — player profiles, streaks, and achievement showcase.

Commands
────────
/profile   [user]  – View a rich stat card
/streak            – Quick streak status + daily bonus info
/achievements [user] – Full achievement showcase
"""

import discord
from discord.ext import commands

from utils import database as db
from utils.achievements import (
    ACHIEVEMENTS, LEVELS, MAX_LEVEL,
    get_level, xp_bar, xp_progress,
    TIER_COLOURS,
)

COL_PROFILE  = 0x7289DA
COL_STREAK   = 0xFF6B35
COL_ACH      = 0xFFD700


def _win_rate(wins: int, games: int) -> str:
    if games == 0:
        return "—"
    return f"{wins / games * 100:.1f}%"


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"


async def _require_guild(ctx: discord.ApplicationContext) -> bool:
    if ctx.guild_id is None:
        await ctx.respond(
            "❌ Sigmoji commands can only be used inside a server, not in DMs.",
            ephemeral=True,
        )
        return False
    return True


class ProfileCog(commands.Cog):

    # ── /profile ──────────────────────────────────────────────────────────────

    @discord.slash_command(name="profile", description="📊 View a player's Sigmoji profile")
    async def profile(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(
            discord.Member,
            "Player to look up (defaults to you)",
            required=False,
            default=None,
        ),
    ) -> None:
        if not await _require_guild(ctx):
            return

        await ctx.defer()

        guild_id = ctx.guild_id
        target   = user or ctx.author
        player   = await db.get_player(guild_id, target.id)

        if player is None:
            msg = (
                "You haven't played yet! Start with `/play`."
                if target == ctx.author
                else f"**{target.display_name}** hasn't played yet."
            )
            await ctx.followup.send(msg, ephemeral=True)
            return

        xp        = player["xp"]
        lvl_idx, lvl_name, lvl_colour_emoji = get_level(xp)
        earned, needed, _ = xp_progress(xp)
        bar       = xp_bar(xp)
        next_lvl  = LEVELS[lvl_idx + 1][1] if lvl_idx < MAX_LEVEL else "MAX"

        cat_stats = await db.get_category_stats(guild_id, target.id)
        top_cats  = sorted(cat_stats.items(), key=lambda x: x[1], reverse=True)[:3]
        top_cat_str = "\n".join(f"• {c}: **{w}** wins" for c, w in top_cats) or "—"

        ach_ids   = await db.get_achievements(guild_id, target.id)
        badge_row = " ".join(
            ACHIEVEMENTS[a]["emoji"] for a in ach_ids if a in ACHIEVEMENTS
        )[:1024] or "None yet"

        rank = await db.get_player_rank(guild_id, target.id)

        streak        = player["current_streak"]
        best_streak   = player["best_streak"]
        total_wins    = player["total_wins"]
        total_games   = player["total_games"]

        embed = discord.Embed(
            title=f"{'🏆 ' if lvl_idx >= 8 else ''}{target.display_name}'s Profile",
            colour=COL_PROFILE,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        xp_desc = (
            f"`{bar}`\n"
            f"**{lvl_colour_emoji} Level {lvl_idx}  —  {lvl_name}**\n"
            f"{earned} / {needed if needed else '—'} XP"
            + (f"  →  next: *{next_lvl}*" if needed else "  🎉 **MAX LEVEL**")
        )
        embed.add_field(name="⭐ Level", value=xp_desc, inline=False)

        embed.add_field(
            name="📊 Stats",
            value=(
                f"🏅 Rank: **{_ordinal(rank)}**\n"
                f"🎯 Wins: **{total_wins}**  |  Games: **{total_games}**\n"
                f"📈 Win Rate: **{_win_rate(total_wins, total_games)}**"
            ),
            inline=True,
        )

        embed.add_field(
            name="🔥 Streak",
            value=(
                f"Current: **{streak}** day{'s' if streak != 1 else ''}\n"
                f"Best: **{best_streak}** day{'s' if best_streak != 1 else ''}"
            ),
            inline=True,
        )

        embed.add_field(name="\u200b", value="\u200b", inline=False)

        embed.add_field(name="🎮 Top Categories", value=top_cat_str, inline=True)

        embed.add_field(
            name=f"🏆 Badges  ({len(ach_ids)}/{len(ACHIEVEMENTS)})",
            value=badge_row,
            inline=True,
        )

        embed.set_footer(text="Use /achievements for full details  •  /play to earn more")
        await ctx.followup.send(embed=embed)

    # ── /streak ───────────────────────────────────────────────────────────────

    @discord.slash_command(name="streak", description="🔥 Check your daily streak status")
    async def streak(self, ctx: discord.ApplicationContext) -> None:
        if not await _require_guild(ctx):
            return

        player = await db.get_player(ctx.guild_id, ctx.author.id)

        if player is None:
            await ctx.respond(
                "You haven't played yet! Use `/play` to start your streak.",
                ephemeral=True,
            )
            return

        streak      = player["current_streak"]
        best        = player["best_streak"]
        last_played = player.get("last_played") or "Never"

        bonus_pts = min(streak + 1, 10) * 5
        next_bonus = (
            f"+{bonus_pts} bonus points on your next win today!"
            if streak > 0
            else "Win today to start your streak!"
        )

        milestones = {3: "🔥 On Fire", 7: "🔥🔥 Committed", 30: "🌋 Inferno", 100: "♾️ Eternal Flame"}
        next_milestone = next(
            ((days, name) for days, name in sorted(milestones.items()) if days > streak),
            None
        )

        embed = discord.Embed(
            title=f"🔥  {ctx.author.display_name}'s Streak",
            colour=COL_STREAK,
        )
        embed.add_field(
            name="Current Streak",
            value=f"**{streak}** day{'s' if streak != 1 else ''}",
            inline=True,
        )
        embed.add_field(
            name="Best Streak",
            value=f"**{best}** day{'s' if best != 1 else ''}",
            inline=True,
        )
        embed.add_field(name="Last Played", value=last_played, inline=True)

        embed.add_field(name="💰 Daily Bonus", value=next_bonus, inline=False)

        if next_milestone:
            days_left, name = next_milestone
            gap = days_left - streak
            embed.add_field(
                name="🎯 Next Milestone",
                value=f"**{name}** — {gap} more day{'s' if gap != 1 else ''} to go!",
                inline=False,
            )
        else:
            embed.add_field(
                name="🏆 Milestones",
                value="You've unlocked ALL streak milestones! Absolute legend.",
                inline=False,
            )

        embed.set_footer(text="Play every day to keep your streak alive!")
        await ctx.respond(embed=embed, ephemeral=True)

    # ── /achievements ─────────────────────────────────────────────────────────

    @discord.slash_command(name="achievements", description="🏅 View your achievement showcase")
    async def achievements(
        self,
        ctx: discord.ApplicationContext,
        user: discord.Option(
            discord.Member,
            "Player to look up (defaults to you)",
            required=False,
            default=None,
        ),
    ) -> None:
        if not await _require_guild(ctx):
            return

        await ctx.defer(ephemeral=True)

        guild_id = ctx.guild_id
        target   = user or ctx.author
        ach_ids  = await db.get_achievements(guild_id, target.id)
        unlocked = set(ach_ids)

        tiers = ["diamond", "gold", "silver", "bronze"]
        tier_labels = {
            "diamond": "💎 Diamond",
            "gold":    "🥇 Gold",
            "silver":  "🥈 Silver",
            "bronze":  "🥉 Bronze",
        }

        embed = discord.Embed(
            title=f"🏅  {target.display_name}'s Achievements  ({len(unlocked)}/{len(ACHIEVEMENTS)})",
            colour=COL_ACH,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        for tier in tiers:
            lines = []
            for ach_id, ach in ACHIEVEMENTS.items():
                if ach["tier"] != tier:
                    continue
                if ach_id in unlocked:
                    lines.append(f"{ach['emoji']} **{ach['name']}** — {ach['desc']}")
                else:
                    lines.append(f"🔒 ~~{ach['name']}~~ — {ach['desc']}")

            if lines:
                embed.add_field(
                    name=tier_labels[tier],
                    value="\n".join(lines),
                    inline=False,
                )

        embed.set_footer(text="Keep playing to unlock more!")
        await ctx.followup.send(embed=embed)


def setup(bot: discord.Bot) -> None:
    bot.add_cog(ProfileCog())
