#!/usr/bin/env bash
# gdoc (Group Doctor) — Telegram Group Moderator Bot uninstaller
set -euo pipefail

APP_NAME="gdoc"
SERVICE_NAME="tg_moderator"
DEFAULT_INSTALL_DIR="/opt/gdoc"

INSTALL_DIR=""
VENV_DIR=""
ENV_FILE=""
DATA_DIR=""
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Behaviour flags (override via environment)
# YES=1 / FORCE=1           — skip confirmation prompts
# PURGE=1                   — remove entire install directory (includes data, .env, venv, source)
# KEEP_DATA=1               — keep data/ even when removing install dir (default unless PURGE)
# REMOVE_SSL=1            — revoke Let's Encrypt certificate for the webhook domain
# REMOVE_NGINX=1            — remove nginx site configs (default: auto when webhook domain found)
# REMOVE_SYSTEM_PACKAGES=0  — also remove redis/nginx/certbot installed for gdoc (not recommended)
YES="${YES:-${FORCE:-0}}"
PURGE="${PURGE:-0}"
KEEP_DATA="${KEEP_DATA:-$([[ "${PURGE}" == "1" ]] && echo 0 || echo 1)}"
REMOVE_SSL="${REMOVE_SSL:-0}"
REMOVE_NGINX="${REMOVE_NGINX:-}"
REMOVE_SYSTEM_PACKAGES="${REMOVE_SYSTEM_PACKAGES:-0}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        log_warn "حذف سرویس systemd و تنظیمات nginx نیاز به دسترسی root دارد."
        log_warn "دوباره اجرا کنید: sudo bash uninstall.sh"
        exit 1
    fi
}

prompt_read() {
    local _input=""
    if [[ -t 0 ]]; then
        read -r "$@" _input || true
    elif [[ -r /dev/tty ]]; then
        read -r "$@" _input </dev/tty || true
    else
        log_error "ترمینال تعاملی در دسترس نیست."
        log_error "برای حذف بدون پرسش: sudo YES=1 bash uninstall.sh"
        exit 1
    fi
    printf '%s' "${_input}"
}

confirm() {
    local message="$1"
    local default_no="${2:-1}"
    local answer=""

    if [[ "${YES}" == "1" ]]; then
        return 0
    fi

    if [[ "${default_no}" == "1" ]]; then
        answer="$(prompt_read -p "${message} [y/N]: ")"
        [[ "${answer}" =~ ^[Yy]$ ]]
    else
        answer="$(prompt_read -p "${message} [Y/n]: ")"
        [[ -z "${answer}" || "${answer}" =~ ^[Yy]$ ]]
    fi
}

read_env_value() {
    local key="$1"
    local file="$2"
    local line=""
    if [[ ! -f "${file}" ]]; then
        return 0
    fi
    line="$(grep -E "^${key}=" "${file}" 2>/dev/null | tail -1 || true)"
    if [[ -n "${line}" ]]; then
        printf '%s' "${line#*=}"
    fi
}

is_gdoc_source_dir() {
    local dir="$1"
    [[ -f "${dir}/bot.py" && -f "${dir}/requirements.txt" ]]
}

update_paths() {
    VENV_DIR="${INSTALL_DIR}/venv"
    ENV_FILE="${INSTALL_DIR}/.env"
    DATA_DIR="${INSTALL_DIR}/data"
}

