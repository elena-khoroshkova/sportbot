# 🏋️ Sports Challenge Telegram Bot — Setup Guide

This guide walks you through everything you need to get the bot running on Railway (free tier).

---

## What the bot does

- Users DM the bot → pick their **sport**, **level** (Newbie / Regular / Pro), enter **corporate email**
- Bot sends them the **group invite link**
- Every morning the bot posts a **reminder** in the group: *"Post your workout photo!"*
- When someone posts a photo, the bot **reacts**, confirms it, and marks the user as ✅ in Google Sheets
- All registrations and daily logs are stored in a **Google Sheet**

---

## Step 1 — Create your Telegram bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts (choose a name and username ending in `bot`)
3. BotFather will give you a **Bot Token** — save it (looks like `7123456789:AAFxxxxxx`)
4. Optionally set a description with `/setdescription` and a profile photo with `/setuserpic`

---

## Step 2 — Create your Telegram group and get its ID

1. Create a new Telegram group (this is your challenge group)
2. Add your bot to the group and **make it an Admin** (it needs permission to send messages and read photos)
3. Create a permanent invite link: group **Settings → Invite Links → Create Link** — save it
4. To find the **Group Chat ID**:
   - Add [@userinfobot](https://t.me/userinfobot) to the group temporarily
   - It will post the group's chat ID (a negative number like `-1001234567890`)
   - Remove @userinfobot after you have the ID

---

## Step 3 — Set up Google Sheets

### 3a — Create the spreadsheet
1. Go to [sheets.google.com](https://sheets.google.com) and create a new spreadsheet
2. Name it something like **Sports Challenge Tracker**
3. Copy the **Spreadsheet ID** from the URL:
   - URL looks like: `https://docs.google.com/spreadsheets/d/`**`1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms`**`/edit`
   - The bold part is your Spreadsheet ID — save it

### 3b — Create a Google Cloud service account
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (e.g. "Sports Bot")
3. Go to **APIs & Services → Enable APIs** → search for and enable **Google Sheets API**
4. Go to **APIs & Services → Credentials → Create Credentials → Service Account**
5. Give it any name (e.g. `sports-bot`), click **Done**
6. Click the service account you just created → **Keys** tab → **Add Key → Create new key → JSON**
7. A JSON file will download — open it in a text editor and **copy the entire contents**

### 3c — Share the spreadsheet with the service account
1. In the downloaded JSON, find the `"client_email"` field (looks like `sports-bot@yourproject.iam.gserviceaccount.com`)
2. Open your Google Sheet → **Share** → paste that email → give it **Editor** access
3. Click **Send** (ignore the "this email doesn't have a Google account" warning — it's fine)

---

## Step 4 — Deploy on Railway

1. Go to [railway.app](https://railway.app) and sign up (free with GitHub)
2. Click **New Project → Deploy from GitHub repo**
   - Push the bot files to a GitHub repo first (see below), or use **Deploy from template**
3. After connecting the repo, click your service → **Variables** tab → add these:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | Your token from BotFather |
| `GOOGLE_SHEET_ID` | Your spreadsheet ID |
| `GOOGLE_CREDENTIALS_JSON` | Paste the entire JSON from Step 3b (as one line) |
| `GROUP_CHAT_ID` | Your group's chat ID (e.g. `-1001234567890`) |
| `GROUP_INVITE_LINK` | Your group's invite link |
| `DAILY_NOTIFY_TIME` | Time to send daily reminder in `HH:MM` format (e.g. `09:00`) |
| `TIMEZONE` | Your timezone (e.g. `Europe/Kyiv`, `Europe/London`, `America/New_York`) |

4. Railway will auto-deploy. Your bot is now live 24/7!

### Pushing to GitHub (if needed)
```bash
git init
git add bot.py requirements.txt Procfile
git commit -m "Initial sports bot"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

---

## Step 5 — Test it

1. DM your bot on Telegram and send `/start`
2. Go through the registration flow
3. Check your Google Sheet — you should see a **Participants** tab with your entry
4. Post a photo in the group — the bot should reply and log you in a daily tab

---

## Google Sheets structure

The bot creates two types of tabs automatically:

**Participants** tab — one row per registered user:
| Telegram ID | Full Name | Username | Sport | Level | Corporate Email | Registered At |

**Daily tabs** (e.g. `2026-04-06`) — created each day when someone posts:
| Telegram ID | Full Name | Photo ✅ | Time |

---

## Commands

| Command | Where | What it does |
|---|---|---|
| `/start` | DM with bot | Starts registration |
| `/cancel` | DM with bot | Cancels registration |
| `/stats` | Anywhere | Shows how many people logged today |

---

## Troubleshooting

**Bot doesn't respond in the group**
→ Make sure the bot is an Admin in the group with "Read Messages" permission

**Google Sheets not updating**
→ Double-check the service account email is shared on the sheet with Editor access

**"MODULE_NOT_FOUND" on Railway**
→ Make sure `requirements.txt` is in the root of your repo

**Getting the Chat ID on Telegram Web**
→ Open the group in web.telegram.org — the URL will show the chat ID after the `#` sign

---

## Need to change something?

- **Change activities or levels**: edit the keyboard buttons in `bot.py` (search for `sport_Running`, `level_Newbie`)
- **Change reminder message**: edit the `daily_reminder()` function in `bot.py`
- **Change notification time**: update the `DAILY_NOTIFY_TIME` environment variable on Railway

---

*Built with python-telegram-bot, gspread, and APScheduler.*
