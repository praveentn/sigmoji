"""
ReminderCog — automated daily engagement reminders for Sigmoji.

Admins configure a target channel and timezone per server via /remind.
The bot sends ONE reminder per guild per day at 08:00 AM in that guild's
configured local time.  If a guild has not configured reminders, nothing
is sent — there is no fallback to default channels.

Setup commands (require Manage Server permission):
  /remind channel #channel        — set target channel (enables reminders)
  /remind timezone America/New_York — set IANA timezone
  /remind status                  — show current config
  /remind test                    — fire a test reminder immediately
  /remind off                     — disable reminders
"""

import logging
import random
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import commands, tasks

from utils import database as db
from utils.categoryhistory import get_today_history

log = logging.getLogger("sigmoji.reminder")

# ── Emoji insights ────────────────────────────────────────────────────────────
# Each tuple: (emoji, one-sentence covering visual, conceptual & abstract uses)

EMOJI_INSIGHTS: list[tuple[str, str]] = [
    ("🌻", "Sunflower — sunshine, loyalty, adoration, longevity; it always turns toward the light, symbolizing optimism and unwavering devotion."),
    ("🦋", "Butterfly — transformation, beauty, fragility, the soul; from caterpillar to wings, it embodies metamorphosis and rebirth."),
    ("🔥", "Fire — passion, destruction, warmth, creativity, danger; it can forge steel or burn forests, representing both power and chaos."),
    ("🌊", "Wave — the ocean, emotion, change, momentum, overwhelming force; it ebbs and flows like life's ups and downs."),
    ("⚡", "Lightning bolt — speed, electricity, sudden insight, divine power; Zeus's weapon and the symbol of a eureka moment."),
    ("🎭", "Theatre masks — drama, duality, comedy and tragedy, performance; they remind us every person wears many faces."),
    ("🧩", "Puzzle piece — problem-solving, fitting in, autism awareness, complexity; every challenge is just a puzzle waiting to be solved."),
    ("🪞", "Mirror — reflection, vanity, self-awareness, truth, illusion; it shows what is but also what we choose to see."),
    ("🗝️", "Key — access, secrets, solutions, authority, mystery; every locked door in life has a key waiting to be found."),
    ("🌙", "Crescent moon — nighttime, mystery, Islam, feminine energy, dreams; it watches over the world while half the planet sleeps."),
    ("🎯", "Bullseye — precision, goals, focus, accuracy, achievement; hitting the target requires patience, aim, and release."),
    ("🧭", "Compass — navigation, direction, morality, exploration, finding your way; it always points north even when you're lost."),
    ("🪴", "Potted plant — growth, nurturing, patience, indoor nature, self-care; small daily attention yields remarkable results."),
    ("💎", "Gem — value, rarity, luxury, clarity, resilience; diamonds form under extreme pressure, much like character."),
    ("🎪", "Circus tent — spectacle, wonder, childhood, entertainment, organized chaos; life is a circus and we're all performers."),
    ("🦉", "Owl — wisdom, night vision, mystery, knowledge, silence; the keeper of secrets who sees what others miss."),
    ("🌈", "Rainbow — hope, diversity, promise, beauty after rain, LGBTQ+ pride; nature's reminder that storms don't last forever."),
    ("⏳", "Hourglass — time passing, patience, urgency, mortality, the precious now; every grain of sand is a moment you won't get back."),
    ("🎲", "Dice — chance, risk, gambling, probability, fate; sometimes life asks you to roll and trust the outcome."),
    ("🔮", "Crystal ball — prediction, mystery, fortune-telling, the future, intuition; it represents our eternal desire to see what comes next."),
    ("🧊", "Ice cube — cold, preservation, chill, clarity, fragility; solid yet destined to melt, a metaphor for impermanence."),
    ("🪶", "Feather — lightness, flight, writing, freedom, indigenous culture; it falls slowly but can tip the scales of justice."),
    ("🎵", "Musical notes — melody, rhythm, emotion, harmony, universal language; music is the shorthand of feeling."),
    ("🏔️", "Mountain — challenge, achievement, majesty, permanence, perspective; the summit rewards those who endure the climb."),
    ("🌀", "Cyclone — spin, confusion, hypnosis, storms, spiraling energy; the eye of the storm is always calm."),
    ("🦊", "Fox — cleverness, cunning, beauty, adaptability, trickery; nature's reminder that intelligence outwits brute force."),
    ("🍀", "Four-leaf clover — luck, Ireland, rarity, hope, fortune; one in 10,000 clovers has four leaves — you might just be that one."),
    ("🎨", "Artist palette — creativity, color, expression, imagination, art; every masterpiece starts with a single brushstroke."),
    ("🌍", "Globe — the world, unity, travel, environment, interconnectedness; we all share one pale blue dot."),
    ("🦁", "Lion — courage, royalty, strength, pride, leadership; the king of the jungle who fears nothing."),
    ("🕊️", "Dove — peace, purity, hope, love, the Holy Spirit; its olive branch signals the end of the flood."),
    ("🧠", "Brain — intelligence, thinking, neuroscience, ideas, consciousness; the 3-pound universe inside your head."),
    ("🌋", "Volcano — eruption, raw power, creation, destruction, transformation; it builds new land while destroying the old."),
    ("🎀", "Ribbon — gift, awareness campaigns, celebration, femininity, decoration; a bow tied around the present moment."),
    ("⚖️", "Balance scale — justice, fairness, law, equilibrium, choices; every decision weighs one thing against another."),
    ("🦅", "Eagle — freedom, vision, America, soaring, power; it sees prey from two miles away — focus personified."),
    ("🔬", "Microscope — science, discovery, detail, research, the invisible world; it reveals universes too small for the naked eye."),
    ("🏰", "Castle — royalty, defense, fairy tales, history, ambition; every castle began as someone's audacious dream."),
    ("🌸", "Cherry blossom — Japan, beauty, transience, spring, renewal; its brief bloom reminds us to savor every moment."),
    ("🎹", "Piano — music, elegance, practice, harmony, emotion; 88 keys and infinite possibilities."),
    ("🐙", "Octopus — intelligence, adaptability, ocean mystery, camouflage, multi-tasking; three hearts and the ability to solve puzzles."),
    ("🪨", "Rock — stability, foundation, endurance, geology, stubbornness; unmoved by wind and rain, a symbol of resilience."),
    ("🎈", "Balloon — celebration, childhood, lightness, fragility, letting go; one pin away from a pop, yet it soars."),
    ("🦚", "Peacock — beauty, pride, display, confidence, vanity; sometimes showing your true colors is the bravest thing."),
    ("🧲", "Magnet — attraction, physics, polarity, pull, connection; opposites attract and some bonds are just magnetic."),
    ("🍂", "Fallen leaf — autumn, change, letting go, impermanence, maturity; trees shed to survive, and so must we."),
    ("🕰️", "Mantelpiece clock — tradition, time, nostalgia, patience, the steady tick of life moving forward."),
    ("🐢", "Turtle — patience, longevity, protection, steady progress, wisdom; slow and steady really does win the race."),
    ("🎻", "Violin — elegance, emotion, classical music, passion, precision; its strings vibrate with the full spectrum of human feeling."),
    ("🌵", "Cactus — resilience, survival, the desert, minimalism, boundaries; it thrives where nothing else can, armed with thorns."),
    ("🦈", "Shark — power, fear, ancient survival, apex predator, focus; 450 million years of evolution made it perfect."),
    ("🔭", "Telescope — exploration, astronomy, curiosity, the cosmos, vision; it stretches our sight across billions of light-years."),
    ("🏺", "Amphora — ancient history, pottery, storage, art, archaeology; a vessel that carried civilizations' stories across millennia."),
    ("🧬", "DNA helix — genetics, life's blueprint, identity, evolution, biotechnology; the code written in every living cell."),
    ("🪁", "Kite — wind, play, childhood, freedom, ingenuity; it only flies because it's tethered — sometimes limits lift us."),
    ("🐝", "Bee — teamwork, pollination, nature's worker, sweetness, industry; if bees vanish, the ecosystem collapses."),
    ("🎩", "Top hat — elegance, magic, formality, showmanship, old-world class; tip your hat to the classics."),
    ("🌕", "Full moon — completeness, tides, lunacy, romance, werewolves; it pulls oceans and imaginations alike."),
    ("🧿", "Nazar — protection from evil eye, Turkish culture, superstition, warding off negativity, ancient belief."),
    ("🎡", "Ferris wheel — perspective, amusement, cycles, ups and downs, wonder; life looks different from the top."),
    ("🗿", "Moai — mystery, Easter Island, ancestors, monumental effort, silent guardians watching across centuries."),
    ("🍄", "Mushroom — nature, growth in darkness, psychedelics, decomposition, hidden networks; forests communicate through fungal webs."),
    ("⛵", "Sailboat — adventure, wind-power, freedom, navigation, journey; you can't control the wind, but you can adjust the sails."),
    ("🎓", "Graduation cap — education, achievement, commencement, knowledge, new beginnings; the tassel is worth the hassle."),
    ("🦀", "Crab — the ocean, tenacity, sideways thinking, protection, zodiac Cancer; it moves differently but always gets there."),
    ("🔑", "Old key — unlocking potential, discovery, trust, access, vintage charm; every answer is a key to the next question."),
    ("🌺", "Hibiscus — tropical beauty, Hawaii, femininity, delicate strength, warm welcome; it blooms boldly in the heat."),
    ("🐘", "Elephant — memory, wisdom, family bonds, strength, conservation; they mourn their dead and never forget."),
    ("🪐", "Ringed planet — Saturn, space, cosmic scale, rings of mystery, the sublime vastness of the universe."),
    ("🎤", "Microphone — voice, performance, karaoke, amplification, being heard; everyone deserves a moment at the mic."),
    ("🦩", "Flamingo — balance (they sleep on one leg), pink vibrancy, tropics, grace, standing out in a crowd."),
    ("🧪", "Test tube — experiment, chemistry, science, discovery, trial and error; breakthroughs begin with 'what if?'"),
    ("🗺️", "World map — exploration, geography, planning, adventure, perspective; the world is both vast and small."),
    ("🎋", "Tanabata tree — Japanese festival, wishes, stars, love, tradition; write your wish and hang it on the bamboo."),
    ("🐉", "Dragon — mythology, power, Chinese culture, fire, the untamed imagination; it exists in every culture's legends."),
    ("🎸", "Guitar — rock & roll, campfires, emotion, self-expression, rebellion; six strings and a dream."),
    ("🦜", "Parrot — mimicry, tropical color, communication, intelligence, companionship; it speaks your words back to you."),
    ("🏹", "Bow and arrow — archery, precision, Sagittarius, hunting, focus; to hit the mark you must first draw back."),
    ("🌪️", "Tornado — raw nature, destruction, unpredictability, force, Dorothy's Kansas; chaos that reshapes landscapes."),
    ("🍯", "Honey pot — sweetness, nature's preservative, hard work, bees, Winnie the Pooh; the reward of collective effort."),
    ("🧘", "Meditation pose — mindfulness, calm, yoga, inner peace, spiritual practice; stillness is the loudest statement."),
    ("🎠", "Carousel — nostalgia, childhood, going in circles, amusement, gentle motion; sometimes the journey matters more than the destination."),
    ("🦝", "Raccoon — resourcefulness, mischief, nocturnal life, masked identity, urban wildlife; the bandit who adapts to any environment."),
    ("🔔", "Bell — alarm, celebration, school, mindfulness, clarity; a single ring cuts through any noise."),
    ("🌾", "Sheaf of rice — harvest, agriculture, sustenance, gratitude, hard work; civilization began when we learned to farm."),
    ("🐋", "Whale — the deep ocean, migration, song, conservation, gentle giants; the largest heartbeat on the planet."),
    ("🏮", "Red lantern — Chinese New Year, festival, warmth, tradition, guiding light in the dark."),
    ("🎬", "Clapperboard — cinema, action, storytelling, filmmaking, 'take two'; every great story has a first take."),
    ("🦠", "Microbe — invisible world, biology, pandemics, evolution, the tiny things that shape our lives."),
    ("🧶", "Yarn — knitting, patience, warmth, craft, connection; one thread becomes a blanket stitch by stitch."),
    ("🗻", "Mount Fuji — Japan's icon, symmetry in nature, pilgrimage, volcanic beauty, quiet majesty."),
    ("🐺", "Wolf — loyalty, pack mentality, wildness, the moon, survival instinct; strength through unity."),
    ("🎰", "Slot machine — luck, gambling, Vegas, risk vs. reward, the allure of chance."),
    ("🧳", "Suitcase — travel, adventure, new beginnings, packing your life, the excitement of departure."),
    ("🌏", "Globe (Asia-Australia) — Eastern hemisphere, diversity, interconnected world, oceanic expanse, perspective shift."),
    ("🦕", "Sauropod — dinosaurs, deep time, extinction, awe, the reminder that even giants don't last forever."),
    ("🎧", "Headphones — music, immersion, solitude, podcasts, your personal soundtrack to life."),
    ("🏝️", "Desert island — escape, paradise, isolation, Robinson Crusoe, the fantasy of starting fresh."),
    ("🔗", "Chain link — connection, blockchain, strength in unity, bondage, unbreakable bonds."),
]

