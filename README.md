# 🎮 Sigmoji

> **Decode the emojis. Race to answer. Earn glory.**

Sigmoji is an addictive Discord party game where the bot posts a cryptic sequence of emojis and players race to type the correct answer in chat. First one right wins points, a fun fact, and XP toward their level — with daily streaks, 21 unlockable achievements, and a global leaderboard keeping competition fierce.

---

## Table of Contents

1. [Discord Developer Setup](#1-discord-developer-setup)
2. [Local Setup](#2-local-setup)
3. [Railway Deployment](#3-railway-deployment)
4. [Configuration Reference](#4-configuration-reference)
5. [How to Play](#5-how-to-play)
6. [Commands](#6-commands)
7. [Scoring & Levelling](#7-scoring--levelling)
8. [Achievements](#8-achievements)
9. [Adding Questions](#9-adding-questions)

---

## 1. Discord Developer Setup

### 1.1 Create the application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → give it a name (e.g. *Sigmoji*) → **Create**
3. Optionally add an icon under **General Information**

### 1.2 Create the bot

1. In the left sidebar click **Bot**
2. Click **Add Bot** → **Yes, do it!**
3. Under the bot's username click **Reset Token** → copy the token somewhere safe — you'll need it in step 2.4

### 1.3 Enable required intents

Still on the **Bot** page, scroll down to **Privileged Gateway Intents** and turn **ON**:

| Intent | Why it's needed |
|---|---|
| **Message Content Intent** | Lets the bot read players' plain-text answers in chat |

> Without this intent `message.content` is always empty and no answer will ever register as correct.

Save changes.

### 1.4 Generate an invite URL

1. In the left sidebar click **OAuth2 → URL Generator**
2. Under **Scopes** tick:
   - `bot`
   - `applications.commands`
3. Under **Bot Permissions** tick:
   - `Send Messages`
   - `Read Message History`
   - `Add Reactions`
   - `Embed Links`
   - `Use Slash Commands`
4. Copy the generated URL at the bottom and open it in your browser
5. Select your server → **Authorise**

---

## 2. Local Setup

### Prerequisites

- Python 3.10 or newer — [python.org](https://python.org)
- A Discord server where you have **Manage Server** permission

### 2.1 Clone and enter the repo

```bash
git clone <your-repo-url>
cd sigmoji
```

### 2.2 Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
DISCORD_TOKEN=paste_your_bot_token_here

# Set to your test server's ID for instant slash command registration.
# In Discord: right-click your server icon → Copy Server ID
# (Requires Developer Mode: Settings → Advanced → Developer Mode)
DISCORD_GUILD_ID=your_server_id_here

PORT=8080
```

> **Tip:** Set `DISCORD_GUILD_ID` while developing — slash commands register instantly in guild mode instead of taking up to 1 hour globally.

### 2.3 Run the bot

**macOS / Linux:**
```bash
./start.sh
```

**Windows:**
```
start.bat
```

The script will:
- Detect your Python version
- Create and activate a virtual environment
- Install all dependencies from `requirements.txt`
- Start the bot and status dashboard

### 2.4 Verify it's running

Open [http://localhost:8080](http://localhost:8080) — you should see the bot connected and your guild listed.

---

## 3. Railway Deployment

1. Push the repo to GitHub
2. In [Railway](https://railway.app) → **New Project → Deploy from GitHub repo** → select this repo
3. Under **Variables**, add:
   - `DISCORD_TOKEN` — your bot token
   - `PORT` — Railway sets this automatically, but you can override it
   - **Do not set** `DISCORD_GUILD_ID` in production — leave it blank for global commands
4. Railway will auto-deploy on every push to `main`

> Railway provides a persistent filesystem volume for `sigmoji.db`. No external database needed.

---

## 4. Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | *(required)* | Bot token from the Discord Developer Portal |
| `DISCORD_GUILD_ID` | *(blank)* | Guild ID for instant dev-mode command registration. Remove for production. |
| `PORT` | `8080` | Port for the status dashboard (`/`) and health endpoint (`/health`) |
| `DATABASE_PATH` | `sigmoji.db` | Path to the SQLite database file |

---

## 5. How to Play

### Stage 1 — Pick a category

Type `/play` to get a random category, or choose one:

```
/play
/play Kerala Places
/play Bollywood Movies
```

### Stage 2 — Decode the clue

The bot posts an embed like this:

```
🎮 Sigmoji — Decode the Emojis!
Category: Kerala Places  |  Difficulty: 🟡 Medium

🔡 The Clue
# 🐔 🧥

⏱️ 60s to answer  •  💡 /hint (4 available)  •  ⏭️ /skip to give up
```

### Stage 3 — Race to answer

Just type your answer as plain text in the same channel — no prefix, no slash command:

```
Kozhikode
```

Everyone can guess. There's no penalty for wrong answers (the bot reacts with ❌ so you know it saw your guess). First correct answer wins the round.

### Stage 4 — Winner!

```
🎉 alice got it!

Answer: Kozhikode
⏱️ Time: 8.3s  🚀 Very Fast
💰 Points: +178  (+10 streak bonus)

📖 Did you know?
Vasco da Gama landed here in 1498 — opening Europe's sea route to India!...

📊 Decoder (Lv 3)
[████████░░░░] 680/800 XP
🔥 4-day streak!
```

### Stage 5 — Repeat!

Keep playing to climb the leaderboard, unlock achievements, and level up. Daily streaks give bonus points for consecutive play.

---

## 6. Commands

| Command | Description |
|---|---|
| `/play [category]` | Start a round. Category autocompletes as you type. |
| `/hint` | Reveal one letter of the answer. Costs −20 pts per hint. |
| `/skip` | Give up and reveal the answer immediately. |
| `/categories` | List all available categories and question counts. |
| `/profile [user]` | View a player's full stat card: level, win rate, badges, top categories. |
| `/streak` | Check your daily streak and see how close the next milestone is. |
| `/achievements [user]` | Full achievement list — locked and unlocked. |
| `/leaderboard [category]` | Top 10 players globally or filtered by category. |
| `/rank [user]` | Your current rank plus the player just ahead of you. |

---

## 7. Scoring & Levelling

### Points per round

```
Points = base + speed_bonus − hint_penalty
```

| Component | Value |
|---|---|
| Base (Easy) | 50 pts |
| Base (Medium) | 100 pts |
| Base (Hard) | 200 pts |
| Speed bonus | up to +100 pts, drops 2 pts/second |
| Hint penalty | −20 pts per hint used |
| Minimum awarded | 10 pts |

**Speed tiers:**

| Response time | Label |
|---|---|
| < 3 s | ⚡ LIGHTNING! |
| < 5 s | 🌩️ Blazing |
| < 10 s | 🚀 Very Fast |
| < 20 s | 💨 Fast |
| < 40 s | 👍 Good |
| 40 s+ | 🐢 Steady |

### Daily streak bonus

Playing every day keeps your streak alive. Each win awards a streak bonus on top of your points:

| Streak | Bonus |
|---|---|
| Day 1 | +5 pts |
| Day 2 | +10 pts |
| Day 3 | +15 pts |
| … | … |
| Day 10+ | +50 pts (max) |

### Levels

| Level | Name | XP required |
|---|---|---|
| 1 | ⬜ Rookie | 0 |
| 2 | 🟦 Explorer | 150 |
| 3 | 🟩 Decoder | 400 |
| 4 | 🟨 Cipher | 800 |
| 5 | 🟧 Mastermind | 1 400 |
| 6 | 🟥 Wizard | 2 200 |
| 7 | 🟪 Oracle | 3 400 |
| 8 | 🔵 Sage | 5 000 |
| 9 | 🔴 Virtuoso | 7 200 |
| 10 | 🌟 Grandmaster | 10 000 |
| 11 | 💎 SIGMOJI | 14 000 |

---

## 8. Achievements

Achievements are unlocked automatically and displayed as badges in `/profile`.

| Tier | Achievement | How to unlock |
|---|---|---|
| 🥉 Bronze | First Blood 🩸 | Win your first round |
| 🥉 Bronze | Quick Draw ⚡ | Answer in under 10 seconds |
| 🥉 Bronze | Getting Started 🌱 | Win 5 total games |
| 🥉 Bronze | Hooked 🪝 | Win 25 total games |
| 🥉 Bronze | On Fire 🔥 | 3-day play streak |
| 🥉 Bronze | Category Lover 🎯 | Win 10 games in one category |
| 🥉 Bronze | Night Owl 🦉 | Win between midnight and 4 AM |
| 🥉 Bronze | Early Bird 🐦 | Win before 7 AM |
| 🥈 Silver | Lightning 🌩️ | Answer in under 5 seconds |
| 🥈 Silver | Committed 🔥🔥 | 7-day play streak |
| 🥈 Silver | Centurion 💯 | Win 100 total games |
| 🥈 Silver | No Peeking 🙈 | Win 10 games without hints |
| 🥈 Silver | Pure Genius 🧠 | Solve a hard question without hints |
| 🥈 Silver | Jack of All Trades 🃏 | Win at least once in every category |
| 🥈 Silver | Category Expert 🏅 | Win 50 games in one category |
| 🥈 Silver | Halfway There ⭐ | Reach Level 5 |
| 🥇 Gold | Telepathic 🔮 | Answer in under 3 seconds |
| 🥇 Gold | Inferno 🌋 | 30-day play streak |
| 🥇 Gold | Unstoppable 🌪️ | Win 500 total games |
| 💎 Diamond | Eternal Flame ♾️ | 100-day play streak |
| 💎 Diamond | Legend 🏆 | Win 1000 total games |
| 💎 Diamond | SIGMOJI Master 💎 | Reach the maximum level |

---

## 9. Adding Questions

Open `data/questions.csv` and add a row. The bot picks up new questions on the next restart.

### Column format

| Column | Description | Example |
|---|---|---|
| `id` | Unique integer | `61` |
| `category` | Category name (must match existing or creates a new one) | `Kerala Places` |
| `answer` | The correct answer | `Kozhikode` |
| `emojis` | Space-separated emoji clue | `🐔 🧥` |
| `answer_alts` | Pipe-separated alternate spellings (can be empty) | `calicut\|kozhikodan` |
| `fact` | Fun fact revealed after a correct guess | `Vasco da Gama landed here…` |
| `difficulty` | `easy`, `medium`, or `hard` | `medium` |

### Example row

```csv
61,Kerala Places,Thiruvananthapuram,🕉️ 🐍 🌊,trivandrum,"Capital of Kerala! The name means City of the Sacred Serpent (Thiru+Anantha+Puram). Home to Padmanabhaswamy Temple.",hard
```

### Tips for writing good emoji clues

- **Phonetic wordplay** works best for place names — break the word into syllables and find emojis that sound like them
  - `Kozhikode` → 🐔 (Kozhi = Chicken) + 🧥 (Coat → Code)
  - `Munnar` → 3️⃣ (Moonu = Three) + ⛰️ (Aar = River/Mountain)
- **Cultural/visual association** works for movies, foods, and cities
  - `Titanic` → 🚢 💔 🌊
  - `Biryani` → 🍚 🐑 🌶️
- Aim for 2–4 emojis per clue — enough to be a puzzle, not so many it becomes obvious
- Write the logic in the `fact` field so players understand the wordplay after they guess

---

*Built with [py-cord](https://pycord.dev) · Deployed on [Railway](https://railway.app)*
