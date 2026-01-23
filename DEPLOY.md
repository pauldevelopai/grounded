# Production Deployment Guide - No Docker

This guide provides step-by-step instructions for deploying ToolkitRAG on a production VPS without Docker.

## Table of Contents
1. [Create Lightsail Instance](#1-create-lightsail-instance)
2. [Secure SSH Access](#2-secure-ssh-access)
3. [Install System Dependencies](#3-install-system-dependencies)
4. [Setup PostgreSQL](#4-setup-postgresql)
5. [Clone and Configure Application](#5-clone-and-configure-application)
6. [Run Database Migrations](#6-run-database-migrations)
7. [Configure Systemd Service](#7-configure-systemd-service)
8. [Configure Reverse Proxy](#8-configure-reverse-proxy)
9. [Configure Firewall](#9-configure-firewall)
10. [Setup Logging and Monitoring](#10-setup-logging-and-monitoring)
11. [Backup Strategy](#11-backup-strategy)
12. [Production Validation](#12-production-validation)

---

## 1. Create Lightsail Instance

### Option A: AWS Lightsail

1. **Log in to AWS Console**: https://lightsail.aws.amazon.com/

2. **Create Instance**:
   ```
   - Platform: Linux/Unix
   - Blueprint: OS Only → Ubuntu 22.04 LTS
   - Instance Plan: $10/month (2 GB RAM, 1 vCPU, 60 GB SSD)
   - Name: toolkitrag-prod
   ```

3. **Create Static IP** (Optional but recommended):
   ```
   - Networking tab → Create static IP
   - Attach to your instance
   - Note the IP address
   ```

4. **Configure Networking**:
   - Open Ports: 22 (SSH), 80 (HTTP), 443 (HTTPS)
   - Close Port 8000 (app will be behind reverse proxy)

### Option B: Other VPS Providers

**DigitalOcean**:
- Droplet: Ubuntu 22.04, Basic plan ($12/month, 2GB RAM)

**Linode**:
- Linode: Ubuntu 22.04, Nanode 2GB ($12/month)

**Vultr**:
- Cloud Compute: Ubuntu 22.04, 2GB RAM ($12/month)

### Initial Connection

```bash
# Download SSH key from Lightsail console (or use your own)
chmod 400 ~/Downloads/LightsailDefaultKey.pem

# Connect to instance
ssh -i ~/Downloads/LightsailDefaultKey.pem ubuntu@YOUR_IP_ADDRESS
```

---

## 2. Secure SSH Access

### Create Non-Root User

```bash
# Create deployment user
sudo adduser deployer
sudo usermod -aG sudo deployer

# Set strong password when prompted
```

### Setup SSH Keys for New User

**On your local machine**:

```bash
# Generate SSH key if you don't have one
ssh-keygen -t ed25519 -C "deployer@toolkitrag"

# Copy public key
cat ~/.ssh/id_ed25519.pub
```

**On the server (as ubuntu user)**:

```bash
# Setup SSH for deployer user
sudo mkdir -p /home/deployer/.ssh
sudo touch /home/deployer/.ssh/authorized_keys
sudo chmod 700 /home/deployer/.ssh
sudo chmod 600 /home/deployer/.ssh/authorized_keys

# Add your public key
sudo nano /home/deployer/.ssh/authorized_keys
# Paste your public key and save

sudo chown -R deployer:deployer /home/deployer/.ssh
```

### Test SSH Access

**From your local machine**:

```bash
# Test login with new user
ssh deployer@YOUR_IP_ADDRESS

# If successful, proceed to harden SSH
```

### Harden SSH Configuration

```bash
# Backup original config
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup

# Edit SSH config
sudo nano /etc/ssh/sshd_config
```

**Update these settings**:

```
# Disable root login
PermitRootLogin no

# Disable password authentication (use keys only)
PasswordAuthentication no
PubkeyAuthentication yes

# Disable empty passwords
PermitEmptyPasswords no

# Use SSH Protocol 2 only
Protocol 2

# Limit users who can SSH
AllowUsers deployer

# Change default port (optional but recommended)
# Port 2222
```

**Restart SSH**:

```bash
# Restart SSH service
sudo systemctl restart sshd

# IMPORTANT: Keep your current session open!
# Test in a NEW terminal window before closing this one
ssh deployer@YOUR_IP_ADDRESS  # (use -p 2222 if you changed port)
```

---

## 3. Install System Dependencies

### Update System

```bash
# Update package lists
sudo apt update
sudo apt upgrade -y

# Install essential tools
sudo apt install -y \
    build-essential \
    curl \
    git \
    ufw \
    unattended-upgrades \
    fail2ban
```

### Install Python 3.11

```bash
# Add deadsnakes PPA for Python 3.11
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update

# Install Python 3.11
sudo apt install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip

# Verify installation
python3.11 --version  # Should show Python 3.11.x
```

### Install PostgreSQL Client

```bash
# Install PostgreSQL 15 client tools
sudo apt install -y postgresql-client-15

# Verify
psql --version  # Should show psql (PostgreSQL) 15.x
```

### Install Caddy (Recommended) or Nginx

**Option A: Caddy (Recommended - Automatic HTTPS)**:

```bash
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy

# Verify
caddy version
```

**Option B: Nginx (Alternative)**:

```bash
# Install Nginx
sudo apt install -y nginx

# Verify
nginx -v
```

---

## 4. Setup PostgreSQL

You have several options for PostgreSQL:

### Option A: Local PostgreSQL (Included)

```bash
# Install PostgreSQL 15
sudo apt install -y postgresql-15 postgresql-contrib

# Install pgvector extension
sudo apt install -y postgresql-15-pgvector

# Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql <<EOF
CREATE USER toolkitrag WITH PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';
CREATE DATABASE toolkitrag OWNER toolkitrag;
\c toolkitrag
CREATE EXTENSION vector;
GRANT ALL PRIVILEGES ON DATABASE toolkitrag TO toolkitrag;
EOF

# Configure PostgreSQL to only accept local connections
sudo nano /etc/postgresql/15/main/postgresql.conf
# Ensure: listen_addresses = 'localhost'

sudo systemctl restart postgresql

# Test connection
psql -h localhost -U toolkitrag -d toolkitrag -c "SELECT version();"
```

**DATABASE_URL**: `postgresql://toolkitrag:YOUR_PASSWORD@localhost:5432/toolkitrag`

### Option B: AWS RDS

1. **Create RDS Instance**:
   - Engine: PostgreSQL 15
   - Template: Free tier or Production
   - DB instance identifier: toolkitrag-db
   - Master username: toolkitrag
   - Master password: (generate strong password)
   - VPC: Same as Lightsail instance
   - Public access: No (unless Lightsail is in different VPC)
   - Create database: toolkitrag

2. **Enable pgvector**:
   ```sql
   -- Connect to RDS and run:
   CREATE EXTENSION vector;
   ```

**DATABASE_URL**: `postgresql://toolkitrag:PASSWORD@your-rds-endpoint.region.rds.amazonaws.com:5432/toolkitrag`

### Option C: Supabase

1. **Create Project**: https://supabase.com/dashboard
2. **Get Connection String**: Settings → Database → Connection string (Direct)
3. **Enable pgvector**: Already installed

**DATABASE_URL**: `postgresql://postgres:PASSWORD@db.PROJECT_ID.supabase.co:5432/postgres`

### Option D: Neon

1. **Create Project**: https://neon.tech/
2. **Get Connection String**: From dashboard
3. **pgvector**: Already installed

**DATABASE_URL**: `postgresql://user:password@ep-xxx.region.aws.neon.tech/dbname?sslmode=require`

---

## 5. Clone and Configure Application

### Create Application Directory

```bash
# Create app directory
sudo mkdir -p /opt/toolkitrag
sudo chown deployer:deployer /opt/toolkitrag
cd /opt/toolkitrag
```

### Clone Repository

```bash
# Clone from GitHub (replace with your repo)
git clone https://github.com/YOUR_USERNAME/toolkitrag.git app
cd app

# Or upload via SCP if not using git:
# From your local machine:
# scp -r /path/to/aitools deployer@YOUR_IP:/opt/toolkitrag/app
```

### Create Virtual Environment

```bash
# Create venv with Python 3.11
python3.11 -m venv venv

# Activate venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "import fastapi; print(fastapi.__version__)"
```

### Create Required Directories

```bash
# Create data directories
mkdir -p /opt/toolkitrag/data/uploads
mkdir -p /var/log/toolkitrag

# Set permissions
sudo chown -R deployer:deployer /opt/toolkitrag
sudo chown -R deployer:deployer /var/log/toolkitrag
```

### Configure Environment Variables

```bash
# Create production environment file
sudo nano /etc/toolkitrag/.env
```

**Production .env template**:

```bash
# =============================================================================
# PRODUCTION ENVIRONMENT CONFIGURATION
# =============================================================================

# Environment (MUST be 'prod')
ENV=prod

# =============================================================================
# Database
# =============================================================================
# Replace with your actual database URL
DATABASE_URL=postgresql://toolkitrag:YOUR_PASSWORD@localhost:5432/toolkitrag

# =============================================================================
# Security - CRITICAL
# =============================================================================
# Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'
SECRET_KEY=REPLACE_WITH_YOUR_GENERATED_SECRET_KEY_32_CHARS_MIN

# CSRF Secret (auto-generated if not provided)
CSRF_SECRET_KEY=REPLACE_WITH_YOUR_CSRF_SECRET_32_CHARS_MIN

# Cookie Security (auto-enforced in production)
COOKIE_SECURE=true
COOKIE_HTTPONLY=true
COOKIE_SAMESITE=lax

# Session Settings
SESSION_COOKIE_NAME=session
SESSION_MAX_AGE=2592000  # 30 days

# =============================================================================
# Rate Limiting
# =============================================================================
RATE_LIMIT_ENABLED=true
RATE_LIMIT_AUTH_REQUESTS=5
RATE_LIMIT_AUTH_WINDOW=60
RATE_LIMIT_RAG_REQUESTS=20
RATE_LIMIT_RAG_WINDOW=60

# =============================================================================
# Logging
# =============================================================================
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/var/log/toolkitrag/app.log

# =============================================================================
# OpenAI API
# =============================================================================
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-REPLACE_WITH_YOUR_OPENAI_API_KEY
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_CHAT_TEMPERATURE=0.1

# Embedding Configuration
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# =============================================================================
# RAG Configuration
# =============================================================================
RAG_TOP_K=5
RAG_SIMILARITY_THRESHOLD=0.7
RAG_MAX_CONTEXT_LENGTH=4000

# =============================================================================
# Admin - DO NOT SET IN PRODUCTION
# =============================================================================
# Create admin users through the application after deployment
# ADMIN_PASSWORD=  # LEAVE EMPTY OR COMMENTED OUT
```

**Generate secrets**:

```bash
# Generate SECRET_KEY
python3.11 -c 'import secrets; print(secrets.token_urlsafe(32))'

# Generate CSRF_SECRET_KEY
python3.11 -c 'import secrets; print(secrets.token_urlsafe(32))'

# Copy these values into your .env file
```

**Set secure permissions**:

```bash
# Create directory
sudo mkdir -p /etc/toolkitrag

# Move .env file
sudo mv /etc/toolkitrag/.env /etc/toolkitrag/.env.bak  # if exists
sudo nano /etc/toolkitrag/.env  # Create with above template

# Set permissions
sudo chown root:deployer /etc/toolkitrag/.env
sudo chmod 640 /etc/toolkitrag/.env

# Link to app directory
ln -s /etc/toolkitrag/.env /opt/toolkitrag/app/.env
```

---

## 6. Run Database Migrations

```bash
# Navigate to app directory
cd /opt/toolkitrag/app

# Activate venv
source venv/bin/activate

# Verify .env is linked
ls -la .env  # Should show symlink to /etc/toolkitrag/.env

# Test database connection
python -c "from app.db import engine; from sqlalchemy import text; \
    with engine.connect() as conn: print(conn.execute(text('SELECT 1')).scalar())"

# Run migrations
alembic upgrade head

# Verify tables created
psql $DATABASE_URL -c "\dt"
# Should show: users, sessions, toolkit_documents, toolkit_chunks, chat_logs, feedbacks, strategies
```

**If migrations fail**:

```bash
# Check database connection
psql $DATABASE_URL -c "SELECT version();"

# Check alembic current version
alembic current

# Show migration history
alembic history

# If stuck, you can manually stamp:
# alembic stamp head
```

---

## 7. Configure Systemd Service

### Create Systemd Service File

```bash
sudo nano /etc/systemd/system/toolkitrag.service
```

**Copy contents from `deployment/toolkitrag.service` (see section below)**

### Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable toolkitrag

# Start service
sudo systemctl start toolkitrag

# Check status
sudo systemctl status toolkitrag

# View logs
sudo journalctl -u toolkitrag -f

# If there are errors, check logs and fix issues
sudo journalctl -u toolkitrag -n 100 --no-pager
```

### Test Application

```bash
# Test local connection
curl http://localhost:8000/health
# Should return: {"status":"healthy"}

curl http://localhost:8000/ready
# Should return: {"status":"ready","database":"connected","tables":"present"}
```

---

## 8. Configure Reverse Proxy

### Option A: Caddy (Recommended)

**Why Caddy?**
- Automatic HTTPS with Let's Encrypt
- Simple configuration
- Automatic certificate renewal
- Modern defaults

**Steps**:

```bash
# Stop Caddy if running
sudo systemctl stop caddy

# Create Caddyfile
sudo nano /etc/caddy/Caddyfile
```

**Copy contents from `deployment/Caddyfile` (see section below)**

**Update domain**:
```bash
# Replace yourdomain.com with your actual domain
sudo sed -i 's/yourdomain.com/YOUR_ACTUAL_DOMAIN/g' /etc/caddy/Caddyfile
```

**Start Caddy**:

```bash
# Test configuration
sudo caddy validate --config /etc/caddy/Caddyfile

# Start Caddy
sudo systemctl start caddy
sudo systemctl enable caddy

# Check status
sudo systemctl status caddy

# View logs
sudo journalctl -u caddy -f
```

### Option B: Nginx (Alternative)

**Steps**:

```bash
# Create Nginx config
sudo nano /etc/nginx/sites-available/toolkitrag
```

**Copy contents from `deployment/nginx.conf` (see section below)**

**Update domain and enable site**:

```bash
# Replace domain
sudo sed -i 's/yourdomain.com/YOUR_ACTUAL_DOMAIN/g' /etc/nginx/sites-available/toolkitrag

# Create symlink
sudo ln -s /etc/nginx/sites-available/toolkitrag /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

**Install SSL with Certbot**:

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d yourdomain.com

# Test auto-renewal
sudo certbot renew --dry-run
```

### DNS Configuration

**Before HTTPS will work, configure your DNS**:

1. **Point Domain to Server**:
   ```
   Type: A Record
   Name: @ (or subdomain like 'app')
   Value: YOUR_SERVER_IP
   TTL: 3600
   ```

2. **Wait for DNS Propagation** (5-30 minutes):
   ```bash
   # Check DNS
   nslookup yourdomain.com
   dig yourdomain.com
   ```

3. **Verify HTTPS**:
   ```bash
   curl -I https://yourdomain.com/health
   ```

---

## 9. Configure Firewall

### Setup UFW (Uncomplicated Firewall)

```bash
# Reset UFW (if previously configured)
sudo ufw --force reset

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (IMPORTANT: Do this first!)
sudo ufw allow 22/tcp
# Or if you changed SSH port:
# sudo ufw allow 2222/tcp

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Deny direct access to app port
sudo ufw deny 8000/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status verbose
```

**Expected output**:
```
Status: active

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW       Anywhere
80/tcp                     ALLOW       Anywhere
443/tcp                    ALLOW       Anywhere
8000/tcp                   DENY        Anywhere
```

### Install Fail2Ban (SSH Protection)

```bash
# Install fail2ban
sudo apt install -y fail2ban

# Create local config
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local

# Edit config
sudo nano /etc/fail2ban/jail.local
```

**Update these settings**:
```ini
[sshd]
enabled = true
port = 22  # Or your custom SSH port
maxretry = 3
bantime = 3600
findtime = 600
```

**Start fail2ban**:

```bash
sudo systemctl start fail2ban
sudo systemctl enable fail2ban

# Check status
sudo fail2ban-client status sshd
```

---

## 10. Setup Logging and Monitoring

### Configure Log Rotation

```bash
# Create logrotate config
sudo nano /etc/logrotate.d/toolkitrag
```

**Contents**:
```
/var/log/toolkitrag/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 deployer deployer
    sharedscripts
    postrotate
        systemctl reload toolkitrag >/dev/null 2>&1 || true
    endscript
}
```

**Test logrotate**:

```bash
# Test rotation
sudo logrotate -d /etc/logrotate.d/toolkitrag

# Force rotation (for testing)
sudo logrotate -f /etc/logrotate.d/toolkitrag
```

### View Logs

```bash
# Application logs (JSON format)
tail -f /var/log/toolkitrag/app.log | jq .

# Systemd logs
sudo journalctl -u toolkitrag -f

# Caddy/Nginx logs
sudo journalctl -u caddy -f
# or
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Search for errors
grep '"level":"ERROR"' /var/log/toolkitrag/app.log | jq .

# Track specific request
grep '"request_id":"abc-123"' /var/log/toolkitrag/app.log | jq .
```

### Setup Monitoring (Optional)

**Basic health monitoring with cron**:

```bash
# Create health check script
cat > /opt/toolkitrag/health-check.sh <<'EOF'
#!/bin/bash
HEALTH=$(curl -s http://localhost:8000/health | jq -r '.status')
if [ "$HEALTH" != "healthy" ]; then
    echo "$(date): Health check failed!" | mail -s "ToolkitRAG Down" admin@yourdomain.com
fi
EOF

chmod +x /opt/toolkitrag/health-check.sh

# Add to cron (every 5 minutes)
crontab -e
# Add: */5 * * * * /opt/toolkitrag/health-check.sh
```

---

## 11. Backup Strategy

### Database Backups

**Create backup script**:

```bash
# Create backup directory
sudo mkdir -p /opt/toolkitrag/backups
sudo chown deployer:deployer /opt/toolkitrag/backups

# Create backup script
nano /opt/toolkitrag/backup-db.sh
```

**Script contents**:
```bash
#!/bin/bash

# Configuration
BACKUP_DIR="/opt/toolkitrag/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/toolkitrag_$DATE.sql.gz"
DB_URL="postgresql://toolkitrag:PASSWORD@localhost:5432/toolkitrag"

# Keep only last 30 days of backups
RETENTION_DAYS=30

# Create backup
pg_dump "$DB_URL" | gzip > "$BACKUP_FILE"

# Check if backup was successful
if [ $? -eq 0 ]; then
    echo "$(date): Backup successful: $BACKUP_FILE"
else
    echo "$(date): Backup failed!" >&2
    exit 1
fi

# Delete old backups
find "$BACKUP_DIR" -name "toolkitrag_*.sql.gz" -mtime +$RETENTION_DAYS -delete

# Optional: Upload to S3
# aws s3 cp "$BACKUP_FILE" s3://your-bucket/backups/
```

**Make executable and test**:

```bash
chmod +x /opt/toolkitrag/backup-db.sh
/opt/toolkitrag/backup-db.sh
```

**Schedule daily backups**:

```bash
# Add to crontab
crontab -e

# Add line (runs daily at 2 AM):
0 2 * * * /opt/toolkitrag/backup-db.sh >> /var/log/toolkitrag/backup.log 2>&1
```

### Uploaded Files Backup

**Create backup script**:

```bash
nano /opt/toolkitrag/backup-files.sh
```

**Script contents**:
```bash
#!/bin/bash

BACKUP_DIR="/opt/toolkitrag/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/uploads_$DATE.tar.gz"
UPLOADS_DIR="/opt/toolkitrag/data/uploads"

# Create backup
tar -czf "$BACKUP_FILE" -C /opt/toolkitrag/data uploads

# Keep last 30 days
find "$BACKUP_DIR" -name "uploads_*.tar.gz" -mtime +30 -delete

echo "$(date): Files backup complete: $BACKUP_FILE"
```

**Schedule weekly backups**:

```bash
chmod +x /opt/toolkitrag/backup-files.sh

# Add to crontab (runs weekly on Sunday at 3 AM)
crontab -e
0 3 * * 0 /opt/toolkitrag/backup-files.sh >> /var/log/toolkitrag/backup.log 2>&1
```

### Restore from Backup

**Restore database**:

```bash
# Find backup
ls -lh /opt/toolkitrag/backups/

# Restore from backup
gunzip < /opt/toolkitrag/backups/toolkitrag_20260123_020000.sql.gz | \
    psql postgresql://toolkitrag:PASSWORD@localhost:5432/toolkitrag
```

**Restore files**:

```bash
# Restore uploads
tar -xzf /opt/toolkitrag/backups/uploads_20260123_030000.tar.gz \
    -C /opt/toolkitrag/data/
```

---

## 12. Production Validation

### Pre-Deployment Checklist

Run through this checklist before considering deployment complete:

```bash
# Navigate to validation script location
cd /opt/toolkitrag/app

# Create validation script
cat > validate-deployment.sh <<'EOF'
#!/bin/bash

echo "=========================================="
echo "ToolkitRAG Production Validation"
echo "=========================================="
echo ""

# 1. Check services
echo "1. Checking services..."
systemctl is-active --quiet toolkitrag && echo "✓ Application running" || echo "✗ Application not running"
systemctl is-active --quiet caddy && echo "✓ Caddy running" || echo "✓ Caddy running (or using Nginx)"
systemctl is-active --quiet postgresql && echo "✓ PostgreSQL running" || echo "✓ Using managed DB"

echo ""

# 2. Check health endpoints
echo "2. Checking health endpoints..."
HEALTH=$(curl -s http://localhost:8000/health | jq -r '.status' 2>/dev/null)
[ "$HEALTH" = "healthy" ] && echo "✓ /health returns healthy" || echo "✗ /health failed"

READY=$(curl -s http://localhost:8000/ready | jq -r '.status' 2>/dev/null)
[ "$READY" = "ready" ] && echo "✓ /ready returns ready" || echo "✗ /ready failed"

echo ""

# 3. Check HTTPS
echo "3. Checking HTTPS..."
if curl -s -I https://$(hostname -f)/health 2>&1 | grep -q "200 OK"; then
    echo "✓ HTTPS working"
else
    echo "✗ HTTPS not working (check DNS and certificates)"
fi

echo ""

# 4. Check file permissions
echo "4. Checking permissions..."
[ -r /etc/toolkitrag/.env ] && echo "✓ .env readable" || echo "✗ .env not readable"
[ -w /opt/toolkitrag/data/uploads ] && echo "✓ Uploads writable" || echo "✗ Uploads not writable"
[ -w /var/log/toolkitrag ] && echo "✓ Logs writable" || echo "✗ Logs not writable"

echo ""

# 5. Check database
echo "5. Checking database..."
python3 -c "from app.db import engine; from sqlalchemy import text; \
    conn = engine.connect(); \
    result = conn.execute(text('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = \\'public\\'')); \
    count = result.scalar(); \
    print(f'✓ Database has {count} tables')" 2>/dev/null || echo "✗ Database check failed"

echo ""
echo "=========================================="
echo "Validation complete"
echo "=========================================="
EOF

chmod +x validate-deployment.sh
./validate-deployment.sh
```

### Manual Validation Tests

**1. Test Login**:

```bash
# Visit your domain
https://yourdomain.com/login

# Create test account or login with existing credentials
# Verify:
# - Login successful
# - Session cookie set
# - Redirects to toolkit page
```

**2. Test Admin Ingest**:

```bash
# Visit admin page
https://yourdomain.com/admin

# Upload a test document:
# - Navigate to /admin/documents/upload
# - Upload a .docx file
# - Enter version tag (e.g., "test-v1")
# - Submit and verify ingestion completes

# Check document appears in /admin/documents
```

**3. Test Chat + Citations**:

```bash
# Visit toolkit
https://yourdomain.com/toolkit

# Enter a query about your ingested content
# Verify:
# - Answer is generated
# - Citations are shown
# - Feedback option appears
```

**4. Test Strategy Plan Creation**:

```bash
# Visit strategy builder
https://yourdomain.com/strategy

# Create a new strategy plan:
# - Enter initiative details
# - Define clusters
# - Map tools to clusters
# - Save strategy

# Verify:
# - Strategy saves successfully
# - Appears in strategy list
# - Can be edited and deleted
```

**5. Test Multi-User Isolation**:

```bash
# Create two test accounts:
# User A: usera@test.com
# User B: userb@test.com

# As User A:
# - Create a strategy plan "User A Plan"

# As User B:
# - Create a strategy plan "User B Plan"
# - Verify you CANNOT see User A's plan

# As Admin:
# - View /admin/users
# - Verify both users appear
# - Verify each has separate data
```

---

## Quick Command Reference

### Application Management

```bash
# Start/stop/restart app
sudo systemctl start toolkitrag
sudo systemctl stop toolkitrag
sudo systemctl restart toolkitrag

# View status
sudo systemctl status toolkitrag

# View logs
sudo journalctl -u toolkitrag -f

# Reload after code changes
sudo systemctl restart toolkitrag
```

### Database Operations

```bash
# Connect to database
psql $DATABASE_URL

# Run migrations
cd /opt/toolkitrag/app && source venv/bin/activate
alembic upgrade head

# Create backup
/opt/toolkitrag/backup-db.sh

# Restore backup
gunzip < backup.sql.gz | psql $DATABASE_URL
```

### Reverse Proxy

```bash
# Caddy
sudo systemctl restart caddy
sudo journalctl -u caddy -f

# Nginx
sudo systemctl restart nginx
sudo nginx -t  # Test config
```

### Monitoring

```bash
# Check health
curl https://yourdomain.com/health
curl https://yourdomain.com/ready

# View application logs
tail -f /var/log/toolkitrag/app.log | jq .

# View reverse proxy logs
sudo journalctl -u caddy -f
```

---

## Troubleshooting

### Application Won't Start

```bash
# Check logs
sudo journalctl -u toolkitrag -n 100 --no-pager

# Check environment
sudo -u deployer cat /etc/toolkitrag/.env | grep -v "PASSWORD\|KEY"

# Test manually
cd /opt/toolkitrag/app
source venv/bin/activate
python -m app.main
```

### Database Connection Issues

```bash
# Test connection
psql $DATABASE_URL -c "SELECT 1"

# Check PostgreSQL status
sudo systemctl status postgresql

# View PostgreSQL logs
sudo journalctl -u postgresql -f
```

### HTTPS Not Working

```bash
# Check DNS
nslookup yourdomain.com

# Check certificates (Caddy)
sudo caddy validate --config /etc/caddy/Caddyfile

# Check certificates (Nginx)
sudo certbot certificates

# Check firewall
sudo ufw status
```

### Rate Limiting Issues

```bash
# Check rate limit logs
grep "Rate limit exceeded" /var/log/toolkitrag/app.log | jq .

# Temporarily disable (in .env)
RATE_LIMIT_ENABLED=false
sudo systemctl restart toolkitrag
```

---

## Security Hardening Checklist

- [ ] Non-root user created (`deployer`)
- [ ] SSH key authentication enabled
- [ ] SSH password authentication disabled
- [ ] SSH root login disabled
- [ ] Firewall enabled (UFW)
- [ ] Fail2ban installed and configured
- [ ] ENV=prod in environment file
- [ ] SECRET_KEY is 32+ characters
- [ ] COOKIE_SECURE=true
- [ ] Database password is strong
- [ ] .env file permissions are 640
- [ ] HTTPS enabled with valid certificate
- [ ] Auto-renewal configured (Caddy or Certbot)
- [ ] Regular backups scheduled
- [ ] Log rotation configured
- [ ] Monitoring/alerting configured

---

## Next Steps

After successful deployment:

1. **Create Admin User**: Visit `/register` and create admin account, then promote via database or admin panel

2. **Upload Production Content**: Ingest your production toolkit documents

3. **Configure Monitoring**: Setup external monitoring (UptimeRobot, Pingdom, etc.)

4. **Setup Alerts**: Configure email/Slack alerts for downtime

5. **Document Procedures**: Create runbook for your team

6. **Test Disaster Recovery**: Verify backups and restoration procedures

---

For detailed configuration files, see:
- `deployment/toolkitrag.service` - Systemd service file
- `deployment/Caddyfile` - Caddy reverse proxy config
- `deployment/nginx.conf` - Nginx reverse proxy config

For additional help, refer to [DEPLOYMENT.md](DEPLOYMENT.md) or contact support.