# ── Streak status labels ──────────────────────────────────────────────────────

_STREAK_LABELS = [
    (100, "🏆 LEGENDARY"),
    (30,  "💎 DIAMOND"),
    (14,  "🔥🔥 BLAZING"),
    (7,   "🔥 ON FIRE"),
    (3,   "✨ BUILDING"),
    (1,   "🌱 STARTING"),
]

def _streak_label(streak: int) -> str:
    for threshold, label in _STREAK_LABELS:
        if streak >= threshold:
            return label
    return "💤 DORMANT"


# ── Helpers ───────────────────────────────────────────────────────────────────

# Discord content field limit; leave buffer for safety
_MAX_CONTENT = 1900

def _mention_chunks(players: list[dict], per_line: bool = False) -> list[str]:
    """
    Split a player list into content-safe chunks of mention strings.

    per_line=False → space-separated mentions (dormant section)
    per_line=True  → one mention + streak info per line (at-risk section)
    Each returned string fits within _MAX_CONTENT characters.
    """
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for p in players:
        if per_line:
            streak = p.get("current_streak", 0)
            label = _streak_label(streak)
            part = f"<@{p['user_id']}> — {label} · **{streak}** day{'s' if streak != 1 else ''}"
            sep = "\n"
        else:
            part = f"<@{p['user_id']}>"
            sep = "  "

        add_len = len(part) + (len(sep) if current_parts else 0)
        if current_parts and current_len + add_len > _MAX_CONTENT:
            chunks.append(sep.join(current_parts))
            current_parts = [part]
            current_len = len(part)
        else:
            current_parts.append(part)
            current_len += add_len

    if current_parts:
        sep = "\n" if per_line else "  "
        chunks.append(sep.join(current_parts))

    return chunks


