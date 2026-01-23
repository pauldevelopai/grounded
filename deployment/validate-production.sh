#!/bin/bash

# ToolkitRAG Production Validation Script
# Run this after deployment to verify everything is working

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get domain from args or use localhost
DOMAIN="${1:-localhost}"
PROTOCOL="http"
if [ "$DOMAIN" != "localhost" ]; then
    PROTOCOL="https"
fi

echo "=========================================="
echo "ToolkitRAG Production Validation"
echo "Domain: $DOMAIN"
echo "=========================================="
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to print success
success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Function to print error
error() {
    echo -e "${RED}✗${NC} $1"
}

# Function to print warning
warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# 1. Check system services
echo "1. Checking System Services"
echo "----------------------------"

if systemctl is-active --quiet toolkitrag; then
    success "Application service running"
else
    error "Application service not running"
    echo "  Run: sudo systemctl status toolkitrag"
fi

if systemctl is-active --quiet caddy 2>/dev/null; then
    success "Caddy reverse proxy running"
elif systemctl is-active --quiet nginx 2>/dev/null; then
    success "Nginx reverse proxy running"
else
    warning "No reverse proxy detected (Caddy or Nginx)"
fi

if systemctl is-active --quiet postgresql 2>/dev/null; then
    success "PostgreSQL running (local)"
else
    warning "PostgreSQL not running locally (using managed DB?)"
fi

echo ""

# 2. Check health endpoints
echo "2. Checking Health Endpoints"
echo "----------------------------"

