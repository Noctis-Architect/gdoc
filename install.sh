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
CURRENT_USER="$(whoami)"

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

prompt_value() {
    local var_name="$1"
    local prompt_text="$2"
    local default_value="${3:-}"
    local input=""
    if [[ -n "${default_value}" ]]; then
        read -r -p "${prompt_text} [${default_value}]: " input
        input="${input:-${default_value}}"
    else
        while [[ -z "${input}" ]]; do
            read -r -p "${prompt_text}: " input
            if [[ -z "${input}" ]]; then
                log_error "This value is required."
            fi
        done
    fi
    printf -v "${var_name}" '%s' "${input}"
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
    local ai_provider="$3"
    local ai_api_key="$4"
    local ai_model="$5"
    local use_webhook="$6"
    local webhook_url="$7"

    mkdir -p "${DATA_DIR}"

    cat > "${ENV_FILE}" <<EOF
BOT_TOKEN=${bot_token}
SUPER_ADMIN_ID=${super_admin_id}
AI_PROVIDER=${ai_provider}
AI_API_KEY=${ai_api_key}
AI_MODEL=${ai_model}
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
    echo "  1. Add the bot to your Telegram group"
    echo "  2. Promote the bot to administrator"
    echo "  3. Run /panel in the group to configure moderation"
    echo
}

main() {
    echo "=========================================="
    echo " gdoc — Group Doctor Moderator Bot Installer"
    echo "=========================================="
    echo

    require_root_for_systemd
    resolve_install_dir
    update_paths
    install_system_packages

    local BOT_TOKEN=""
    local SUPER_ADMIN_ID=""
    local AI_PROVIDER=""
    local AI_API_KEY=""
    local AI_MODEL=""
    local USE_WEBHOOK=""
    local WEBHOOK_URL=""

    prompt_value BOT_TOKEN "Enter Telegram Bot Token (from @BotFather)"
    prompt_value SUPER_ADMIN_ID "Enter Super Admin Telegram Numeric ID"
    prompt_value AI_PROVIDER "AI Provider (openai/gemini)" "openai"
    prompt_value AI_API_KEY "Enter OpenAI/Gemini API Key"

    if [[ "${AI_PROVIDER}" == "gemini" ]]; then
        prompt_value AI_MODEL "Gemini model name" "gemini-1.5-flash"
    else
        prompt_value AI_MODEL "OpenAI model name" "gpt-4o-mini"
    fi

    prompt_value USE_WEBHOOK "Use webhook mode? (true/false)" "false"
    if [[ "${USE_WEBHOOK}" == "true" ]]; then
        prompt_value WEBHOOK_URL "Public webhook URL (https://your-domain.com)"
    fi

    setup_venv
    write_env_file "${BOT_TOKEN}" "${SUPER_ADMIN_ID}" "${AI_PROVIDER}" "${AI_API_KEY}" "${AI_MODEL}" "${USE_WEBHOOK}" "${WEBHOOK_URL}"
    create_systemd_service
    print_summary
}

main "$@"