GREETING_HEADERS = [
    "Rise and shine, Sigmoji squad! 🌅",
    "Good morning, emoji detectives! 🕵️",
    "Wake up, legends — it's game time! ☀️",
    "Another day, another chance to be the best! 🏆",
    "The emojis are calling — will you answer? 📞",
    "Top of the morning, puzzle masters! 🧩",
    "New day unlocked — let's get those points! 🔓",
    "Your daily dose of emoji brilliance awaits! 💡",
]

CALL_TO_ACTION = [
    "Type `/play` and prove you've still got it!",
    "Fire up `/play` — your streak depends on it!",
    "Hit `/play` and show the leaderboard who's boss!",
    "Jump into `/play` before your streak vanishes!",
    "Your rivals are already playing — `/play` now!",
    "One round of `/play` keeps the streak alive!",
]


def _build_main_embed(emoji_pick: tuple[str, str], history_fact: str, today: date) -> discord.Embed:
    emoji_char, emoji_desc = emoji_pick
    header = random.choice(GREETING_HEADERS)

    day_suffix = {1: "st", 2: "nd", 3: "rd"}.get(today.day % 10, "th")
    if 11 <= today.day <= 13:
        day_suffix = "th"
    date_display = today.strftime(f"%B {today.day}{day_suffix}, %Y")

    embed = discord.Embed(
        title=f"{emoji_char}  {header}",
        description=(
            f"**📅  {date_display}**\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"### 💡 Emoji of the Day: {emoji_char}\n"
            f"> {emoji_desc}\n\n"
            f"### 📜 On This Day in History\n"
            f"> {history_fact}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        colour=0x7289DA,
    )
    embed.set_footer(text="Sigmoji • Daily Reminder • One game a day keeps the boredom away!")
    return embed


def _build_cta_embed() -> discord.Embed:
    cta = random.choice(CALL_TO_ACTION)
    return discord.Embed(
        description=(
            f"### 🎮  {cta}\n\n"
            f"Keep your streak alive, climb the leaderboard,\n"
            f"and unlock achievements — all in under a minute!"
        ),
        colour=0x43B581,
    )


# ── Cog ───────────────────────────────────────────────────────────────────────

class ReminderCog(commands.Cog):
    """Sends one daily reminder per guild at 08:00 AM in their configured timezone."""

    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot
        self._last_sent: dict[int, str] = {}  # guild_id → date string

    def cog_unload(self) -> None:
        self._daily_tick.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self._daily_tick.is_running():
            self._daily_tick.start()
            log.info("Daily reminder task started.")

    # ── /remind command group ─────────────────────────────────────────────────

    remind = discord.SlashCommandGroup(
        "remind",
        "Configure automated daily reminders for this server",
        guild_only=True,
        default_member_permissions=discord.Permissions(manage_guild=True),
    )

    @remind.command(name="channel", description="Set the channel where daily reminders are sent")
    async def remind_channel(
        self,
        ctx: discord.ApplicationContext,
        channel: discord.Option(discord.TextChannel, "Channel to receive daily reminders"),
    ) -> None:
        if not channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.respond(
                f"❌ I don't have permission to send messages in {channel.mention}.",
                ephemeral=True,
            )
            return

        config = await db.get_reminder_config(ctx.guild_id)
        tz = config["timezone"] if config else "UTC"
        await db.save_reminder_config(ctx.guild_id, channel.id, tz, True)

        await ctx.respond(
            f"✅ Daily reminders will be sent to {channel.mention} at **08:00 AM** (`{tz}`).\n"
            f"Use `/remind timezone` to change the timezone, or `/remind test` to preview.",
            ephemeral=True,
        )

    @remind.command(name="timezone", description="Set the timezone for the 08:00 AM reminder (IANA name)")
    async def remind_timezone(
        self,
        ctx: discord.ApplicationContext,
        timezone: discord.Option(str, "IANA timezone, e.g. America/New_York, Europe/London, Asia/Kolkata"),
    ) -> None:
        try:
            tz = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, KeyError):
            await ctx.respond(
                f"❌ `{timezone}` is not a recognised IANA timezone.\n"
                f"Examples: `America/New_York` · `Europe/London` · `Asia/Kolkata` · `Asia/Tokyo`",
                ephemeral=True,
            )
            return

        config = await db.get_reminder_config(ctx.guild_id)
        if config is None:
            await ctx.respond(
                "❌ No reminder channel set yet. Run `/remind channel` first.",
                ephemeral=True,
            )
            return

        now_local = datetime.now(tz)
        time_str = now_local.strftime("%I:%M %p %Z")

        await db.save_reminder_config(ctx.guild_id, config["channel_id"], timezone, config["enabled"])

        await ctx.respond(
            f"✅ Timezone set to `{timezone}`.\n"
            f"Current local time: **{time_str}**\n"
            f"Reminders will fire at **08:00 AM** in this timezone.",
            ephemeral=True,
        )

    @remind.command(name="status", description="Show the current reminder configuration")
    async def remind_status(self, ctx: discord.ApplicationContext) -> None:
        config = await db.get_reminder_config(ctx.guild_id)
        if config is None:
            await ctx.respond(
                "ℹ️ Reminders are **not configured** for this server.\n"
                "Use `/remind channel #channel` to get started.",
                ephemeral=True,
            )
            return

        channel = ctx.guild.get_channel(config["channel_id"])
        channel_str = channel.mention if channel else f"⚠️ deleted channel (ID {config['channel_id']})"
        status_str = "✅ Enabled" if config["enabled"] else "❌ Disabled"

        try:
            tz = ZoneInfo(config["timezone"])
            now_local = datetime.now(tz)
            time_str = now_local.strftime("%I:%M %p %Z")
        except Exception:
            time_str = "unknown"

        embed = discord.Embed(title="📋 Reminder Configuration", colour=0x7289DA)
        embed.add_field(name="Status", value=status_str, inline=True)
        embed.add_field(name="Channel", value=channel_str, inline=True)
        embed.add_field(name="Timezone", value=f"`{config['timezone']}`", inline=True)
        embed.add_field(name="Current Local Time", value=time_str, inline=True)
        embed.add_field(name="Fires Daily At", value="08:00 AM", inline=True)
        await ctx.respond(embed=embed, ephemeral=True)

    @remind.command(name="test", description="Send a test reminder right now to the configured channel")
    async def remind_test(self, ctx: discord.ApplicationContext) -> None:
        config = await db.get_reminder_config(ctx.guild_id)
        if config is None:
            await ctx.respond(
                "❌ No reminder channel configured. Use `/remind channel` first.",
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        today = date.today()
        emoji_pick = random.choice(EMOJI_INSIGHTS)
        history_fact = get_today_history(today)

        # force=True so all registered players are pinged regardless of whether
        # they already played today (makes the test actually demonstrable)
        await self._send_guild_reminder(
            ctx.guild, config["channel_id"], today, emoji_pick, history_fact, force=True
        )

        channel = ctx.guild.get_channel(config["channel_id"])
        dest = channel.mention if channel else "the configured channel"
        await ctx.followup.send(f"✅ Test reminder sent to {dest}.", ephemeral=True)

    @remind.command(name="off", description="Disable daily reminders for this server")
    async def remind_off(self, ctx: discord.ApplicationContext) -> None:
        config = await db.get_reminder_config(ctx.guild_id)
        if config is None:
            await ctx.respond("ℹ️ Reminders were never configured for this server.", ephemeral=True)
            return

        await db.save_reminder_config(ctx.guild_id, config["channel_id"], config["timezone"], False)
        await ctx.respond(
            "🔕 Daily reminders have been **disabled**.\n"
            "Use `/remind channel` to re-enable them.",
            ephemeral=True,
        )

    # ── Task loop ─────────────────────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def _daily_tick(self) -> None:
        try:
            configs = await db.get_all_active_reminder_configs()
        except Exception as exc:
            log.error("Failed to load reminder configs: %s", exc)
            return

        # Amortise emoji/history lookups when multiple guilds share the same date
        date_cache: dict[str, tuple] = {}

        for config in configs:
            guild_id = config["guild_id"]
            try:
                tz = ZoneInfo(config["timezone"])
            except (ZoneInfoNotFoundError, KeyError):
                log.warning("Invalid timezone %r for guild %d — skipping.", config["timezone"], guild_id)
                continue

            now_local = datetime.now(tz)
            if now_local.hour != 8 or now_local.minute > 0:
                continue

            today_str = str(now_local.date())
            if self._last_sent.get(guild_id) == today_str:
                continue

            if today_str not in date_cache:
                date_cache[today_str] = (random.choice(EMOJI_INSIGHTS), get_today_history(now_local.date()))

            emoji_pick, history_fact = date_cache[today_str]
            self._last_sent[guild_id] = today_str

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                log.debug("Guild %d not in bot cache — skipping.", guild_id)
                continue

            try:
                await self._send_guild_reminder(
                    guild, config["channel_id"], now_local.date(), emoji_pick, history_fact
                )
            except Exception as exc:
                log.error(
                    "Reminder failed for guild %s (%d): %s", guild.name, guild_id, exc, exc_info=True
                )

    @_daily_tick.before_loop
    async def _before_tick(self) -> None:
        await self.bot.wait_until_ready()

    # ── Per-guild send ────────────────────────────────────────────────────────

    async def _send_guild_reminder(
        self,
        guild: discord.Guild,
        channel_id: int,
        today: date,
        emoji_pick: tuple[str, str],
        history_fact: str,
        *,
        force: bool = False,
    ) -> None:
        """
        Send the daily reminder to the configured channel.

        force=True  → ping every registered player regardless of today's play
                       status (used by /remind test so admins can verify pings)
        force=False → only ping players who haven't played yet today (production)
        """
        players = await db.get_all_guild_players(guild.id)
        if not players:
            log.debug("No players in %s — skipping reminder.", guild.name)
            return

        channel = guild.get_channel(channel_id)
        if channel is None:
            log.warning("Configured channel %d not found in %s — skipping.", channel_id, guild.name)
            return
        if not channel.permissions_for(guild.me).send_messages:
            log.warning("No send permission in #%s (%s) — skipping.", channel.name, guild.name)
            return

        # Categorise players
        yesterday = str(today - timedelta(days=1))
        today_str = str(today)
        at_risk: list[dict] = []
        dormant: list[dict] = []

        for p in players:
            lp = p.get("last_played")
            if lp == today_str and not force:
                pass  # already played today — skip in scheduled reminders
            elif lp == yesterday and p.get("current_streak", 0) > 0:
                at_risk.append(p)
            else:
                dormant.append(p)

        at_risk.sort(key=lambda p: p.get("current_streak", 0), reverse=True)

        # 1 — Main header embed (no mentions)
        await channel.send(embeds=[_build_main_embed(emoji_pick, history_fact, today)])

        # 2 — At-risk section: header embed + paginated content pings
        if at_risk:
            await channel.send(embeds=[discord.Embed(
                description=(
                    "### 🚨 Streak at Risk!\n"
                    "Play today or your streak resets to zero!"
                ),
                colour=0xF04747,
            )])
            for chunk in _mention_chunks(at_risk, per_line=True):
                await channel.send(content=chunk)

        # 3 — Dormant / general section: header embed + paginated content pings
        if dormant:
            await channel.send(embeds=[discord.Embed(
                description=(
                    "### 👋 We Miss You!\n"
                    "It's been a while — jump back in!"
                ),
                colour=0xFAA61A,
            )])
            for chunk in _mention_chunks(dormant, per_line=False):
                await channel.send(content=chunk)

        # 4 — Fallback when nothing to ping (shouldn't happen in production
        #     at 8 AM, but useful to surface during manual tests)
        if not at_risk and not dormant:
            await channel.send(embeds=[discord.Embed(
                description=(
                    "### ✅ Everyone's up to date!\n"
                    "All registered players have already played today. "
                    "Check back tomorrow!"
                ),
                colour=0x43B581,
            )])

        # 5 — CTA embed (no mentions)
        await channel.send(embeds=[_build_cta_embed()])

        total_pinged = len(at_risk) + len(dormant)
        log.info(
            "Daily reminder sent to #%s in %s (%d pinged: %d at-risk, %d dormant%s).",
            channel.name, guild.name, total_pinged, len(at_risk), len(dormant),
            ", force=True" if force else "",
        )


def setup(bot: discord.Bot) -> None:
    bot.add_cog(ReminderCog(bot))
