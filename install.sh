#!/usr/bin/env bash
# gdoc (Group Doctor) — Telegram Group Moderator Bot installer
set -euo pipefail

APP_NAME="gdoc"
SERVICE_NAME="tg_moderator"
GITHUB_REPO="https://github.com/Noctis-Architect/gdoc.git"
GIT_BRANCH="${GIT_BRANCH:-main}"
CLONE_TARGET_DIR="/opt/gdoc"

INSTALL_DIR=""
VENV_DIR=""
ENV_FILE=""
DATA_DIR=""
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
if [[ -n "${SUDO_USER:-}" ]]; then
    CURRENT_USER="${SUDO_USER}"
else
    CURRENT_USER="$(whoami)"
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

require_root_for_systemd() {
    if [[ "${EUID}" -ne 0 ]]; then
        log_warn "System packages and systemd setup require root privileges."
        log_warn "Re-run with: sudo bash install.sh"
        exit 1
    fi
}

prompt_read() {
    # When piped (curl | bash), stdin is the script — read prompts from the terminal.
    local _input=""
    if [[ -t 0 ]]; then
        read -r "$@" _input || true
    elif [[ -r /dev/tty ]]; then
        read -r "$@" _input </dev/tty || true
    else
        log_error "No interactive terminal available."
        log_error "Download and run instead:"
        log_error "  curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh -o /tmp/gdoc-install.sh"
        log_error "  sudo bash /tmp/gdoc-install.sh"
        exit 1
    fi
    printf '%s' "${_input}"
}

prompt_value() {
    local var_name="$1"
    local prompt_text="$2"
    local default_value="${3:-}"
    local input=""
    if [[ -n "${default_value}" ]]; then
        input="$(prompt_read -p "${prompt_text} [${default_value}]: ")"
        input="${input:-${default_value}}"
    else
        while [[ -z "${input}" ]]; do
            input="$(prompt_read -p "${prompt_text}: ")"
            if [[ -z "${input}" ]]; then
                log_error "This value is required."
            fi
        done
    fi
    printf -v "${var_name}" '%s' "${input}"
}

validate_super_admin_id() {
    local id="$1"
    if [[ ! "${id}" =~ ^[0-9]+$ ]]; then
        log_error "شناسه سوپرادمین باید عددی باشد (از @userinfobot بگیرید)."
        return 1
    fi
    return 0
}

collect_config() {
    USE_WEBHOOK="${USE_WEBHOOK:-false}"
    WEBHOOK_DOMAIN="${WEBHOOK_DOMAIN:-}"
    SSL_EMAIL="${SSL_EMAIL:-}"
    CF_API_TOKEN="${CF_API_TOKEN:-}"

    if [[ -n "${BOT_TOKEN:-}" && -n "${SUPER_ADMIN_ID:-}" ]]; then
        log_info "تنظیمات از متغیرهای محیطی خوانده شد."
        if ! validate_super_admin_id "${SUPER_ADMIN_ID}"; then
            exit 1
        fi
        if [[ "${USE_WEBHOOK}" == "true" && -n "${WEBHOOK_DOMAIN}" ]]; then
            WEBHOOK_URL="https://${WEBHOOK_DOMAIN}"
        else
            WEBHOOK_URL=""
            USE_WEBHOOK="false"
        fi
        return 0
    fi

    echo
    log_info "--- تنظیمات ربات ---"
    prompt_value BOT_TOKEN "توکن ربات تلگرام (از @BotFather)"
    while true; do
        prompt_value SUPER_ADMIN_ID "شناسه عددی سوپرادمین (از @userinfobot)"
        if validate_super_admin_id "${SUPER_ADMIN_ID}"; then
            break
        fi
    done

    echo
    log_info "--- دامنه و SSL (Webhook) ---"
    log_info "تنظیمات AI (Base URL و کلید API) بعداً از پنل /superadmin در تلگرام انجام می‌شود."
    prompt_value USE_WEBHOOK "از دامنه با SSL استفاده شود؟ (true/false)" "true"

    if [[ "${USE_WEBHOOK}" == "true" ]]; then
        prompt_value WEBHOOK_DOMAIN "دامنه وب‌هوک (مثال: bot.example.com)"
        prompt_value SSL_EMAIL "ایمیل برای گواهی SSL (Let's Encrypt)"
        prompt_value USE_CLOUDFLARE "دامنه روی Cloudflare است؟ (true/false)" "true"
        if [[ "${USE_CLOUDFLARE}" == "true" ]]; then
            prompt_value CF_API_TOKEN "توکن API کلادفلر (دسترسی Zone:DNS:Edit)"
            log_info "SSL با DNS challenge کلادفلر برای ${WEBHOOK_DOMAIN} صادر می‌شود."
        else
            CF_API_TOKEN=""
            log_info "SSL با HTTP challenge برای ${WEBHOOK_DOMAIN} صادر می‌شود."
            log_warn "رکورد A دامنه باید به IP همین سرور اشاره کند."
        fi
        WEBHOOK_URL="https://${WEBHOOK_DOMAIN}"
    else
        WEBHOOK_DOMAIN=""
        WEBHOOK_URL=""
        SSL_EMAIL=""
        CF_API_TOKEN=""
        log_warn "حالت Polling — برای production توصیه می‌شود دامنه فعال باشد."
    fi
}

