# 🚀 Grounded - Quick Start Guide

## ✅ Your App is Running!

Your application is running as a **background service** on macOS. Just refresh your browser!

---

## 🔑 Admin Login

**URL:** http://localhost:8000/login

```
Email:    admin@local.com
Password: admin123
```

---

## 📍 All Available Routes

### Public Pages
- **Homepage:** http://localhost:8000
- **Login:** http://localhost:8000/login
- **Register:** http://localhost:8000/register
- **Health Check:** http://localhost:8000/health

### Authenticated Pages (Login Required)
- **Chat (Toolkit):** http://localhost:8000/toolkit
- **Browse Documents:** http://localhost:8000/browse  
- **Strategy Builder:** http://localhost:8000/strategy

### Admin Pages (Admin Login Required)
- **Admin Dashboard:** http://localhost:8000/admin
- **User Management:** http://localhost:8000/admin/users
- **Document Management:** http://localhost:8000/admin/documents
- **Upload Documents:** http://localhost:8000/admin/documents/upload
- **Analytics:** http://localhost:8000/admin/analytics

### API Endpoints
- **API Docs (Swagger):** http://localhost:8000/docs
- **API Search:** http://localhost:8000/api/search
- **API Answer:** http://localhost:8000/api/answer

---

## 🛠️ Service Management

### Check if Running
```bash
launchctl list | grep grounded
curl http://localhost:8000/health
```

### Restart Service (After Code Changes)
```bash
launchctl unload ~/Library/LaunchAgents/com.grounded.app.plist && \
launchctl load ~/Library/LaunchAgents/com.grounded.app.plist
```

### Stop Service
```bash
launchctl unload ~/Library/LaunchAgents/com.grounded.app.plist
```

### Start Service
```bash
launchctl load ~/Library/LaunchAgents/com.grounded.app.plist
```

### View Logs
```bash
tail -f "/Users/paulmcnally/Developai Dropbox/Paul McNally/DROPBOX/ONMAC/PYTHON 2025/aitools/logs/grounded.log"
```

---

## 💻 Development Mode (Auto-Reload on Save)

If you're actively coding and want the app to **automatically reload** when you save files:

```bash
# 1. Stop the background service
launchctl unload ~/Library/LaunchAgents/com.grounded.app.plist

# 2. Navigate to project
cd "/Users/paulmcnally/Developai Dropbox/Paul McNally/DROPBOX/ONMAC/PYTHON 2025/aitools"

# 3. Activate virtual environment
source venv/bin/activate

# 4. Run with auto-reload
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 5. Press Ctrl+C to stop when done, then restart background service:
launchctl load ~/Library/LaunchAgents/com.grounded.app.plist
```

---

## 🗄️ Database Management

### Connect to Database
```bash
PGPASSWORD=changeme psql -h localhost -U toolkitrag -d toolkitrag
```

### Check Tables
```sql
\dt
```

### View Users
```sql
SELECT email, username, is_admin FROM users;
```

### Create Another Admin User
```bash
cd "/Users/paulmcnally/Developai Dropbox/Paul McNally/DROPBOX/ONMAC/PYTHON 2025/aitools"
PGPASSWORD=changeme psql -h localhost -U toolkitrag -d toolkitrag << 'EOF'
INSERT INTO users (email, username, hashed_password, is_admin, created_at)
VALUES (
    'your@email.com',
    'yourusername',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5aq2.MlBGxlqK',
    true,
    NOW()
)
ON CONFLICT (email) DO NOTHING;
EOF
# Password is: admin123
```

---

## 📦 What's Available

### Features Implemented
- ✅ User Authentication (login/register/logout)
- ✅ Admin Panel with user management
- ✅ Document upload and ingestion
- ✅ RAG (Retrieval Augmented Generation) chat
- ✅ Document browsing by section
- ✅ Strategy planning wizard
- ✅ Feedback system
- ✅ Analytics dashboard
- ✅ Vector search with PostgreSQL + pgvector
- ✅ OpenAI GPT-4 integration

### Navigation
Once logged in, you'll see the navigation bar with:
- **Chat** - Ask questions about your documents
- **Browse** - Browse ingested documents by section
- **Strategy** - Create strategic plans
- **Admin** - (Admin users only) Manage system

---

## 🔧 Common Tasks

### Upload a Document
1. Login as admin (admin@local.com / admin123)
2. Go to http://localhost:8000/admin/documents/upload
3. Select a `.docx` file
4. Enter a version tag (e.g., "v1.0")
5. Click "Upload & Ingest"

### Ask Questions
1. Login with any account
2. Go to http://localhost:8000/toolkit
3. Type your question
4. Get AI-powered answers with citations!

### View All Documents
1. Login
2. Go to http://localhost:8000/browse
3. Browse by section headings

---

## ⚠️ Troubleshooting

### App Not Loading?
```bash
# Check if service is running
launchctl list | grep grounded

# Check PostgreSQL
brew services list | grep postgresql

# Restart everything
launchctl unload ~/Library/LaunchAgents/com.grounded.app.plist
launchctl load ~/Library/LaunchAgents/com.grounded.app.plist
```

### Can't Login?
Make sure you created the admin user (see top of this document).

### Port 8000 Already in Use?
```bash
# Find and kill the process
lsof -ti:8000 | xargs kill -9

# Restart service
launchctl load ~/Library/LaunchAgents/com.grounded.app.plist
```

---

## 🎯 Quick Test

**Is everything working?**

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status":"healthy"}

# Visit homepage
open http://localhost:8000

# Login as admin
open http://localhost:8000/login
```

---

**Your app is ready! Start at:** http://localhost:8000
