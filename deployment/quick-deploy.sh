#!/bin/bash

# Grounded - Quick Deployment Script for Lightsail
# This script automates the entire deployment process

set -e

echo "=================================="
echo "Grounded Quick Deployment"
echo "=================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}Step 1: Installing system dependencies...${NC}"
apt update -qq
apt install -y python3.11 python3.11-venv python3-pip postgresql postgresql-contrib git curl > /dev/null 2>&1

echo -e "${GREEN}Step 2: Setting up PostgreSQL...${NC}"
systemctl start postgresql
systemctl enable postgresql

# Create database and user
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = 'grounded'" | grep -q 1 || \
sudo -u postgres psql -c "CREATE DATABASE grounded;"

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname = 'grounded'" | grep -q 1 || \
sudo -u postgres psql -c "CREATE USER grounded WITH PASSWORD 'grounded2024';"

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE grounded TO grounded;" > /dev/null 2>&1
sudo -u postgres psql -c "ALTER DATABASE grounded OWNER TO grounded;" > /dev/null 2>&1
sudo -u postgres psql -d grounded -c "GRANT ALL ON SCHEMA public TO grounded;" > /dev/null 2>&1

echo -e "${GREEN}Step 3: Creating deployer user...${NC}"
id -u deployer &>/dev/null || useradd -m -s /bin/bash deployer

echo -e "${GREEN}Step 4: Creating application directories...${NC}"
mkdir -p /opt/grounded/app
mkdir -p /opt/grounded/data/uploads
mkdir -p /opt/grounded/backups
mkdir -p /var/log/grounded
mkdir -p /etc/grounded

chown -R deployer:deployer /opt/grounded
chown -R deployer:deployer /var/log/grounded

echo -e "${GREEN}Step 5: Cloning repository...${NC}"
if [ -d "/opt/grounded/app/.git" ]; then
    echo "Repository already exists, pulling latest..."
    cd /opt/grounded/app
    sudo -u deployer git pull
else
    rm -rf /opt/grounded/app/*
    sudo -u deployer git clone https://github.com/pauldevelopai/aitools.git /opt/grounded/app
fi

echo -e "${GREEN}Step 6: Setting up Python environment...${NC}"
cd /opt/grounded/app

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    sudo -u deployer python3.11 -m venv venv
fi

# Install dependencies
sudo -u deployer /opt/grounded/app/venv/bin/pip install --upgrade pip -q
sudo -u deployer /opt/grounded/app/venv/bin/pip install -r requirements.txt -q
sudo -u deployer /opt/grounded/app/venv/bin/pip install slowapi -q

echo -e "${GREEN}Step 7: Generating secure keys...${NC}"
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
CSRF_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

echo -e "${GREEN}Step 8: Creating .env file...${NC}"
cat > /etc/grounded/.env << EOF
# Environment
ENV=prod

# Database
DATABASE_URL=postgresql://grounded:grounded2024@localhost:5432/grounded

# Security
SECRET_KEY=${SECRET_KEY}
CSRF_SECRET_KEY=${CSRF_SECRET_KEY}

# OpenAI API Key (UPDATE THIS!)
OPENAI_API_KEY=sk-update-me-with-your-key

# Embedding Settings
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-ada-002
EMBEDDING_DIMENSIONS=1536

# Cookie Settings
SESSION_COOKIE_NAME=grounded_session
SESSION_MAX_AGE=2592000
COOKIE_HTTPONLY=true
COOKIE_SECURE=true
COOKIE_SAMESITE=lax

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_AUTH_REQUESTS=5
RATE_LIMIT_AUTH_WINDOW=60
RATE_LIMIT_RAG_REQUESTS=20
RATE_LIMIT_RAG_WINDOW=60

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/var/log/grounded/app.log

# Paths
UPLOAD_DIR=/opt/grounded/data/uploads
EOF

chown deployer:deployer /etc/grounded/.env
chmod 640 /etc/grounded/.env

echo -e "${GREEN}Step 9: Running database migrations...${NC}"
cd /opt/grounded/app
export $(grep -v '^#' /etc/grounded/.env | xargs)
sudo -u deployer -E /opt/grounded/app/venv/bin/alembic upgrade head

echo -e "${GREEN}Step 10: Installing Caddy web server...${NC}"
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update -qq
apt install -y caddy > /dev/null 2>&1

echo -e "${GREEN}Step 11: Configuring Caddy...${NC}"
cat > /etc/caddy/Caddyfile << 'EOF'
{
    # Global options
    admin off
}

:80 {
    # Health check endpoint
    handle /health {
        reverse_proxy localhost:8000
    }

    # Main application
    handle {
        reverse_proxy localhost:8000 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    # Security headers
    header {
        X-Frame-Options "SAMEORIGIN"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    # Logging
    log {
        output file /var/log/caddy/access.log
        format json
    }
}
EOF

systemctl enable caddy
systemctl restart caddy

echo -e "${GREEN}Step 12: Creating systemd service...${NC}"
cat > /etc/systemd/system/grounded.service << 'EOF'
[Unit]
Description=Grounded FastAPI Application
After=network.target postgresql.service

[Service]
Type=simple
User=deployer
Group=deployer
WorkingDirectory=/opt/grounded/app
EnvironmentFile=/etc/grounded/.env
ExecStart=/opt/grounded/app/venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 2 \
    --log-level info

Restart=always
RestartSec=10
StandardOutput=append:/var/log/grounded/app.log
StandardError=append:/var/log/grounded/error.log

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/grounded/data /var/log/grounded

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable grounded
systemctl restart grounded

echo ""
echo -e "${GREEN}Step 13: Configuring firewall...${NC}"
ufw --force enable
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw reload

echo ""
echo -e "${GREEN}=================================="
echo "Deployment Complete! ✅"
echo "==================================${NC}"
echo ""
echo "Your Grounded application is now running!"
echo ""
echo -e "${YELLOW}Access your application:${NC}"
echo "  http://$(curl -s ifconfig.me)"
echo ""
echo -e "${YELLOW}Service commands:${NC}"
echo "  Status:  sudo systemctl status grounded"
echo "  Logs:    sudo journalctl -u grounded -f"
echo "  Restart: sudo systemctl restart grounded"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT - Update your OpenAI API key:${NC}"
echo "  sudo nano /etc/grounded/.env"
echo "  Then restart: sudo systemctl restart grounded"
echo ""
echo -e "${YELLOW}Create your first admin user:${NC}"
echo "  Visit: http://$(curl -s ifconfig.me)/register"
echo ""
echo -e "${GREEN}✅ Deployment successful!${NC}"
