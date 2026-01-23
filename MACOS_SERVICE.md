# ToolkitRAG macOS Background Service

The application is now running permanently in the background using **launchd** (macOS's service manager).

## Service Status

✅ **Service Name**: `com.toolkitrag.app`
✅ **URL**: http://localhost:8000
✅ **Auto-start**: Enabled (starts on login and system restart)

## Service Management Commands

### Check if service is running
```bash
launchctl list | grep toolkitrag
```

### Restart the service
```bash
launchctl unload ~/Library/LaunchAgents/com.toolkitrag.app.plist
launchctl load ~/Library/LaunchAgents/com.toolkitrag.app.plist
```

### Stop the service
```bash
launchctl unload ~/Library/LaunchAgents/com.toolkitrag.app.plist
```

### Start the service
```bash
launchctl load ~/Library/LaunchAgents/com.toolkitrag.app.plist
```

### View logs
```bash
# Application logs
tail -f "/Users/paulmcnally/Developai Dropbox/Paul McNally/DROPBOX/ONMAC/PYTHON 2025/aitools/logs/toolkitrag.log"

# Error logs
tail -f "/Users/paulmcnally/Developai Dropbox/Paul McNally/DROPBOX/ONMAC/PYTHON 2025/aitools/logs/toolkitrag.error.log"
```

## Health Checks

### Test if app is running
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status":"healthy"}
```

### Test database connectivity
```bash
curl http://localhost:8000/ready
```

## Accessing the Application

- **Homepage**: http://localhost:8000
- **Login**: http://localhost:8000/login
- **Register**: http://localhost:8000/register
- **API Docs**: http://localhost:8000/docs (Swagger UI)

## Service Configuration

The service configuration is located at:
```
~/Library/LaunchAgents/com.toolkitrag.app.plist
```

### Key settings:
- **Workers**: 2 (can be adjusted in the plist file)
- **Port**: 8000
- **Host**: 127.0.0.1 (localhost only)
- **Environment**: Development (controlled by `.env` file)

## Troubleshooting

### Service won't start
1. Check logs for errors:
   ```bash
   tail -50 "/Users/paulmcnally/Developai Dropbox/Paul McNally/DROPBOX/ONMAC/PYTHON 2025/aitools/logs/toolkitrag.error.log"
   ```

2. Verify PostgreSQL is running:
   ```bash
   brew services list | grep postgresql
   ```

3. Test database connection:
   ```bash
   PGPASSWORD=changeme psql -h localhost -U toolkitrag -d toolkitrag -c "SELECT 1;"
   ```

### Port 8000 already in use
Find and kill the process:
```bash
lsof -ti:8000 | xargs kill -9
```

### Modify service settings
After editing the plist file, reload the service:
```bash
launchctl unload ~/Library/LaunchAgents/com.toolkitrag.app.plist
launchctl load ~/Library/LaunchAgents/com.toolkitrag.app.plist
```

## Uninstalling the Service

To remove the background service:

```bash
# Stop and unload the service
launchctl unload ~/Library/LaunchAgents/com.toolkitrag.app.plist

# Remove the plist file
rm ~/Library/LaunchAgents/com.toolkitrag.app.plist
```

The application files and database will remain intact.

## Database Management

### Backup database
```bash
cd "/Users/paulmcnally/Developai Dropbox/Paul McNally/DROPBOX/ONMAC/PYTHON 2025/aitools"
./deployment/backup-database.sh
```

### Run migrations
```bash
cd "/Users/paulmcnally/Developai Dropbox/Paul McNally/DROPBOX/ONMAC/PYTHON 2025/aitools"
source venv/bin/activate
alembic upgrade head
```

## Notes

- The service runs with 2 workers for better performance
- Logs are automatically rotated (when logrotate is configured)
- The service will automatically restart if it crashes
- Changes to code will NOT auto-reload (unlike `--reload` mode)
- To see code changes, you must restart the service

## Making the Service See Code Changes

If you're actively developing, you have two options:

### Option 1: Manually restart after changes
```bash
launchctl unload ~/Library/LaunchAgents/com.toolkitrag.app.plist && \
launchctl load ~/Library/LaunchAgents/com.toolkitrag.app.plist
```

### Option 2: Run in development mode (temporary)
Stop the service and run manually with auto-reload:
```bash
# Stop the background service
launchctl unload ~/Library/LaunchAgents/com.toolkitrag.app.plist

# Run in foreground with auto-reload
cd "/Users/paulmcnally/Developai Dropbox/Paul McNally/DROPBOX/ONMAC/PYTHON 2025/aitools"
source venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# When done developing, press Ctrl+C and restart the service:
launchctl load ~/Library/LaunchAgents/com.toolkitrag.app.plist
```

---

**Service Created**: 2026-01-23
**Service Version**: 1.0
