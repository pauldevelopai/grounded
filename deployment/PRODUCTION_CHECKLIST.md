# Production Validation Checklist

Use this checklist to verify Grounded is properly deployed and fully functional.

## Current Production Server (AWS Lightsail)

| Setting | Value |
|---------|-------|
| **Instance Name** | GROUNDED |
| **OS** | Ubuntu |
| **Region** | eu-west-2 (London, Zone A) |
| **Instance Type** | General purpose |
| **Network** | Dual-stack |
| **Public IPv4** | 3.10.224.68 |
| **Private IPv4** | 172.26.10.236 |
| **Public IPv6** | 2a05:d01c:39:4900:1f55:672a:3ac7:c465 |
| **Username** | ubuntu |
| **SSH Key** | Default key for eu-west-2 |

### Quick SSH Access
```bash
ssh ubuntu@3.10.224.68
```

---

## Pre-Deployment Checklist

### Server Setup
- [x] VPS created (AWS Lightsail - GROUNDED instance)
- [x] Static IP assigned (3.10.224.68)
- [ ] DNS A record configured pointing to server IP
- [ ] Non-root user created (`deployer`)
- [ ] SSH key authentication configured
- [ ] SSH password authentication disabled
- [ ] SSH root login disabled

### System Dependencies
- [ ] Ubuntu 22.04 LTS installed
- [ ] System packages updated (`apt update && apt upgrade`)
- [ ] Python 3.11 installed
- [ ] PostgreSQL 15 client installed (or using managed DB)
- [ ] Caddy or Nginx installed
- [ ] UFW firewall installed
- [ ] fail2ban installed

### Database
- [ ] PostgreSQL database created
- [ ] Database user created with strong password
- [ ] pgvector extension installed
- [ ] Database accessible from application
- [ ] Connection tested with `psql`

### Application
- [ ] Repository cloned to `/opt/grounded/app`
- [ ] Virtual environment created with Python 3.11
- [ ] Dependencies installed from requirements.txt
- [ ] `.env` file created at `/etc/grounded/.env`
- [ ] `.env` permissions set to 640
- [ ] Environment variables configured (see below)
- [ ] SECRET_KEY generated (32+ characters)
- [ ] CSRF_SECRET_KEY generated (32+ characters)
- [ ] Database migrations run (`alembic upgrade head`)
- [ ] Upload directory created (`/opt/grounded/data/uploads`)
- [ ] Log directory created (`/var/log/grounded`)
- [ ] Permissions set correctly (deployer:deployer)

### Systemd Service
- [ ] Service file copied to `/etc/systemd/system/grounded.service`
- [ ] Service enabled (`systemctl enable grounded`)
- [ ] Service started (`systemctl start grounded`)
- [ ] Service status is active (`systemctl status grounded`)
- [ ] No errors in service logs (`journalctl -u grounded`)

