"""Built-in moderation rule templates (direct ban & suspect)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TemplateKind = Literal["ban", "suspect"]


@dataclass(frozen=True)
class RuleTemplate:
    id: str
    kind: TemplateKind
    label: str
    description: str
    rules_text: str


# --- Direct ban templates (instant ban + delete message) ---

BAN_TEMPLATES: list[RuleTemplate] = [
    RuleTemplate(
        id="ban_hack",
        kind="ban",
        label="🔓 هک و نفوذ",
        description="فروش/درخواست ابزار هک، رمزنگاری، نفوذ",
        rules_text=(
            "- فروش یا تبلیغ خدمات هک و نفوذ ممنوع\n"
            "مثال: هک اکانت میزنم\n"
            "مثال: رمز وای‌فای رو میگیرم\n"
            "مثال: نفوذ به سرور\n"
            "مثال: brute force\n"
            "مثال: sql injection"
        ),
    ),
    RuleTemplate(
        id="ban_vpn",
        kind="ban",
        label="🌐 VPN و پروکسی",
        description="فروش/تبلیغ VPN، پروکسی، فیلترشکن",
        rules_text=(
            "- فروش یا تبلیغ VPN و پروکسی ممنوع\n"
            "مثال: VPN میفروشم\n"
            "مثال: فیلترشکن دارم\n"
            "مثال: پروکسی رایگان\n"
            "مثال: v2ray config\n"
            "مثال: کانفیگ outline"
        ),
    ),
    RuleTemplate(
        id="ban_scam",
        kind="ban",
        label="💸 کلاهبرداری",
        description="کلاهبرداری، فیشینگ، درآمد تضمینی",
        rules_text=(
            "- کلاهبرداری و فیشینگ ممنوع\n"
            "مثال: درآمد تضمینی روزانه\n"
            "مثال: سرمایه‌گذاری ۱۰۰٪ سود\n"
            "مثال: لینک فیشینگ\n"
            "مثال: کارت به کارت کن\n"
            "مثال: پولتو بده سود میدم"
        ),
    ),
    RuleTemplate(
        id="ban_malware",
        kind="ban",
        label="🦠 بدافزار",
        description="ویروس، رansomware، keylogger",
        rules_text=(
            "- توزیع بدافزار ممنوع\n"
            "مثال: keylogger\n"
            "مثال: rat trojan\n"
            "مثال: ransomware\n"
            "مثال: ویروس میفرستم"
        ),
    ),
    RuleTemplate(
        id="ban_drugs",
        kind="ban",
        label="💊 مواد مخدر",
        description="فروش/تبلیغ مواد مخدر",
        rules_text=(
            "- فروش مواد مخدر ممنوع\n"
            "مثال: شیشه دارم\n"
            "مثال: مواد میفروشم\n"
            "مثال: تریاک"
        ),
    ),
    RuleTemplate(
        id="ban_adult",
        kind="ban",
        label="🔞 محتوای بزرگسال",
        description="پورنوگرافی و محتوای جنسی صریح",
        rules_text=(
            "- محتوای پورنوگرافی ممنوع\n"
            "مثال: فیلم سکسی\n"
            "مثال: پورن\n"
            "مثال: xxx"
        ),
    ),
]

# --- Suspect templates (admin review PM only) ---

SUSPECT_TEMPLATES: list[RuleTemplate] = [
    RuleTemplate(
        id="suspect_spam",
        kind="suspect",
        label="📢 اسپم تبلیغاتی",
        description="تبلیغ بدون مجوز، لینک کانال/ربات",
        rules_text=(
            "- تبلیغ کانال یا ربات بدون اجازه\n"
            "مثال: عضو کانالم بشید\n"
            "مثال: لینک کانال\n"
            "مثال: ربات منو نصب کن"
        ),
    ),
    RuleTemplate(
        id="suspect_crypto",
        kind="suspect",
        label="🪙 ارز دیجیتال",
        description="سیگنال/پامپ ارز دیجیتال",
        rules_text=(
            "- سیگنال و پامپ ارز دیجیتال\n"
            "مثال: سیگنال خرید\n"
            "مثال: پامپ میشه\n"
            "مثال: coin میخرم"
        ),
    ),
    RuleTemplate(
        id="suspect_account",
        kind="suspect",
        label="👤 خرید/فروش اکانت",
        description="خرید و فروش اکانت بازی/شبکه اجتماعی",
        rules_text=(
            "- خرید و فروش اکانت\n"
            "مثال: اکانت فری فایر\n"
            "مثال: اکانت اینستا\n"
            "مثال: اکانتم رو میفروشم"
        ),
    ),
    RuleTemplate(
        id="suspect_contact",
        kind="suspect",
        label="📞 درخواست تماس خصوصی",
        description="درخواست شماره/ایدی برای تماس خارج گروه",
        rules_text=(
            "- درخواست تماس خصوصی مشکوک\n"
            "مثال: شمارتو بده\n"
            "مثال: pv بده\n"
            "مثال: پیوی بیا"
        ),
    ),
    RuleTemplate(
        id="suspect_politics",
        kind="suspect",
        label="🏛 بحث سیاسی",
        description="بحث‌های سیاسی حساس",
        rules_text=(
            "- بحث سیاسی حساس\n"
            "مثال: رهبر\n"
            "مثال: انقلاب\n"
            "مثال: اعتراض"
        ),
    ),
]

ALL_TEMPLATES: list[RuleTemplate] = BAN_TEMPLATES + SUSPECT_TEMPLATES

_TEMPLATES_BY_ID: dict[str, RuleTemplate] = {t.id: t for t in ALL_TEMPLATES}

DEFAULT_ENABLED: dict[str, bool] = {
    "ban_hack": True,
    "ban_vpn": True,
    "ban_scam": True,
    "ban_malware": False,
    "ban_drugs": False,
    "ban_adult": False,
    "suspect_spam": False,
    "suspect_crypto": False,
    "suspect_account": False,
    "suspect_contact": False,
    "suspect_politics": False,
}


def get_template(template_id: str) -> RuleTemplate | None:
    return _TEMPLATES_BY_ID.get(template_id)


def parse_enabled_templates(raw: str | None) -> dict[str, bool]:
    """Parse JSON stored in DB; merge with defaults for missing keys."""
    import json

    result = dict(DEFAULT_ENABLED)
    if not raw or not raw.strip():
        return result
    try:
        stored = json.loads(raw)
        if isinstance(stored, dict):
            for key, val in stored.items():
                if key in _TEMPLATES_BY_ID:
                    result[key] = bool(val)
    except json.JSONDecodeError:
        pass
    return result


def serialize_enabled_templates(enabled: dict[str, bool]) -> str:
    import json

    filtered = {k: v for k, v in enabled.items() if k in _TEMPLATES_BY_ID}
    return json.dumps(filtered, ensure_ascii=False)


def build_ban_rules_text(enabled: dict[str, bool], custom_rules: str = "") -> str:
    """Merge enabled ban templates with custom ban rules."""
    parts: list[str] = []
    for tmpl in BAN_TEMPLATES:
        if enabled.get(tmpl.id, False):
            parts.append(tmpl.rules_text)
    if custom_rules.strip():
        parts.append(custom_rules.strip())
    return "\n\n".join(parts)


def build_suspect_rules_text(enabled: dict[str, bool], suspect_rules: str = "") -> str:
    """Merge enabled suspect templates with custom suspect rules."""
    parts: list[str] = []
    for tmpl in SUSPECT_TEMPLATES:
        if enabled.get(tmpl.id, False):
            parts.append(tmpl.rules_text)
    if suspect_rules.strip():
        parts.append(suspect_rules.strip())
    return "\n\n".join(parts)
