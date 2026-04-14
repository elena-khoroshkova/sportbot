# 🏋️ Telegram-бот Sports Challenge — руководство по установке

Это руководство проведёт вас через все шаги, чтобы запустить бота на Railway (бесплатный тариф).

---

## Что умеет бот

- Пользователи пишут боту в личные сообщения → выбирают **вид спорта**, **уровень** (Newbie / Regular / Pro), вводят **корпоративный email**
- Бот отправляет им **ссылку-приглашение в группу**
- Каждое утро бот публикует в группе **напоминание**: *"Опубликуйте фото тренировки!"*
- Когда кто-то публикует фото, бот **реагирует**, подтверждает его и отмечает пользователя ✅ в Google Sheets
- Все регистрации и ежедневные отметки хранятся в **Google Sheet**

---

## Шаг 1 — Создайте Telegram-бота

1. Откройте Telegram и найдите **@BotFather**
2. Отправьте `/newbot` и следуйте инструкциям (выберите имя и username, заканчивающийся на `bot`)
3. BotFather выдаст вам **Bot Token** — сохраните его (выглядит как `7123456789:AAFxxxxxx`)
4. По желанию задайте описание через `/setdescription` и аватар через `/setuserpic`

---

## Шаг 2 — Создайте Telegram-группу и узнайте её ID

1. Создайте новую Telegram-группу (это будет группа вашего челленджа)
2. Добавьте бота в группу и **сделайте его администратором** (ему нужны права отправлять сообщения и читать фото)
3. Создайте постоянную ссылку-приглашение: **Settings → Invite Links → Create Link** — сохраните её
4. Чтобы узнать **Group Chat ID**:
   - Временно добавьте [@userinfobot](https://t.me/userinfobot) в группу
   - Он отправит chat ID группы (отрицательное число вроде `-1001234567890`)
   - Удалите @userinfobot после того, как получите ID

---

## Шаг 3 — Настройте Google Sheets

### 3a — Создайте таблицу
1. Перейдите на [sheets.google.com](https://sheets.google.com) и создайте новую таблицу
2. Назовите её, например, **Sports Challenge Tracker**
3. Скопируйте **Spreadsheet ID** из URL:
   - URL выглядит так: `https://docs.google.com/spreadsheets/d/`**`1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms`**`/edit`
   - Выделенная часть — это Spreadsheet ID, сохраните его

### 3b — Включите Google Sheets API
1. Перейдите в [console.cloud.google.com](https://console.cloud.google.com)
2. Создайте новый проект (например, "Sports Bot")
3. Откройте **APIs & Services → Enable APIs** → найдите и включите **Google Sheets API**

### 3c — Создайте OAuth-клиент (Desktop app)
1. В Google Cloud Console откройте **APIs & Services → OAuth consent screen**
2. Настройте экран согласия (если попросит):
   - Выберите **External** (если нет Google Workspace-ограничений) или вариант, который подходит вашей организации
   - Заполните обязательные поля (название приложения и т.д.)
3. Откройте **APIs & Services → Credentials → Create Credentials → OAuth client ID**
4. Выберите тип приложения **Desktop app**
5. Сохраните значения **Client ID** и **Client secret** — они понадобятся для переменных:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`

### 3d — Получите `GOOGLE_REFRESH_TOKEN`
Бот использует OAuth refresh token, чтобы иметь доступ к вашей таблице без ручного входа.

1. Локально (на своём компьютере) установите зависимость:

```bash
pip install google-auth-oauthlib
```

2. Установите переменные окружения (или заполните `.env` для локального запуска):
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
3. Запустите скрипт:

```bash
python get_refresh_token.py
```

4. Откройте ссылку, войдите в Google-аккаунт, выдайте доступ
5. Скопируйте выведенное значение refresh token в `GOOGLE_REFRESH_TOKEN` (в Railway и/или в `.env`)

---

## Шаг 4 — Задеплойте на Railway

1. Перейдите на [railway.app](https://railway.app) и зарегистрируйтесь (бесплатно через GitHub)
2. Нажмите **New Project → Deploy from GitHub repo**
   - Сначала загрузите файлы бота в GitHub-репозиторий (см. ниже) или используйте **Deploy from template**
3. После подключения репозитория откройте ваш сервис → вкладка **Variables** → добавьте переменные:

| Переменная | Значение |
|---|---|
| `BOT_TOKEN` | Токен от BotFather |
| `GOOGLE_SHEET_ID` | Spreadsheet ID вашей таблицы |
| `GOOGLE_CLIENT_ID` | OAuth Client ID (из шага 3c) |
| `GOOGLE_CLIENT_SECRET` | OAuth Client secret (из шага 3c) |
| `GOOGLE_REFRESH_TOKEN` | Refresh token (из шага 3d) |
| `GROUP_CHAT_ID` | Chat ID группы (например, `-1001234567890`) |
| `GROUP_INVITE_LINK` | Ссылка-приглашение в группу |
| `DAILY_NOTIFY_TIME` | Время ежедневного напоминания в формате `HH:MM` (например, `09:00`) |
| `TIMEZONE` | Ваш часовой пояс (например, `Europe/Kyiv`, `Europe/London`, `America/New_York`) |

4. Railway задеплоит проект автоматически. Бот будет работать 24/7.

### Загрузка в GitHub (если нужно)
```bash
git init
git add bot.py requirements.txt Procfile
git commit -m "Initial sports bot"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

---

## Шаг 5 — Протестируйте

1. Напишите боту в личные сообщения в Telegram и отправьте `/start`
2. Пройдите регистрацию
3. Проверьте Google Sheet — должна появиться вкладка **Participants** с вашей записью
4. Отправьте фото в группу — бот должен ответить и записать отметку на дневной вкладке

---

## Структура Google Sheets

Бот автоматически создаёт два типа вкладок:

**Participants** — по одной строке на каждого зарегистрированного пользователя:
| Telegram ID | Full Name | Username | Sport | Level | Corporate Email | Registered At |

**Дневные вкладки** (например, `2026-04-06`) — создаются в те дни, когда кто-то публикует пост:
| Telegram ID | Full Name | Photo ✅ | Time |

---

## Команды

| Команда | Где | Что делает |
|---|---|---|
| `/start` | ЛС с ботом | Запускает регистрацию |
| `/cancel` | ЛС с ботом | Отменяет регистрацию |
| `/stats` | Где угодно | Показывает, сколько людей отметилось сегодня |

---

## Решение проблем

**Бот не отвечает в группе**
→ Убедитесь, что бот — администратор группы и у него есть право "Read Messages"

**Google Sheets не обновляется**
→ Проверьте, что корректно заданы `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` и `GOOGLE_SHEET_ID` (и что вы выдавали доступ именно тому Google-аккаунту, который должен писать в таблицу)

**Ошибка "MODULE_NOT_FOUND" на Railway**
→ Убедитесь, что `requirements.txt` лежит в корне репозитория

**Как получить Chat ID в Telegram Web**
→ Откройте группу в web.telegram.org — в URL после символа `#` будет указан chat ID

---

## Нужно что-то изменить?

- **Изменить активности или уровни**: отредактируйте кнопки клавиатуры в `bot.py` (ищите `sport_Running`, `level_Newbie`)
- **Изменить текст напоминания**: отредактируйте функцию `daily_reminder()` в `bot.py`
- **Изменить время уведомления**: обновите переменную окружения `DAILY_NOTIFY_TIME` в Railway

---

*Сделано на python-telegram-bot, gspread и APScheduler.*
