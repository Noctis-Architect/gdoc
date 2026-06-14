#!/usr/bin/env bash
# Setup nginx reverse proxy + Let's Encrypt SSL for gdoc webhook
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
CF_TOKEN="${3:-}"
LOCAL_PORT="${4:-8443}"
WEBHOOK_PATH="${5:-/webhook}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

if [[ "${EUID}" -ne 0 ]]; then
    log_error "This script must be run as root."
    exit 1
fi

if [[ -z "${DOMAIN}" || -z "${EMAIL}" ]]; then
    log_error "Usage: setup_webhook_ssl.sh <domain> <email> [cloudflare_api_token] [local_port] [webhook_path]"
    exit 1
fi

install_packages() {
    log_info "Installing nginx and certbot..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -y
        apt-get install -y nginx certbot
        if [[ -n "${CF_TOKEN}" ]]; then
            apt-get install -y python3-certbot-dns-cloudflare || {
                log_warn "certbot-dns-cloudflare not in repos, installing via pip..."
                apt-get install -y python3-pip
                pip3 install certbot-dns-cloudflare --break-system-packages 2>/dev/null \
                    || pip3 install certbot-dns-cloudflare
            }
        else
            apt-get install -y python3-certbot-nginx || true
        fi
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y nginx certbot
        if [[ -n "${CF_TOKEN}" ]]; then
            dnf install -y python3-certbot-dns-cloudflare || pip3 install certbot-dns-cloudflare
        else
            dnf install -y python3-certbot-nginx || true
        fi
    else
        log_error "Unsupported package manager. Install nginx and certbot manually."
        exit 1
    fi
}

write_nginx_config() {
    local ssl_cert="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
    local ssl_key="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"

    if [[ -f "${ssl_cert}" ]]; then
        cat > "/etc/nginx/sites-available/gdoc-${DOMAIN}" <<EOF
server {
    listen 80;
    server_name ${DOMAIN};
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name ${DOMAIN};

    ssl_certificate ${ssl_cert};
    ssl_certificate_key ${ssl_key};
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location ${WEBHOOK_PATH} {
        proxy_pass http://127.0.0.1:${LOCAL_PORT}${WEBHOOK_PATH};
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
        cat > "/etc/nginx/sites-available/gdoc-${DOMAIN}" <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location ${WEBHOOK_PATH} {
        proxy_pass http://127.0.0.1:${LOCAL_PORT}${WEBHOOK_PATH};
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
    ln -sf "/etc/nginx/sites-available/gdoc-${DOMAIN}" "/etc/nginx/sites-enabled/gdoc-${DOMAIN}"
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
    nginx -t
    systemctl enable nginx
    systemctl restart nginx
}

obtain_certificate() {
    log_info "Obtaining SSL certificate for ${DOMAIN}..."

    if [[ -n "${CF_TOKEN}" ]]; then
        log_info "Using Cloudflare DNS challenge..."
        mkdir -p /etc/letsencrypt
        cat > /etc/letsencrypt/cloudflare.ini <<EOF
dns_cloudflare_api_token = ${CF_TOKEN}
EOF
        chmod 600 /etc/letsencrypt/cloudflare.ini

        certbot certonly \
            --dns-cloudflare \
            --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
            --dns-cloudflare-propagation-seconds 30 \
            -d "${DOMAIN}" \
            --email "${EMAIL}" \
            --agree-tos \
            --non-interactive \
            --no-eff-email
    else
        log_info "Using HTTP challenge (ensure ${DOMAIN} points to this server)..."
        certbot certonly \
            --nginx \
            -d "${DOMAIN}" \
            --email "${EMAIL}" \
            --agree-tos \
            --non-interactive \
            --no-eff-email
    fi
}

setup_auto_renewal() {
    systemctl enable certbot.timer 2>/dev/null || true
    systemctl start certbot.timer 2>/dev/null || true

    cat > /etc/letsencrypt/renewal-hooks/deploy/gdoc-nginx-reload.sh <<'HOOK'
#!/bin/bash
nginx -t && systemctl reload nginx
HOOK
    chmod +x /etc/letsencrypt/renewal-hooks/deploy/gdoc-nginx-reload.sh
}

main() {
    log_info "Setting up webhook SSL for ${DOMAIN}..."

    if [[ ! "${DOMAIN}" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]]; then
        log_error "Invalid domain: ${DOMAIN}"
        exit 1
    fi

    install_packages
    write_nginx_config
    obtain_certificate
    write_nginx_config
    systemctl reload nginx
    setup_auto_renewal

    log_info "SSL setup complete!"
    log_info "Webhook URL: https://${DOMAIN}${WEBHOOK_PATH}"
    echo
    echo "Make sure:"
    echo "  - DNS A record for ${DOMAIN} points to this server"
    if [[ -n "${CF_TOKEN}" ]]; then
        echo "  - Cloudflare proxy (orange cloud) is OK with Full (strict) SSL mode"
    else
        echo "  - Port 80 and 443 are open in firewall"
    fi
}

main "$@"
