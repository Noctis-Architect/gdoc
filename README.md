# gdoc — Group Doctor

**gdoc** (Group Doctor) is an AI-powered Telegram group moderation bot. It combines fast local filters with OpenAI or Google Gemini classification to detect scams, spam, and policy violations — with a Persian-first admin panel.

Repository: [https://github.com/Noctis-Architect/gdoc](https://github.com/Noctis-Architect/gdoc)

---

## Features

- **Two-layer moderation** — regex/keyword blacklist (Layer 1) + AI classification (Layer 2)
- **Per-group settings** — strictness level, action mode, warning threshold, custom rules
- **Super-admin panel** — manage groups, API keys, and global settings from Telegram
- **Persian UI** — admin panels and messages in Farsi
- **Production-ready** — SQLite or PostgreSQL, Redis caching, systemd service, polling or webhook mode
- **Audit log** — review flagged messages and moderation decisions per group

---

## Requirements

| Component | Version |
|-----------|---------|
| Linux server (Debian/Ubuntu, RHEL/CentOS) | — |
| Python | 3.10+ |
| Redis | local instance |
| Telegram Bot Token | from [@BotFather](https://t.me/BotFather) |
| AI API key | OpenAI or Google Gemini |

---

## Quick Install (from GitHub)

The installer clones the repository (if needed), installs system dependencies, creates a Python virtual environment, writes `.env`, and registers a **systemd** service named `tg_moderator`.

### Option A — One command (recommended)

Install directly from GitHub with curl:

```bash
curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh | sudo bash
```

Alternative (saves script first, then runs — same prompts):

```bash
curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh -o /tmp/gdoc-install.sh
sudo bash /tmp/gdoc-install.sh
```

Custom install directory:

```bash
curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh -o /tmp/gdoc-install.sh
sudo INSTALL_DIR=/home/gdoc/gdoc bash /tmp/gdoc-install.sh
```

Non-interactive install via environment variables:

```bash
curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh -o /tmp/gdoc-install.sh
sudo BOT_TOKEN="..." SUPER_ADMIN_ID="123456789" \
  USE_WEBHOOK="true" WEBHOOK_DOMAIN="bot.example.com" SSL_EMAIL="you@example.com" \
  CF_API_TOKEN="..." bash /tmp/gdoc-install.sh
```

> **Note:** Use `sudo bash`, not `sudo curl`. Only the installer needs root.  
> **AI settings** (API key, base URL, model) are configured later via `/superadmin` in Telegram — not during install.

### Option B — Clone, then install

```bash
git clone https://github.com/Noctis-Architect/gdoc.git
cd gdoc
sudo bash install.sh
```

The interactive installer will ask for:

1. **Telegram Bot Token** — from [@BotFather](https://t.me/BotFather)
2. **Super Admin ID** — your numeric Telegram user ID (use [@userinfobot](https://t.me/userinfobot))
3. **Domain & SSL** — webhook domain, Let's Encrypt email, and optional Cloudflare API token for automatic SSL
4. **Polling fallback** — set webhook to `false` if you have no public domain

**Not asked during install:** AI provider, API key, base URL, or model — configure these from `/superadmin` in Telegram (super admin only).

When finished, the bot runs as a systemd service.

---

## Service Management

```bash
# Check status
sudo systemctl status tg_moderator

# View live logs
sudo journalctl -u tg_moderator -f

# Restart after config changes
sudo systemctl restart tg_moderator

# Stop / start
sudo systemctl stop tg_moderator
sudo systemctl start tg_moderator
```

Default install path: `/opt/gdoc`  
Environment file: `/opt/gdoc/.env`  
Database (SQLite): `/opt/gdoc/data/gdoc.db`

---

## Telegram Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Add the bot to your Telegram group.
3. **Promote the bot to administrator** (required to delete messages and ban users).
4. In the group, send `/panel` to open the group admin panel.
5. As the owner, send `/superadmin` in a private chat with the bot for the global control panel.

### Bot Commands

| Command | Where | Description |
|---------|-------|-------------|
| `/start` | Any | Welcome message |
| `/help` | Any | Usage help |
| `/panel` | Group | Group moderation settings (group admins only) |
| `/superadmin` | Private | Owner control panel (super admin only) |

---

## Configuration

All settings live in `.env`. Copy `.env.example` for reference:

```bash
cp .env.example .env
nano .env
sudo systemctl restart tg_moderator
```

### Key variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_TOKEN` | — | Telegram bot token (required) |
| `SUPER_ADMIN_ID` | — | Owner Telegram numeric ID (required) |
| `AI_PROVIDER` | `openai` | `openai` or `gemini` — set via `/superadmin` panel |
| `AI_API_KEY` | — | API key — set via `/superadmin` panel (optional env fallback) |
| `AI_BASE_URL` | — | Custom API base URL — set via `/superadmin` panel |
| `AI_MODEL` | `gpt-4o-mini` | Model name — set via `/superadmin` panel |
| `DB_BACKEND` | `sqlite` | `sqlite` or `postgres` |
| `DATABASE_URL` | `sqlite:///./data/gdoc.db` | SQLite path |
| `POSTGRES_DSN` | — | PostgreSQL connection string (if using postgres) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `USE_WEBHOOK` | `false` | `true` to use webhook instead of polling |
| `WEBHOOK_URL` | — | Public HTTPS base URL (webhook mode) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## Manual Install (without systemd)

For development or non-systemd environments:

```bash
git clone https://github.com/Noctis-Architect/gdoc.git
cd gdoc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your values
python bot.py
```

Ensure Redis is running locally before starting the bot.

---

## Architecture

```
Telegram Update
      │
      ▼
  bot.py (handlers)
      │
      ▼
ModerationEngine
      ├── Layer 1: regex / keyword blacklist (instant)
      └── Layer 2: AI classifier (OpenAI / Gemini)
      │
      ▼
  Action: delete / warn / ban (per group config)
      │
      ├── Database (SQLite / PostgreSQL)
      └── Redis (config & dedupe cache)
```

---

## Troubleshooting

**Bot does not start**

```bash
sudo journalctl -u tg_moderator -n 50 --no-pager
```

Check that `BOT_TOKEN` and `SUPER_ADMIN_ID` are set in `.env`. Configure AI via `/superadmin` if moderation is not working.

**Bot cannot delete messages**

Promote the bot to **administrator** in the group with *Delete messages* permission.

**Redis connection error**

```bash
sudo systemctl status redis-server   # Debian/Ubuntu
sudo systemctl status redis          # RHEL/CentOS
```

**Re-run installer on an existing clone**

If you already cloned the repo, run `sudo bash install.sh` from inside the project directory — the script detects the source tree and skips cloning.

**Change install directory**

```bash
sudo INSTALL_DIR=/custom/path bash install.sh
```

---

## Project Structure

```
gdoc/
├── bot.py              # Entry point
├── config.py           # Environment configuration
├── moderation.py       # Two-layer moderation engine
├── ai.py               # OpenAI / Gemini classifier
├── database.py         # SQLite / PostgreSQL layer
├── redis_cache.py      # Redis caching
├── i18n.py             # Persian UI strings
├── handlers/           # Commands, callbacks, message handler
├── install.sh          # Production installer (GitHub + systemd)
├── requirements.txt
└── .env.example
```

---

## License

See repository for license details.

---

<br>

---

# gdoc — دکتر گروه

**gdoc** (Group Doctor / دکتر گروه) یک ربات تلگرام برای مدیریت و moderation گروه‌هاست. این ربات با ترکیب فیلتر محلی و هوش مصنوعی (OpenAI یا Gemini) محتوای مخرب، اسپم و کلاهبرداری را شناسایی می‌کند. پنل مدیریت به زبان فارسی است.

مخزن گیت‌هاب: [https://github.com/Noctis-Architect/gdoc](https://github.com/Noctis-Architect/gdoc)

---

## امکانات

- **Moderation دو لایه** — فیلتر کلمات/regex (لایه ۱) + طبقه‌بندی AI (لایه ۲)
- **تنظیمات جدا برای هر گروه** — سطح سخت‌گیری، نوع اقدام، آستانه اخطار، قوانین سفارشی
- **پنل سوپرادمین** — مدیریت گروه‌ها و تنظیمات سراسری از داخل تلگرام
- **رابط فارسی** — پیام‌ها و پنل‌های مدیریت به فارسی
- **آماده production** — SQLite یا PostgreSQL، کش Redis، سرویس systemd، polling یا webhook
- **لاگ audit** — بررسی پیام‌های پرچم‌گذاری‌شده در هر گروه

---

## پیش‌نیازها

| مورد | نسخه |
|------|------|
| سرور لینوکس (Debian/Ubuntu یا RHEL/CentOS) | — |
| Python | 3.10 به بالا |
| Redis | نصب محلی |
| توکن ربات تلگرام | از [@BotFather](https://t.me/BotFather) |
| کلید API هوش مصنوعی | OpenAI یا Google Gemini |

---

## نصب سریع (از گیت‌هاب)

اسکریپت `install.sh` در صورت نیاز مخزن را clone می‌کند، وابستگی‌های سیستم را نصب می‌کند، محیط مجازی Python می‌سازد، فایل `.env` را می‌نویسد و سرویس **systemd** با نام `tg_moderator` ثبت می‌کند.

### روش ۱ — یک دستور (پیشنهادی)

نصب مستقیم از گیت‌هاب با curl:

```bash
curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh | sudo bash
```

روش جایگزین (ذخیره اسکریپت و اجرا):

```bash
curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh -o /tmp/gdoc-install.sh
sudo bash /tmp/gdoc-install.sh
```

مسیر نصب دلخواه:

```bash
curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh -o /tmp/gdoc-install.sh
sudo INSTALL_DIR=/home/gdoc/gdoc bash /tmp/gdoc-install.sh
```

نصب بدون تعامل با متغیر محیطی:

```bash
curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh -o /tmp/gdoc-install.sh
sudo BOT_TOKEN="..." SUPER_ADMIN_ID="123456789" \
  USE_WEBHOOK="true" WEBHOOK_DOMAIN="bot.example.com" SSL_EMAIL="you@example.com" \
  CF_API_TOKEN="..." bash /tmp/gdoc-install.sh
```

> **نکته:** فقط `bash` را با sudo اجرا کنید، نه `curl` را.  
> **تنظیمات AI** (کلید API، Base URL، مدل) بعداً از `/superadmin` در تلگرام انجام می‌شود — نه در زمان نصب.

### روش ۲ — Clone و سپس نصب

```bash
git clone https://github.com/Noctis-Architect/gdoc.git
cd gdoc
sudo bash install.sh
```

در حین نصب، این موارد از شما پرسیده می‌شود:

1. **توکن ربات تلگرام** — از [@BotFather](https://t.me/BotFather)
2. **شناسه عددی سوپرادمین** — ID عددی تلگرام شما (از [@userinfobot](https://t.me/userinfobot))
3. **دامنه و SSL** — دامنه وب‌هوک، ایمیل Let's Encrypt، و در صورت نیاز توکن API کلادفلر برای SSL خودکار
4. **Polling** — اگر دامنه عمومی ندارید، webhook را `false` بگذارید

**در زمان نصب پرسیده نمی‌شود:** پرووایدر AI، کلید API، Base URL، مدل — فقط از `/superadmin` در تلگرام (فقط سوپرادمین).

پس از اتمام، ربات به‌صورت سرویس systemd اجرا می‌شود.

---

## مدیریت سرویس

```bash
# وضعیت سرویس
sudo systemctl status tg_moderator

# مشاهده لاگ زنده
sudo journalctl -u tg_moderator -f

# راه‌اندازی مجدد پس از تغییر تنظیمات
sudo systemctl restart tg_moderator

# توقف / شروع
sudo systemctl stop tg_moderator
sudo systemctl start tg_moderator
```

مسیر پیش‌فرض نصب: `/opt/gdoc`  
فایل تنظیمات: `/opt/gdoc/.env`  
پایگاه داده (SQLite): `/opt/gdoc/data/gdoc.db`

---

## راه‌اندازی در تلگرام

1. با [@BotFather](https://t.me/BotFather) ربات بسازید و توکن را کپی کنید.
2. ربات را به گروه تلگرام اضافه کنید.
3. ربات را **به ادمین گروه ارتقا دهید** (برای حذف پیام و بن کاربر لازم است).
4. در گروه دستور `/panel` را بفرستید تا پنل مدیریت گروه باز شود.
5. به‌عنوان مالک، در چت خصوصی با ربات `/superadmin` را بفرستید.

### دستورات ربات

| دستور | محل استفاده | توضیح |
|-------|-------------|-------|
| `/start` | هر جا | پیام خوش‌آمد |
| `/help` | هر جا | راهنما |
| `/panel` | گروه | پنل moderation (فقط ادمین‌های گروه) |
| `/superadmin` | خصوصی | پنل مالک (فقط سوپرادمین) |

---

## تنظیمات

همه تنظیمات در فایل `.env` هستند:

```bash
cp .env.example .env
nano .env
sudo systemctl restart tg_moderator
```

### متغیرهای مهم

| متغیر | پیش‌فرض | توضیح |
|-------|---------|-------|
| `BOT_TOKEN` | — | توکن ربات (الزامی) |
| `SUPER_ADMIN_ID` | — | ID عددی مالک (الزامی) |
| `AI_PROVIDER` | `openai` | `openai` یا `gemini` — از پنل `/superadmin` |
| `AI_API_KEY` | — | کلید API — از پنل `/superadmin` (اختیاری در env) |
| `AI_BASE_URL` | — | آدرس پایه API — از پنل `/superadmin` |
| `AI_MODEL` | `gpt-4o-mini` | نام مدل — از پنل `/superadmin` |
| `DB_BACKEND` | `sqlite` | `sqlite` یا `postgres` |
| `REDIS_URL` | `redis://localhost:6379/0` | اتصال Redis |
| `USE_WEBHOOK` | `false` | `true` برای webhook |
| `LOG_LEVEL` | `INFO` | سطح لاگ |

---

## نصب دستی (بدون systemd)

برای توسعه یا محیط‌های بدون systemd:

```bash
git clone https://github.com/Noctis-Architect/gdoc.git
cd gdoc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# مقادیر .env را ویرایش کنید
python bot.py
```

قبل از اجرا Redis باید در حال اجرا باشد.

---

## عیب‌یابی

**ربات بالا نمی‌آید**

```bash
sudo journalctl -u tg_moderator -n 50 --no-pager
```

مطمئن شوید `BOT_TOKEN` و `SUPER_ADMIN_ID` در `.env` تنظیم شده‌اند. AI را از `/superadmin` پیکربندی کنید.

**ربات پیام حذف نمی‌کند**

ربات را **ادمین** کنید و مجوز *Delete messages* را فعال کنید.

**خطای اتصال Redis**

```bash
sudo systemctl status redis-server   # Debian/Ubuntu
sudo systemctl status redis          # RHEL/CentOS
```

**نصب مجدد روی clone موجود**

اگر قبلاً clone کرده‌اید، از داخل پوشه پروژه `sudo bash install.sh` را اجرا کنید — اسکریپت source را تشخیص می‌دهد و clone مجدد انجام نمی‌دهد.

**تغییر مسیر نصب**

```bash
sudo INSTALL_DIR=/custom/path bash install.sh
```

---

## ساختار پروژه

```
gdoc/
├── bot.py              # نقطه ورود
├── config.py           # تنظیمات محیطی
├── moderation.py       # موتور moderation دو لایه
├── ai.py               # طبقه‌بند OpenAI / Gemini
├── database.py         # لایه SQLite / PostgreSQL
├── redis_cache.py      # کش Redis
├── i18n.py             # متن‌های فارسی UI
├── handlers/           # دستورات، callback، handler پیام
├── install.sh          # نصب production (GitHub + systemd)
├── requirements.txt
└── .env.example
```
