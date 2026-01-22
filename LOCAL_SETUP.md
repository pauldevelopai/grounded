# Local Setup Guide (Without Docker)

This guide will help you set up the application to run locally without Docker.

## Step 1: Set Up PostgreSQL Database

You have PostgreSQL 15 installed. Now you need to create the database and user.

### Option A: Using pgAdmin (GUI)

If you have pgAdmin installed:
1. Open pgAdmin
2. Connect to your PostgreSQL server
3. Right-click on "Databases" → Create → Database
   - Database name: `toolkitrag`
4. Right-click on "Login/Group Roles" → Create → Login/Group Role
   - General tab: Name = `toolkitrag`
   - Definition tab: Password = `changeme`
   - Privileges tab: Check "Can login?"
5. Right-click on the `toolkitrag` database → Query Tool
6. Run: `CREATE EXTENSION vector;`
7. Grant permissions: `GRANT ALL ON SCHEMA public TO toolkitrag;`

### Option B: Using Command Line

Run these commands in your terminal:

```bash
# You may need to enter your PostgreSQL admin password
# If prompted for a password and you don't know it, try using pgAdmin instead

# Connect as postgres superuser (you'll need the postgres user password)
psql -U postgres

# Then run these SQL commands:
CREATE USER toolkitrag WITH PASSWORD 'changeme';
CREATE DATABASE toolkitrag OWNER toolkitrag;
\c toolkitrag
CREATE EXTENSION vector;
GRANT ALL ON SCHEMA public TO toolkitrag;
\q
```

### Option C: Reset PostgreSQL Password (if needed)

If you don't know the postgres user password:

1. Find your `pg_hba.conf` file:
```bash
psql -U postgres -c "SHOW hba_file;"
# Or check: /Library/PostgreSQL/15/data/pg_hba.conf
```

2. Edit `pg_hba.conf` and temporarily change authentication to `trust`:
```
# Find this line:
local   all             postgres                                md5
# Change to:
local   all             postgres                                trust
```

3. Restart PostgreSQL:
```bash
sudo /Library/PostgreSQL/15/bin/pg_ctl restart -D /Library/PostgreSQL/15/data
```

4. Now you can connect without password:
```bash
psql -U postgres -f setup_db.sql
```

5. **IMPORTANT:** Change `pg_hba.conf` back to `md5` and restart PostgreSQL for security.

## Step 2: Verify Database Connection

Test the connection:

```bash
PGPASSWORD=changeme psql -h localhost -U toolkitrag -d toolkitrag -c "SELECT version();"
```

You should see PostgreSQL version information.

## Step 3: Install Python Dependencies

```bash
cd "/Users/paulmcnally/Developai Dropbox/Paul McNally/DROPBOX/ONMAC/PYTHON 2025/aitools"
pip install -r requirements.txt
```

## Step 4: Update .env File

Edit your `.env` file and change the DATABASE_URL from `db` to `localhost`:

```env
DATABASE_URL=postgresql://toolkitrag:changeme@localhost:5432/toolkitrag
```

All other settings can remain the same.

## Step 5: Run Database Migrations

```bash
alembic upgrade head
```

You should see output like:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 001, add users table
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, add toolkit tables
INFO  [alembic.runtime.migration] Running upgrade 002 -> 003, add chat and feedback
INFO  [alembic.runtime.migration] Running upgrade 003 -> 004, add strategy_plans
```

## Step 6: Start the Application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

## Step 7: Access the Application

Open your browser and go to:
- http://localhost:8000

## Step 8: Run Tests

```bash
pytest tests/ -v
```

Or for just the strategy tests:
```bash
pytest tests/test_strategy.py -v
```

## Troubleshooting

### PostgreSQL Connection Issues

If you get "connection refused":
- Check if PostgreSQL is running: `pg_isready`
- Check the port: `lsof -i :5432`
- Restart PostgreSQL if needed

### pgvector Extension Not Available

If you get an error about the vector extension:
```bash
# Install pgvector using Homebrew
brew install pgvector

# Or download and compile from source
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

### Migration Issues

If migrations fail:
```bash
# Check database connection
PGPASSWORD=changeme psql -h localhost -U toolkitrag -d toolkitrag -c "\dt"

# Reset migrations (WARNING: This will drop all tables)
alembic downgrade base
alembic upgrade head
```

### Python Dependencies

If you get import errors:
```bash
# Make sure you're using Python 3.10+
python --version

# Upgrade pip
pip install --upgrade pip

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## Next Steps

Once the application is running:
1. Go to http://localhost:8000/auth/register
2. Create a test user
3. Ingest toolkit documents (if not already done)
4. Test the chat, browse, and strategy features

## Running in Production

For production, you'll want to:
1. Use a stronger password for the database user
2. Set `APP_ENV=production` in `.env`
3. Set `APP_DEBUG=false`
4. Use a proper WSGI server like Gunicorn
5. Set up HTTPS with a reverse proxy (nginx)
6. Configure proper logging
7. Set up database backups
