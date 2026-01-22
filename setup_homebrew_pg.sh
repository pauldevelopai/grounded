#!/bin/bash
# Setup script for Homebrew PostgreSQL

set -e  # Exit on error

echo "=========================================="
echo "  Setting up Homebrew PostgreSQL"
echo "=========================================="

# Define paths
PG_BIN="/opt/homebrew/opt/postgresql@15/bin"
PG_DATA="/opt/homebrew/var/postgresql@15"

# Stop old PostgreSQL if running
echo ""
echo "Stopping old PostgreSQL..."
sudo /Library/PostgreSQL/15/bin/pg_ctl stop -D /Library/PostgreSQL/15/data 2>/dev/null || echo "Old PostgreSQL already stopped"

# Initialize database if needed
if [ ! -d "$PG_DATA" ]; then
    echo ""
    echo "Initializing PostgreSQL database..."
    $PG_BIN/initdb -D $PG_DATA
else
    echo ""
    echo "PostgreSQL database already initialized"
fi

# Start PostgreSQL in background
echo ""
echo "Starting PostgreSQL..."
$PG_BIN/pg_ctl -D $PG_DATA -l /opt/homebrew/var/log/postgresql@15.log start

# Wait for PostgreSQL to start
echo "Waiting for PostgreSQL to start..."
sleep 3

# Create database and user
echo ""
echo "Creating database and user..."
$PG_BIN/createdb toolkitrag 2>/dev/null || echo "Database already exists"
$PG_BIN/psql -d toolkitrag -c "CREATE USER toolkitrag WITH PASSWORD 'changeme';" 2>/dev/null || echo "User already exists"
$PG_BIN/psql -d toolkitrag -c "GRANT ALL PRIVILEGES ON DATABASE toolkitrag TO toolkitrag;"
$PG_BIN/psql -d toolkitrag -c "CREATE EXTENSION IF NOT EXISTS vector;"
$PG_BIN/psql -d toolkitrag -c "GRANT ALL ON SCHEMA public TO toolkitrag;"

# Test connection
echo ""
echo "Testing connection..."
PGPASSWORD=changeme $PG_BIN/psql -h localhost -U toolkitrag -d toolkitrag -c "SELECT version();"

echo ""
echo "=========================================="
echo "  ✅ PostgreSQL setup complete!"
echo "=========================================="
echo ""
echo "PostgreSQL is now running on localhost:5432"
echo "Database: toolkitrag"
echo "User: toolkitrag"
echo "Password: changeme"
echo ""