is_gdoc_source_dir() {
    local dir="$1"
    [[ -f "${dir}/bot.py" && -f "${dir}/requirements.txt" ]]
}

resolve_install_dir() {
    local script_path="${BASH_SOURCE[0]:-}"
    local candidate=""

    if [[ -n "${script_path}" && "${script_path}" != "bash" && "${script_path}" != "-bash" && -f "${script_path}" ]]; then
        candidate="$(cd "$(dirname "${script_path}")" && pwd)"
        if is_gdoc_source_dir "${candidate}"; then
            INSTALL_DIR="${candidate}"
            log_info "Using existing source at ${INSTALL_DIR}"
            return 0
        fi
    fi

    if [[ -n "${INSTALL_DIR:-}" ]]; then
        candidate="${INSTALL_DIR}"
    else
        candidate="${CLONE_TARGET_DIR}"
    fi

    if is_gdoc_source_dir "${candidate}"; then
        INSTALL_DIR="${candidate}"
        log_info "Using existing installation at ${INSTALL_DIR}"
        return 0
    fi

    if [[ -d "${candidate}" ]]; then
        log_error "Directory ${candidate} exists but is not a valid gdoc source tree."
        log_error "Remove it, choose another path with INSTALL_DIR=/path, or clone manually:"
        log_error "  git clone ${GITHUB_REPO} ${candidate}"
        exit 1
    fi

    if ! command -v git >/dev/null 2>&1; then
        log_error "git is required to clone from GitHub. Install git and re-run."
        exit 1
    fi

    log_info "Cloning gdoc from GitHub..."
    log_info "  Repository: ${GITHUB_REPO}"
    log_info "  Branch:     ${GIT_BRANCH}"
    log_info "  Target:     ${candidate}"

    mkdir -p "$(dirname "${candidate}")"
    git clone --depth 1 --branch "${GIT_BRANCH}" "${GITHUB_REPO}" "${candidate}"
    INSTALL_DIR="${candidate}"
    chmod +x "${INSTALL_DIR}/install.sh" 2>/dev/null || true
}

update_paths() {
    VENV_DIR="${INSTALL_DIR}/venv"
    ENV_FILE="${INSTALL_DIR}/.env"
    DATA_DIR="${INSTALL_DIR}/data"
}

install_system_packages() {
    log_info "Updating system packages..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -y
        apt-get install -y python3 python3-pip python3-venv redis-server curl git
        systemctl enable redis-server
        systemctl start redis-server
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y python3 python3-pip redis curl git
        systemctl enable redis
        systemctl start redis
    elif command -v yum >/dev/null 2>&1; then
        yum install -y python3 python3-pip redis curl git
        systemctl enable redis
        systemctl start redis
    else
        log_warn "Unknown package manager. Ensure Python 3.10+, pip, venv, git, and Redis are installed."
    fi
}

setup_venv() {
    log_info "Creating Python virtual environment..."
    python3 -m venv "${VENV_DIR}"
    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"
    pip install --upgrade pip wheel
    pip install -r "${INSTALL_DIR}/requirements.txt"
    deactivate
}

