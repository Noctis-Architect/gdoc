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
        WEBHOOK_URL="https://${WEBHOOK_DOMAIN}"
        log_info "SSL خودکار با Let's Encrypt (فقط دامنه + ایمیل لازم است)."
        log_warn "قبل از ادامه: رکورد A دامنه باید به IP همین سرور اشاره کند."
        log_warn "اگر Cloudflare دارید، موقتاً پروکسی (ابر نارنجی) را خاموش کنید."
    else
        WEBHOOK_DOMAIN=""
        WEBHOOK_URL=""
        SSL_EMAIL=""
        log_warn "حالت Polling — برای production توصیه می‌شود دامنه فعال باشد."
    fi
}

is_gdoc_source_dir() {
    local dir="$1"
    [[ -f "${dir}/bot.py" && -f "${dir}/requirements.txt" ]]
}

sync_install_dir() {
    local dir="$1"
    if [[ ! -d "${dir}/.git" ]]; then
        return 0
    fi

    log_info "به‌روزرسانی نصب موجود از گیت‌هاب..."
    if git -C "${dir}" fetch --depth 1 origin "${GIT_BRANCH}" 2>/dev/null \
        && git -C "${dir}" checkout "${GIT_BRANCH}" 2>/dev/null \
        && git -C "${dir}" reset --hard "origin/${GIT_BRANCH}" 2>/dev/null; then
        log_info "نصب موجود به‌روز شد."
    else
        log_warn "git pull ناموفق بود؛ فایل‌های گم‌شده به‌صورت دستی دانلود می‌شوند."
    fi
}

finalize_install_dir() {
    sync_install_dir "${INSTALL_DIR}"
}

resolve_install_dir() {
    local script_path="${BASH_SOURCE[0]:-}"
    local candidate=""

    if [[ -n "${script_path}" && "${script_path}" != "bash" && "${script_path}" != "-bash" && -f "${script_path}" ]]; then
        candidate="$(cd "$(dirname "${script_path}")" && pwd)"
        if is_gdoc_source_dir "${candidate}"; then
            INSTALL_DIR="${candidate}"
            log_info "Using existing source at ${INSTALL_DIR}"
            finalize_install_dir
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
        finalize_install_dir
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
    finalize_install_dir
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

install_ssl_packages() {
    log_info "نصب nginx و certbot..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -y
        apt-get install -y nginx certbot python3-certbot-nginx
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y nginx certbot python3-certbot-nginx || dnf install -y nginx certbot
    elif command -v yum >/dev/null 2>&1; then
        yum install -y nginx certbot python3-certbot-nginx || yum install -y nginx certbot
    else
        log_error "مدیر بسته ناشناخته — nginx و certbot را دستی نصب کنید."
        exit 1
    fi
}

write_nginx_config() {
    local domain="$1"
    local local_port="$2"
    local webhook_path="$3"
    local ssl_cert="/etc/letsencrypt/live/${domain}/fullchain.pem"
    local ssl_key="/etc/letsencrypt/live/${domain}/privkey.pem"
    local site_file="/etc/nginx/sites-available/gdoc-${domain}"

    if [[ -f "${ssl_cert}" ]]; then
        cat > "${site_file}" <<EOF
server {
    listen 80;
    server_name ${domain};
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name ${domain};

    ssl_certificate ${ssl_cert};
    ssl_certificate_key ${ssl_key};
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location ${webhook_path} {
        proxy_pass http://127.0.0.1:${local_port}${webhook_path};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        return 404;
    }
}
EOF
    else
        cat > "${site_file}" <<EOF
server {
    listen 80;
    server_name ${domain};

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location ${webhook_path} {
        proxy_pass http://127.0.0.1:${local_port}${webhook_path};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        return 404;
    }
}
EOF
    fi

    mkdir -p /etc/nginx/sites-enabled
    ln -sf "${site_file}" "/etc/nginx/sites-enabled/gdoc-${domain}"
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
    nginx -t
    systemctl enable nginx
    systemctl restart nginx
}

obtain_ssl_certificate() {
    local domain="$1"
    local email="$2"

    log_info "دریافت گواهی SSL برای ${domain} (Let's Encrypt HTTP)..."
    certbot certonly \
        --nginx \
        -d "${domain}" \
        --email "${email}" \
        --agree-tos \
        --non-interactive \
        --no-eff-email
}

setup_ssl_renewal() {
    systemctl enable certbot.timer 2>/dev/null || true
    systemctl start certbot.timer 2>/dev/null || true

    mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    cat > /etc/letsencrypt/renewal-hooks/deploy/gdoc-nginx-reload.sh <<'HOOK'
#!/bin/bash
nginx -t && systemctl reload nginx
HOOK
    chmod +x /etc/letsencrypt/renewal-hooks/deploy/gdoc-nginx-reload.sh
}

setup_webhook_ssl() {
    local domain="$1"
    local email="$2"
    local local_port="8443"
    local webhook_path="/webhook"

    if [[ ! "${domain}" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]]; then
        log_error "دامنه نامعتبر: ${domain}"
        exit 1
    fi

    log_info "راه‌اندازی nginx + SSL برای ${domain}..."
    install_ssl_packages
    write_nginx_config "${domain}" "${local_port}" "${webhook_path}"
    obtain_ssl_certificate "${domain}" "${email}"
    write_nginx_config "${domain}" "${local_port}" "${webhook_path}"
    systemctl reload nginx
    setup_ssl_renewal

    log_info "SSL فعال شد: https://${domain}${webhook_path}"
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
        setup_webhook_ssl "${WEBHOOK_DOMAIN}" "${SSL_EMAIL}"
    fi

    create_systemd_service
    print_summary
}

main "$@"