resolve_install_dir() {
    local script_path="${BASH_SOURCE[0]:-}"
    local candidate=""

    if [[ -n "${script_path}" && "${script_path}" != "bash" && "${script_path}" != "-bash" && -f "${script_path}" ]]; then
        candidate="$(cd "$(dirname "${script_path}")" && pwd)"
        if is_gdoc_source_dir "${candidate}"; then
            INSTALL_DIR="${candidate}"
            log_info "مسیر نصب از اسکریپت: ${INSTALL_DIR}"
            return 0
        fi
    fi

    if [[ -n "${INSTALL_DIR:-}" ]]; then
        candidate="${INSTALL_DIR}"
    else
        candidate="${DEFAULT_INSTALL_DIR}"
    fi

    if is_gdoc_source_dir "${candidate}" || [[ -f "${candidate}/.env" || -d "${candidate}/venv" ]]; then
        INSTALL_DIR="${candidate}"
        log_info "مسیر نصب شناسایی شد: ${INSTALL_DIR}"
        return 0
    fi

    if [[ -f "${SERVICE_FILE}" ]]; then
        local from_service=""
        from_service="$(grep -E '^WorkingDirectory=' "${SERVICE_FILE}" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
        if [[ -n "${from_service}" && -d "${from_service}" ]]; then
            INSTALL_DIR="${from_service}"
            log_info "مسیر نصب از سرویس systemd: ${INSTALL_DIR}"
            return 0
        fi
    fi

    log_error "نصب gdoc پیدا نشد."
    log_error "مسیر را مشخص کنید: sudo INSTALL_DIR=/path/to/gdoc bash uninstall.sh"
    exit 1
}