write_env_file() {
    local bot_token="$1"
    local super_admin_id="$2"
    local use_webhook="$3"
    local webhook_url="$4"

    mkdir -p "${DATA_DIR}"

    cat > "${ENV_FILE}" <<EOF
BOT_TOKEN=${bot_token}
SUPER_ADMIN_ID=${super_admin_id}
# AI settings: configure via /superadmin panel in Telegram (super admin only)
DB_BACKEND=sqlite
DATABASE_URL=sqlite:///${DATA_DIR}/gdoc.db
REDIS_URL=redis://localhost:6379/0
USE_WEBHOOK=${use_webhook}
WEBHOOK_URL=${webhook_url}
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8443
WEBHOOK_PATH=/webhook
LOG_LEVEL=INFO
DATA_DIR=${DATA_DIR}
EOF

    chmod 600 "${ENV_FILE}"
    log_info "Environment file written to ${ENV_FILE}"
}

create_systemd_service() {
    log_info "Creating systemd service at ${SERVICE_FILE}..."

    cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=gdoc Telegram Group Moderator Bot (Group Doctor)
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/bot.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

# Hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}.service"
    systemctl restart "${SERVICE_NAME}.service"
}

setup_webhook_ssl() {
    local domain="$1"
    local email="$2"
    local cf_token="${3:-}"
    local ssl_script="${INSTALL_DIR}/scripts/setup_webhook_ssl.sh"

    if [[ ! -f "${ssl_script}" ]]; then
        log_error "SSL setup script not found: ${ssl_script}"
        exit 1
    fi

    chmod +x "${ssl_script}"
    log_info "Setting up nginx + SSL for ${domain}..."
    bash "${ssl_script}" "${domain}" "${email}" "${cf_token}" 8443 /webhook
}

print_summary() {
    echo
    log_info "=========================================="
    log_info " gdoc (Group Doctor) installation complete"
    log_info "=========================================="
    echo
    echo "Install dir: ${INSTALL_DIR}"
    echo "Service:     ${SERVICE_NAME}"
    echo "Status:      systemctl status ${SERVICE_NAME}"
    echo "Logs:        journalctl -u ${SERVICE_NAME} -f"
    echo "Restart:     sudo systemctl restart ${SERVICE_NAME}"
    echo
    echo "Bot commands:"
    echo "  /start       — Welcome"
    echo "  /panel       — Group admin panel (in groups)"
    echo "  /superadmin  — Owner control panel"
    echo
    echo "Next steps:"
    echo "  1. Send /superadmin to the bot in private chat"
    echo "  2. Configure AI provider, API key, and model from the panel"
    echo "  3. Add the bot to your Telegram group and promote to admin"
    echo "  4. Run /panel in the group to configure moderation"
    if [[ "${USE_WEBHOOK:-false}" == "true" && -n "${WEBHOOK_DOMAIN:-}" ]]; then
        echo
        echo "Webhook: https://${WEBHOOK_DOMAIN}/webhook (SSL active)"
    fi
    echo
}

main() {
    echo "=========================================="
    echo " gdoc — Group Doctor Moderator Bot Installer"
    echo "=========================================="
    echo
    echo "نصب از گیت‌هاب:"
    echo "  curl -fsSL https://raw.githubusercontent.com/Noctis-Architect/gdoc/main/install.sh | sudo bash"
    echo

    require_root_for_systemd
    resolve_install_dir
    update_paths
    install_system_packages

    BOT_TOKEN="${BOT_TOKEN:-}"
    SUPER_ADMIN_ID="${SUPER_ADMIN_ID:-}"

    collect_config

    setup_venv
    write_env_file "${BOT_TOKEN}" "${SUPER_ADMIN_ID}" "${USE_WEBHOOK}" "${WEBHOOK_URL}"

    if [[ "${USE_WEBHOOK}" == "true" && -n "${WEBHOOK_DOMAIN}" && -n "${SSL_EMAIL}" ]]; then
        setup_webhook_ssl "${WEBHOOK_DOMAIN}" "${SSL_EMAIL}" "${CF_API_TOKEN:-}"
    fi

    create_systemd_service
    print_summary
}

main "$@"