### Reverse Proxy
- [ ] Caddy or Nginx configured
- [ ] Domain name updated in config file
- [ ] SSL certificate obtained (Let's Encrypt)
- [ ] HTTPS working
- [ ] HTTP redirects to HTTPS
- [ ] Security headers configured
- [ ] Reverse proxy logs show no errors

### Firewall
- [ ] UFW enabled
- [ ] SSH port allowed (22 or custom)
- [ ] HTTP port allowed (80)
- [ ] HTTPS port allowed (443)
- [ ] App port blocked (8000)
- [ ] fail2ban configured for SSH

### Backups
- [ ] Backup directory created (`/opt/grounded/backups`)
- [ ] Database backup script installed
- [ ] File backup script installed
- [ ] Backup scripts executable
- [ ] Cron jobs configured (daily DB, weekly files)
- [ ] Test backups created successfully
- [ ] Restore procedure tested

### Logging
- [ ] Application logs to `/var/log/grounded/app.log`
- [ ] Log rotation configured (`/etc/logrotate.d/grounded`)
- [ ] Logs are JSON formatted (production)
- [ ] No errors in recent logs

---

## Environment Variables Checklist

Verify all required environment variables are set in `/etc/grounded/.env`:

### Critical Settings
- [ ] `ENV=prod`
- [ ] `DATABASE_URL` (valid connection string)
- [ ] `SECRET_KEY` (32+ characters, unique)
- [ ] `CSRF_SECRET_KEY` (32+ characters, unique)
- [ ] `OPENAI_API_KEY` (valid API key)

### Security Settings
- [ ] `COOKIE_SECURE=true`
- [ ] `COOKIE_HTTPONLY=true`
- [ ] `COOKIE_SAMESITE=lax`
- [ ] `RATE_LIMIT_ENABLED=true`

### Logging Settings
- [ ] `LOG_LEVEL=INFO`
- [ ] `LOG_FORMAT=json`
- [ ] `LOG_FILE=/var/log/grounded/app.log`

### NOT Set (Security)
- [ ] `ADMIN_PASSWORD` is NOT set (or commented out)

---

## Functional Testing Checklist

### 1. Health Checks
Run automated validation script:
```bash
cd /opt/grounded/app
./deployment/validate-production.sh yourdomain.com
```

Manual checks:
- [ ] `curl http://localhost:8000/health` returns `{"status":"healthy"}`
- [ ] `curl http://localhost:8000/ready` returns `{"status":"ready","database":"connected","tables":"present"}`
- [ ] `curl https://yourdomain.com/health` returns 200 OK

### 2. User Registration and Login

**Test User Registration**:
1. [ ] Visit `https://yourdomain.com/register`
2. [ ] Create test account (email: `test1@example.com`, username: `testuser1`)
3. [ ] Registration succeeds and redirects to toolkit
4. [ ] Session cookie is set
5. [ ] User is logged in

**Test User Login**:
1. [ ] Log out (visit `/auth/logout`)
2. [ ] Visit `https://yourdomain.com/login`
3. [ ] Login with test credentials
4. [ ] Login succeeds and redirects to toolkit
5. [ ] Session persists across page reloads

**Test Invalid Login**:
1. [ ] Try logging in with wrong password
2. [ ] Error message displayed
3. [ ] Login prevented

### 3. Admin Access

**Test Admin Dashboard Access**:
1. [ ] Create admin user (register or promote via database)
2. [ ] Login as admin
3. [ ] Visit `https://yourdomain.com/admin`
4. [ ] Admin dashboard loads successfully
5. [ ] Stats displayed correctly

**Test Non-Admin Blocked**:
1. [ ] Login as regular user (testuser1)
2. [ ] Try to visit `/admin`
3. [ ] Access denied (403 Forbidden)

### 4. Document Ingestion

**Test Document Upload**:
1. [ ] Login as admin
2. [ ] Visit `https://yourdomain.com/admin/documents/upload`
3. [ ] Upload a test .docx file
4. [ ] Enter version tag (e.g., "test-v1")
5. [ ] Check "Create embeddings"
6. [ ] Submit form
7. [ ] Document ingestion completes without errors
8. [ ] Document appears in `/admin/documents`
9. [ ] Chunk count is displayed
10. [ ] Embeddings are created

**Verify Ingestion**:
```bash
# Check database
psql $DATABASE_URL -c "SELECT version_tag, chunk_count FROM toolkit_documents;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM toolkit_chunks WHERE embedding IS NOT NULL;"
```

**Test Reindex**:
1. [ ] In `/admin/documents`, click reindex icon for a document
2. [ ] Confirm reindex
3. [ ] Reindex completes successfully
4. [ ] Chunk count updates (if changed)

### 5. Chat + Citations

**Test RAG Query**:
1. [ ] Login as regular user
2. [ ] Visit `https://yourdomain.com/toolkit`
3. [ ] Enter a query about ingested content
4. [ ] Submit query
5. [ ] Answer is generated
6. [ ] Citations are displayed
7. [ ] Similarity scores shown
8. [ ] Feedback options appear

**Test Feedback**:
1. [ ] Submit positive feedback (thumbs up)
2. [ ] Feedback is recorded
3. [ ] Submit negative feedback with issue type
4. [ ] Feedback is recorded

**Verify Chat Logs**:
```bash
psql $DATABASE_URL -c "SELECT query, answer FROM chat_logs ORDER BY created_at DESC LIMIT 5;"
psql $DATABASE_URL -c "SELECT rating, issue_type FROM feedbacks ORDER BY created_at DESC LIMIT 5;"
```

### 6. Strategy Plan Creation

**Create Strategy**:
1. [ ] Login as user
2. [ ] Visit `https://yourdomain.com/strategy`
3. [ ] Click "Create New Strategy"
4. [ ] Fill in initiative details:
   - Initiative name: "Test Initiative"
   - Strategic focus: "Test Focus"
   - Impact areas: "Productivity, Innovation"
5. [ ] Add cluster:
   - Cluster ID: "cluster-1"
   - Cluster name: "Test Cluster"
6. [ ] Add tool to cluster:
   - Tool name: "Test Tool"
   - Purpose: "Testing"
7. [ ] Save strategy
8. [ ] Strategy appears in list

**Edit Strategy**:
1. [ ] Click edit on strategy
2. [ ] Modify fields
3. [ ] Save changes
4. [ ] Changes persist

**Delete Strategy**:
1. [ ] Click delete on strategy
2. [ ] Confirm deletion
3. [ ] Strategy removed from list

### 7. Multi-User Isolation

**Test Data Isolation**:
1. [ ] Create User A (usera@test.com)
2. [ ] Login as User A
3. [ ] Create strategy "User A Strategy"
4. [ ] Create chat query (should appear in chat logs)

5. [ ] Logout
6. [ ] Create User B (userb@test.com)
7. [ ] Login as User B
8. [ ] Create strategy "User B Strategy"
9. [ ] Visit `/strategy`
10. [ ] Verify ONLY "User B Strategy" is visible
11. [ ] Verify "User A Strategy" is NOT visible

**Verify Database Isolation**:
```bash
# Check strategies are user-specific
psql $DATABASE_URL -c "SELECT user_id, initiative_name FROM strategies;"

# Check chat logs are user-specific
psql $DATABASE_URL -c "SELECT user_id, query FROM chat_logs ORDER BY created_at DESC LIMIT 10;"
```

### 8. Admin Analytics

**Test Analytics Dashboard**:
1. [ ] Login as admin
2. [ ] Visit `https://yourdomain.com/admin/analytics`
3. [ ] Top queries displayed
4. [ ] Lowest rated answers shown
5. [ ] Issue types displayed
6. [ ] Refusal rate calculated
7. [ ] Rating distribution shown

### 9. Security Testing

**Test Rate Limiting**:
```bash
# Try 6 rapid login attempts (should be rate limited after 5)
for i in {1..6}; do
  curl -X POST https://yourdomain.com/auth/login \
    -d "username=test&password=wrong" \
    -w "\nHTTP Status: %{http_code}\n"
  sleep 1
done
```
- [ ] 6th request returns HTTP 429 (Too Many Requests)
- [ ] Retry-After header is present

**Test HTTPS Enforcement**:
```bash
# Try accessing via HTTP
curl -I http://yourdomain.com
```
- [ ] Redirects to HTTPS (301 or 302)

**Test Secure Cookies**:
```bash
# Check Set-Cookie headers
curl -I https://yourdomain.com/login
```
- [ ] Cookies have `HttpOnly` flag
- [ ] Cookies have `Secure` flag
- [ ] Cookies have `SameSite=Lax`

**Test Firewall**:
```bash
# Try accessing app port directly
curl http://yourdomain.com:8000/health
```
- [ ] Connection refused or timeout (port blocked by firewall)

### 10. Performance Testing

**Test Response Times**:
```bash
# Health check (should be < 50ms)
curl -w "@-" -o /dev/null -s https://yourdomain.com/health <<< 'time_total: %{time_total}s\n'

# Ready check (should be < 200ms)
curl -w "@-" -o /dev/null -s https://yourdomain.com/ready <<< 'time_total: %{time_total}s\n'

# Homepage (should be < 500ms)
curl -w "@-" -o /dev/null -s https://yourdomain.com/ <<< 'time_total: %{time_total}s\n'
```

**Test Concurrent Requests**:
```bash
# Use Apache Bench if available
ab -n 100 -c 10 https://yourdomain.com/health
```
- [ ] All requests succeed
- [ ] Average response time < 100ms

### 11. Backup and Restore

**Test Database Backup**:
```bash
/opt/grounded/deployment/backup-database.sh
```
- [ ] Backup completes successfully
- [ ] Backup file created in `/opt/grounded/backups`
- [ ] Backup file is gzipped SQL

**Test File Backup**:
```bash
/opt/grounded/deployment/backup-files.sh
```
- [ ] Backup completes successfully
- [ ] Backup file created
- [ ] Backup contains uploaded files

**Test Restore (Use Test Database!)**:
```bash
# List backups
./deployment/restore.sh

# Test database restore
./deployment/restore.sh database /opt/grounded/backups/grounded_YYYYMMDD_HHMMSS.sql.gz
```
- [ ] Restore completes successfully
- [ ] Application restarts
- [ ] Data is restored

### 12. Monitoring and Logging

**Check Application Logs**:
```bash
tail -f /var/log/grounded/app.log | jq .
```
- [ ] Logs are in JSON format
- [ ] Each request has unique `request_id`
- [ ] Log level is INFO
- [ ] No ERROR level logs (except expected)

**Check System Logs**:
```bash
sudo journalctl -u grounded -f
```
- [ ] Service is active
- [ ] No error messages

**Check Reverse Proxy Logs**:
```bash
# Caddy
sudo journalctl -u caddy -f

# Or Nginx
sudo tail -f /var/log/nginx/grounded.access.log
sudo tail -f /var/log/nginx/grounded.error.log
```
- [ ] Requests are being proxied
- [ ] HTTPS is working
- [ ] No 5xx errors

---

## Post-Deployment Checklist

### Immediate Actions
- [ ] Create first admin user
- [ ] Upload production toolkit documents
- [ ] Test all major features (login, admin, chat, strategy)
- [ ] Verify backups are running
- [ ] Configure monitoring/alerting

### Within 24 Hours
- [ ] Monitor error logs for issues
- [ ] Test from different devices/browsers
- [ ] Verify email notifications (if configured)
- [ ] Check SSL certificate expiry date
- [ ] Document any custom configurations

### Within 1 Week
- [ ] Perform first backup restore test
- [ ] Review analytics for usage patterns
- [ ] Optimize based on performance metrics
- [ ] Create runbook for your team
- [ ] Setup external monitoring (UptimeRobot, Pingdom)

---

## Troubleshooting Common Issues

### Application Won't Start
```bash
# Check logs
sudo journalctl -u grounded -n 100 --no-pager

# Test manually
cd /opt/grounded/app
source venv/bin/activate
python -m uvicorn app.main:app --reload
```

### Database Connection Failed
```bash
# Test connection
psql $DATABASE_URL -c "SELECT version();"

# Check PostgreSQL status
sudo systemctl status postgresql
```

### HTTPS Not Working
```bash
# Check DNS
nslookup yourdomain.com

# Check certificates
sudo caddy validate --config /etc/caddy/Caddyfile
# or
sudo certbot certificates

# Check logs
sudo journalctl -u caddy -n 50
```

### Rate Limits Too Strict
```bash
# Edit .env
sudo nano /etc/grounded/.env

# Increase limits
RATE_LIMIT_AUTH_REQUESTS=10
RATE_LIMIT_RAG_REQUESTS=50

# Restart
sudo systemctl restart grounded
```

---

## Success Criteria

✅ **Deployment is successful when**:
- All items in "Pre-Deployment Checklist" are checked
- All items in "Functional Testing Checklist" pass
- `/deployment/validate-production.sh` runs with no errors
- Users can register, login, and use all features
- Admins can ingest documents and access admin dashboard
- Backups are automated and tested
- Monitoring is in place
- Documentation is complete

---

## Support

For issues or questions:
1. Check logs: `sudo journalctl -u grounded -f`
2. Review deployment guide: `DEPLOY.md`
3. Run validation script: `./deployment/validate-production.sh`
4. Consult troubleshooting section above

---

**Deployment Checklist Version**: 3.0
**Last Updated**: 2026-02-03
**Edition**: V3 (AWS Lightsail)