detect_webhook_domain() {
    local url=""
    url="$(read_env_value WEBHOOK_URL "${ENV_FILE}")"
    if [[ -n "${url}" && "${url}" =~ ^https://([^/]+) ]]; then
        printf '%s' "${BASH_REMATCH[1]}"
        return 0
    fi
    return 1
}

stop_and_remove_service() {
    if ! systemctl cat "${SERVICE_NAME}.service" &>/dev/null; then
        log_info "سرویس systemd ${SERVICE_NAME} وجود ندارد — رد شد."
        return 0
    fi

    log_info "توقف و غیرفعال‌سازی سرویس ${SERVICE_NAME}..."
    systemctl stop "${SERVICE_NAME}.service" 2>/dev/null || true
    systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true

    if [[ -f "${SERVICE_FILE}" ]]; then
        rm -f "${SERVICE_FILE}"
        log_info "فایل سرویس حذف شد: ${SERVICE_FILE}"
    fi

    systemctl daemon-reload
    systemctl reset-failed "${SERVICE_NAME}.service" 2>/dev/null || true
}

flush_redis_cache() {
    local prefix="gdoc:"
    if [[ -f "${ENV_FILE}" ]]; then
        local stored_prefix=""
        stored_prefix="$(read_env_value REDIS_PREFIX "${ENV_FILE}")"
        if [[ -n "${stored_prefix}" ]]; then
            prefix="${stored_prefix}"
        fi
    fi

    if ! command -v redis-cli >/dev/null 2>&1; then
        return 0
    fi
    if ! redis-cli ping >/dev/null 2>&1; then
        return 0
    fi

    log_info "پاک‌سازی کش Redis (کلیدهای ${prefix}*)..."
    redis-cli --scan --pattern "${prefix}*" 2>/dev/null \
        | xargs -r -n 100 redis-cli DEL >/dev/null 2>&1 || true
}

remove_nginx_site() {
    local domain="$1"
    local site_available="/etc/nginx/sites-available/gdoc-${domain}"
    local site_enabled="/etc/nginx/sites-enabled/gdoc-${domain}"

    if [[ -f "${site_enabled}" || -L "${site_enabled}" ]]; then
        rm -f "${site_enabled}"
        log_info "حذف nginx enabled: ${site_enabled}"
    fi
    if [[ -f "${site_available}" ]]; then
        rm -f "${site_available}"
        log_info "حذف nginx available: ${site_available}"
    fi
}

remove_nginx_configs() {
    local domain=""
    local found=0

    if [[ "${REMOVE_NGINX}" == "0" ]]; then
        log_info "حذف تنظیمات nginx غیرفعال است — رد شد."
        return 0
    fi

    if ! command -v nginx >/dev/null 2>&1; then
        return 0
    fi

    domain="$(detect_webhook_domain || true)"
    if [[ -n "${domain}" ]]; then
        remove_nginx_site "${domain}"
        found=1
    fi

    # Catch any leftover gdoc-* site files from previous installs.
    shopt -s nullglob
    for site in /etc/nginx/sites-available/gdoc-* /etc/nginx/sites-enabled/gdoc-*; do
        if [[ -e "${site}" ]]; then
            rm -f "${site}"
            log_info "حذف فایل nginx: ${site}"
            found=1
        fi
    done
    shopt -u nullglob

    if [[ "${found}" -eq 1 ]]; then
        if nginx -t >/dev/null 2>&1; then
            systemctl reload nginx 2>/dev/null || true
            log_info "nginx reload شد."
        else
            log_warn "پیکربندی nginx نامعتبر است — reload انجام نشد."
        fi
    fi
}

remove_ssl_renewal_hook() {
    local hook="/etc/letsencrypt/renewal-hooks/deploy/gdoc-nginx-reload.sh"
    if [[ -f "${hook}" ]]; then
        rm -f "${hook}"
        log_info "قلاب تمدید SSL حذف شد: ${hook}"
    fi
}

remove_ssl_certificate() {
    local domain="$1"

    if [[ "${REMOVE_SSL}" != "1" ]]; then
        return 0
    fi
    if ! command -v certbot >/dev/null 2>&1; then
        log_warn "certbot نصب نیست — حذف گواهی SSL رد شد."
        return 0
    fi
    if [[ ! -d "/etc/letsencrypt/live/${domain}" ]]; then
        log_info "گواهی SSL برای ${domain} پیدا نشد — رد شد."
        return 0
    fi

    log_info "حذف گواهی Let's Encrypt برای ${domain}..."
    certbot delete --cert-name "${domain}" --non-interactive 2>/dev/null || {
        log_warn "certbot delete ناموفق بود — ممکن است گواهی قبلاً حذف شده باشد."
    }
}

remove_install_artifacts() {
    if [[ ! -d "${INSTALL_DIR}" ]]; then
        log_info "پوشه نصب وجود ندارد: ${INSTALL_DIR}"
        return 0
    fi

    if [[ "${PURGE}" == "1" ]]; then
        if [[ "${KEEP_DATA}" == "1" && -d "${DATA_DIR}" ]]; then
            local backup_dir=""
            backup_dir="$(mktemp -d "/tmp/gdoc-data-backup.XXXXXX")"
            log_info "نگه‌داشتن data/ در ${backup_dir}..."
            cp -a "${DATA_DIR}/." "${backup_dir}/"
            rm -rf "${INSTALL_DIR}"
            mkdir -p "${DATA_DIR}"
            cp -a "${backup_dir}/." "${DATA_DIR}/"
            rm -rf "${backup_dir}"
            log_info "کل پوشه نصب حذف شد (به‌جز data/ که در ${DATA_DIR} باقی ماند)."
        else
            rm -rf "${INSTALL_DIR}"
            log_info "کل پوشه نصب حذف شد: ${INSTALL_DIR}"
        fi
        return 0
    fi

    if [[ -d "${VENV_DIR}" ]]; then
        rm -rf "${VENV_DIR}"
        log_info "محیط مجازی حذف شد: ${VENV_DIR}"
    fi

    if [[ -f "${ENV_FILE}" ]]; then
        rm -f "${ENV_FILE}"
        log_info "فایل .env حذف شد: ${ENV_FILE}"
    fi

    if [[ "${KEEP_DATA}" != "1" && -d "${DATA_DIR}" ]]; then
        rm -rf "${DATA_DIR}"
        log_info "پوشه data/ (دیتابیس) حذف شد: ${DATA_DIR}"
    elif [[ -d "${DATA_DIR}" ]]; then
        log_info "پوشه data/ حفظ شد: ${DATA_DIR}"
    fi

    find "${INSTALL_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
}

remove_system_packages_optional() {
    if [[ "${REMOVE_SYSTEM_PACKAGES}" != "1" ]]; then
        return 0
    fi

    log_warn "حذف بسته‌های سیستمی — ممکن است سرویس‌های دیگر را تحت تأثیر قرار دهد."
    if ! confirm "آیا مطمئن هستید بسته‌های redis/nginx/certbot حذف شوند؟"; then
        log_info "حذف بسته‌های سیستمی لغو شد."
        return 0
    fi

    if command -v apt-get >/dev/null 2>&1; then
        apt-get remove -y --purge redis-server nginx certbot python3-certbot-nginx 2>/dev/null || true
        apt-get autoremove -y 2>/dev/null || true
    elif command -v dnf >/dev/null 2>&1; then
        dnf remove -y redis nginx certbot python3-certbot-nginx 2>/dev/null || true
    elif command -v yum >/dev/null 2>&1; then
        yum remove -y redis nginx certbot python3-certbot-nginx 2>/dev/null || true
    else
        log_warn "مدیر بسته ناشناخته — حذف دستی لازم است."
    fi
}

collect_uninstall_options() {
    local domain=""

    if [[ -z "${REMOVE_NGINX}" ]]; then
        domain="$(detect_webhook_domain || true)"
        if [[ -n "${domain}" ]] || ls /etc/nginx/sites-available/gdoc-* &>/dev/null; then
            REMOVE_NGINX="1"
        else
            REMOVE_NGINX="0"
        fi
    fi

    if [[ "${YES}" == "1" ]]; then
        return 0
    fi

    echo
    log_info "--- تأیید حذف gdoc ---"
    echo "مسیر نصب:     ${INSTALL_DIR}"
    echo "سرویس:         ${SERVICE_NAME}"
    if [[ -d "${DATA_DIR}" ]]; then
        echo "دیتابیس:       ${DATA_DIR}"
    fi
    domain="$(detect_webhook_domain || true)"
    if [[ -n "${domain}" ]]; then
        echo "دامنه وب‌هوک:  ${domain}"
    fi
    echo

    if ! confirm "آیا gdoc حذف شود؟"; then
        log_info "عملیات لغو شد."
        exit 0
    fi

    if [[ "${PURGE}" != "1" && "${KEEP_DATA}" == "1" ]]; then
        log_info "دیتابیس (data/) حفظ می‌شود."
    elif [[ "${PURGE}" != "1" ]]; then
        if confirm "آیا پوشه data/ (دیتابیس SQLite) هم حذف شود؟" 1; then
            KEEP_DATA="0"
        fi
    fi

    if [[ "${REMOVE_SSL}" != "1" && -n "${domain}" && -d "/etc/letsencrypt/live/${domain}" ]]; then
        if confirm "آیا گواهی SSL (${domain}) هم حذف شود؟" 1; then
            REMOVE_SSL="1"
        fi
    fi

    if [[ "${PURGE}" != "1" ]]; then
        if confirm "آیا کل پوشه نصب (${INSTALL_DIR}) حذف شود؟ (PURGE)" 1; then
            PURGE="1"
        fi
    fi
}

print_summary() {
    echo
    log_info "=========================================="
    log_info " gdoc (Group Doctor) uninstall complete"
    log_info "=========================================="
    echo
    if [[ "${PURGE}" == "1" ]]; then
        echo "پوشه نصب:      حذف شد"
    else
        echo "پوشه نصب:      ${INSTALL_DIR} (سورس باقی ماند)"
        if [[ "${KEEP_DATA}" == "1" && -d "${DATA_DIR}" ]]; then
            echo "دیتابیس:       ${DATA_DIR} (حفظ شد)"
        fi
    fi
    echo "سرویس:         ${SERVICE_NAME} (حذف شد)"
    echo
    echo "نصب مجدد:"
    echo "  curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh | sudo bash"
    echo
    echo "حذف کامل بدون پرسش:"
    echo "  sudo YES=1 PURGE=1 bash uninstall.sh"
    echo
}

main() {
    echo "=========================================="
    echo " gdoc — Group Doctor Moderator Bot Uninstaller"
    echo "=========================================="
    echo
    echo "حذف از گیت‌هاب:"
    echo "  curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/uninstall.sh | sudo bash"
    echo

    require_root
    resolve_install_dir
    update_paths
    collect_uninstall_options

    stop_and_remove_service
    flush_redis_cache

    local domain=""
    domain="$(detect_webhook_domain || true)"
    remove_nginx_configs
    remove_ssl_renewal_hook
    if [[ -n "${domain}" ]]; then
        remove_ssl_certificate "${domain}"
    fi

    remove_install_artifacts
    remove_system_packages_optional
    print_summary
}

main "$@"
