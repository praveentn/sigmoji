"""
LeaderboardCog — rankings and competitive stats.

Commands
────────
/leaderboard  [category]  – Top 10 players globally or by category
/rank         [user]      – Your rank with nearby competition
"""

import discord
from discord.ext import commands

from utils import database as db
from utils.game_data import GameData
from utils.achievements import get_level

COL_LB   = 0x7289DA
COL_RANK = 0xFAA61A

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _pos_emoji(pos: int) -> str:
    return MEDALS.get(pos, f"`#{pos:>2}`")


def _bar(value: int, max_value: int, length: int = 10) -> str:
    if max_value == 0:
        return "░" * length
    filled = max(1, int((value / max_value) * length))
    return "█" * filled + "░" * (length - filled)


async def _require_guild(ctx: discord.ApplicationContext) -> bool:
    if ctx.guild_id is None:
        await ctx.respond(
            "❌ Sigmoji commands can only be used inside a server, not in DMs.",
            ephemeral=True,
        )
        return False
    return True


class LeaderboardCog(commands.Cog):

    def __init__(self) -> None:
        self.game_data = GameData()

    # ── Autocomplete ──────────────────────────────────────────────────────────

    async def _autocomplete_category(self, ctx: discord.AutocompleteContext):
        typed = ctx.value.strip().lower()
        cats  = self.game_data.get_categories()
        return [c for c in cats if typed in c.lower()][:25]

    # ── /leaderboard ──────────────────────────────────────────────────────────

    @discord.slash_command(
        name="leaderboard",
        description="🏆 Top 10 players — globally or by category",
    )
    async def leaderboard(
        self,
        ctx: discord.ApplicationContext,
        category: discord.Option(
            str,
            "Filter by category (leave blank for all-time)",
            autocomplete=_autocomplete_category,
            required=False,
            default=None,
        ),
    ) -> None:
        if not await _require_guild(ctx):
            return

        await ctx.defer()

        resolved_cat = None
        if category:
            resolved_cat = self.game_data.normalise_category(category)
            if resolved_cat is None:
                await ctx.followup.send(
                    f"❌ Unknown category **{category}**. Use `/categories` to see valid ones.",
                    ephemeral=True,
                )
                return

        guild_id = ctx.guild_id
        rows = await db.get_leaderboard(guild_id, category=resolved_cat, limit=10)

        title = (
            f"🏆  Top Players — {resolved_cat}"
            if resolved_cat
            else "🏆  Sigmoji Global Leaderboard"
        )

        if not rows:
            embed = discord.Embed(
                title=title,
                description="No players yet! Be the first — `/play`",
                colour=COL_LB,
            )
            await ctx.followup.send(embed=embed)
            return

        max_wins = rows[0]["total_wins"] if rows else 1

        lines = []
        for i, row in enumerate(rows, 1):
            pos        = _pos_emoji(i)
            wins       = row["total_wins"]
            bar        = _bar(wins, max_wins)
            _, lv_name, _ = get_level(row["xp"])
            name       = discord.utils.escape_markdown(row["username"])
            lines.append(
                f"{pos}  **{name}**  ·  `{bar}`  **{wins}** wins  _{lv_name}_"
            )

        embed = discord.Embed(
            title=title,
            description="\n".join(lines),
            colour=COL_LB,
        )

        own_rank   = await db.get_player_rank(guild_id, ctx.author.id, resolved_cat)
        own_player = await db.get_player(guild_id, ctx.author.id)
        if own_player:
            own_wins = (
                (await db.get_category_stats(guild_id, ctx.author.id)).get(resolved_cat, 0)
                if resolved_cat
                else own_player["total_wins"]
            )
            embed.set_footer(
                text=f"Your rank: #{own_rank} · {own_wins} win{'s' if own_wins != 1 else ''}"
            )
        else:
            embed.set_footer(text="You're not on the board yet — /play to join!")

        await ctx.followup.send(embed=embed)

    # ── /rank ─────────────────────────────────────────────────────────────────

    @discord.slash_command(
        name="rank",
        description="📈 See your rank and the players around you",
    )
    async def rank(
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
        player   = await db.get_player(guild_id, target.id)

        if player is None:
            msg = (
                "You haven't played yet! Start with `/play` to appear on the board."
                if target == ctx.author
                else f"**{target.display_name}** hasn't played yet."
            )
            await ctx.followup.send(msg, ephemeral=True)
            return

        rank     = await db.get_player_rank(guild_id, target.id)
        wins     = player["total_wins"]
        _, lvl_name, lvl_emoji = get_level(player["xp"])

        top_rows = await db.get_leaderboard(guild_id, limit=10)
        max_wins = top_rows[0]["total_wins"] if top_rows else 1

        embed = discord.Embed(
            title=f"📈  {target.display_name}'s Rank",
            colour=COL_RANK,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="Global Rank", value=f"**#{rank}**",          inline=True)
        embed.add_field(name="Total Wins",  value=f"**{wins}**",           inline=True)
        embed.add_field(name="Level",       value=f"{lvl_emoji} **{lvl_name}**", inline=True)

        if top_rows and rank > 1:
            ahead = None
            for r in top_rows:
                if r["user_id"] != target.id and r["total_wins"] > wins:
                    ahead = r
            if ahead:
                gap = ahead["total_wins"] - wins
                embed.add_field(
                    name="🎯 Next Target",
                    value=(
                        f"**{discord.utils.escape_markdown(ahead['username'])}** "
                        f"is {gap} win{'s' if gap != 1 else ''} ahead of you!"
                    ),
                    inline=False,
                )

        embed.set_footer(text="Play more to climb the leaderboard · /play")
        await ctx.followup.send(embed=embed)


def setup(bot: discord.Bot) -> None:
    bot.add_cog(LeaderboardCog())