# Check /health
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
if [ "$HEALTH_STATUS" = "200" ]; then
    HEALTH_JSON=$(curl -s http://localhost:8000/health 2>/dev/null)
    HEALTH_MSG=$(echo "$HEALTH_JSON" | jq -r '.status' 2>/dev/null || echo "unknown")
    if [ "$HEALTH_MSG" = "healthy" ]; then
        success "/health endpoint returns 200 OK (healthy)"
    else
        warning "/health returns 200 but status is: $HEALTH_MSG"
    fi
else
    error "/health endpoint failed (HTTP $HEALTH_STATUS)"
fi

# Check /ready
READY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ready 2>/dev/null || echo "000")
if [ "$READY_STATUS" = "200" ]; then
    READY_JSON=$(curl -s http://localhost:8000/ready 2>/dev/null)
    DB_STATUS=$(echo "$READY_JSON" | jq -r '.database' 2>/dev/null || echo "unknown")
    TABLES_STATUS=$(echo "$READY_JSON" | jq -r '.tables' 2>/dev/null || echo "unknown")

    if [ "$DB_STATUS" = "connected" ] && [ "$TABLES_STATUS" = "present" ]; then
        success "/ready endpoint returns 200 OK (database connected, tables present)"
    else
        warning "/ready returns 200 but DB=$DB_STATUS, Tables=$TABLES_STATUS"
    fi
else
    error "/ready endpoint failed (HTTP $READY_STATUS)"
    echo "  This means database is not connected or tables are missing"
fi

echo ""

# 3. Check HTTPS (if not localhost)
if [ "$DOMAIN" != "localhost" ]; then
    echo "3. Checking HTTPS"
    echo "----------------------------"

    HTTPS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://$DOMAIN/health 2>/dev/null || echo "000")
    if [ "$HTTPS_STATUS" = "200" ]; then
        success "HTTPS working on https://$DOMAIN"

        # Check certificate
        if command_exists openssl; then
            CERT_INFO=$(echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -dates 2>/dev/null)
            if [ -n "$CERT_INFO" ]; then
                success "SSL certificate valid"
            fi
        fi
    else
        error "HTTPS not working (HTTP $HTTPS_STATUS)"
        echo "  Check DNS, certificates, and reverse proxy configuration"
    fi

    echo ""
fi

# 4. Check file permissions
echo "4. Checking File Permissions"
echo "----------------------------"

if [ -r /etc/toolkitrag/.env ]; then
    success ".env file readable"

    # Check ENV setting
    ENV_VALUE=$(grep "^ENV=" /etc/toolkitrag/.env | cut -d'=' -f2)
    if [ "$ENV_VALUE" = "prod" ]; then
        success "ENV=prod (production mode)"
    else
        warning "ENV=$ENV_VALUE (not production)"
    fi

    # Check SECRET_KEY
    if grep -q "^SECRET_KEY=" /etc/toolkitrag/.env; then
        SECRET_LEN=$(grep "^SECRET_KEY=" /etc/toolkitrag/.env | cut -d'=' -f2 | wc -c)
        if [ $SECRET_LEN -ge 32 ]; then
            success "SECRET_KEY set (length OK)"
        else
            warning "SECRET_KEY too short (< 32 characters)"
        fi
    else
        error "SECRET_KEY not set"
    fi
else
    error ".env file not readable"
fi

if [ -w /opt/toolkitrag/data/uploads ]; then
    success "Upload directory writable"
else
    error "Upload directory not writable"
fi

if [ -w /var/log/toolkitrag ]; then
    success "Log directory writable"
else
    error "Log directory not writable"
fi

echo ""

# 5. Check database
echo "5. Checking Database"
echo "----------------------------"

if command_exists python3; then
    cd /opt/toolkitrag/app 2>/dev/null || cd .

    # Check if venv exists
    if [ -f venv/bin/python ]; then
        TABLE_COUNT=$(venv/bin/python -c "
from app.db import engine
from sqlalchemy import text
try:
    with engine.connect() as conn:
        result = conn.execute(text(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'\"))
        print(result.scalar())
except Exception as e:
    print('0')
" 2>/dev/null)

        if [ "$TABLE_COUNT" -gt 0 ]; then
            success "Database has $TABLE_COUNT tables"
        else
            error "Database has no tables (run migrations)"
        fi

        # Check for required tables
        REQUIRED_TABLES=("users" "toolkit_documents" "toolkit_chunks" "sessions" "chat_logs" "feedbacks")
        for table in "${REQUIRED_TABLES[@]}"; do
            EXISTS=$(venv/bin/python -c "
from app.db import engine
from sqlalchemy import text
try:
    with engine.connect() as conn:
        result = conn.execute(text(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='$table')\"))
        print('1' if result.scalar() else '0')
except:
    print('0')
" 2>/dev/null)

            if [ "$EXISTS" = "1" ]; then
                success "Table '$table' exists"
            else
                error "Table '$table' missing"
            fi
        done
    else
        warning "Virtual environment not found, skipping detailed DB check"
    fi
else
    warning "Python not found, skipping database check"
fi

echo ""

# 6. Check logs
echo "6. Checking Logs"
echo "----------------------------"

if [ -f /var/log/toolkitrag/app.log ]; then
    LOG_SIZE=$(du -h /var/log/toolkitrag/app.log | cut -f1)
    LOG_LINES=$(wc -l < /var/log/toolkitrag/app.log)
    success "Application log exists ($LOG_SIZE, $LOG_LINES lines)"

    # Check for recent errors
    RECENT_ERRORS=$(tail -n 100 /var/log/toolkitrag/app.log | grep -c '"level":"ERROR"' || echo "0")
    if [ "$RECENT_ERRORS" -gt 0 ]; then
        warning "Found $RECENT_ERRORS recent errors in logs"
        echo "  Run: tail -f /var/log/toolkitrag/app.log | jq ."
    else
        success "No recent errors in logs"
    fi
else
    warning "Application log not found at /var/log/toolkitrag/app.log"
fi

echo ""

# 7. Check backups
echo "7. Checking Backups"
echo "----------------------------"

if [ -d /opt/toolkitrag/backups ]; then
    DB_BACKUPS=$(find /opt/toolkitrag/backups -name "toolkitrag_*.sql.gz" 2>/dev/null | wc -l)
    FILE_BACKUPS=$(find /opt/toolkitrag/backups -name "uploads_*.tar.gz" 2>/dev/null | wc -l)

    if [ "$DB_BACKUPS" -gt 0 ]; then
        LATEST_DB=$(find /opt/toolkitrag/backups -name "toolkitrag_*.sql.gz" -type f -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
        success "Database backups: $DB_BACKUPS (latest: $(basename $LATEST_DB))"
    else
        warning "No database backups found"
    fi

    if [ "$FILE_BACKUPS" -gt 0 ]; then
        success "File backups: $FILE_BACKUPS"
    else
        warning "No file backups found"
    fi
else
    warning "Backup directory not found"
fi

echo ""

# 8. Check firewall
echo "8. Checking Firewall"
echo "----------------------------"

if command_exists ufw; then
    if sudo ufw status | grep -q "Status: active"; then
        success "UFW firewall active"

        # Check port rules
        if sudo ufw status | grep -q "22.*ALLOW"; then
            success "SSH port open"
        fi
        if sudo ufw status | grep -q "80.*ALLOW"; then
            success "HTTP port open"
        fi
        if sudo ufw status | grep -q "443.*ALLOW"; then
            success "HTTPS port open"
        fi
        if sudo ufw status | grep -q "8000.*DENY"; then
            success "App port 8000 blocked (good!)"
        else
            warning "App port 8000 not explicitly blocked"
        fi
    else
        warning "UFW firewall not active"
    fi
else
    warning "UFW not installed"
fi

echo ""

# Summary
echo "=========================================="
echo "Validation Summary"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Test login at $PROTOCOL://$DOMAIN/login"
echo "2. Test admin access at $PROTOCOL://$DOMAIN/admin"
echo "3. Test document upload at $PROTOCOL://$DOMAIN/admin/documents/upload"
echo "4. Test chat at $PROTOCOL://$DOMAIN/toolkit"
echo "5. Test strategy builder at $PROTOCOL://$DOMAIN/strategy"
echo ""
echo "For detailed logs:"
echo "  sudo journalctl -u toolkitrag -f"
echo "  tail -f /var/log/toolkitrag/app.log | jq ."
echo ""
