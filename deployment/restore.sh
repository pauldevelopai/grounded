#!/bin/bash

# ToolkitRAG Restore Script
# Usage: ./restore.sh [database|files|all] [backup_file]

set -e

BACKUP_DIR="/opt/toolkitrag/backups"
UPLOADS_DIR="/opt/toolkitrag/data/uploads"

# Load database URL from .env
if [ -f /etc/toolkitrag/.env ]; then
    export $(grep -v '^#' /etc/toolkitrag/.env | grep DATABASE_URL | xargs)
else
    echo "ERROR: /etc/toolkitrag/.env not found"
    exit 1
fi

# Function to list available backups
list_backups() {
    local type=$1
    echo "Available ${type} backups:"
    echo "-------------------------------------------"

    if [ "$type" = "database" ]; then
        ls -lh "$BACKUP_DIR"/toolkitrag_*.sql.gz 2>/dev/null | tail -n 10 || echo "No database backups found"
    elif [ "$type" = "files" ]; then
        ls -lh "$BACKUP_DIR"/uploads_*.tar.gz 2>/dev/null | tail -n 10 || echo "No file backups found"
    fi

    echo "-------------------------------------------"
}

# Function to restore database
restore_database() {
    local backup_file=$1

    if [ ! -f "$backup_file" ]; then
        echo "ERROR: Backup file not found: $backup_file"
        exit 1
    fi

    echo "WARNING: This will REPLACE the current database!"
    echo "Database: $DATABASE_URL"
    echo "Backup: $backup_file"
    echo ""
    read -p "Are you sure? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled"
        exit 0
    fi

    echo ""
    echo "Stopping application..."
    sudo systemctl stop toolkitrag

    echo "Creating pre-restore backup..."
    PRE_RESTORE_BACKUP="$BACKUP_DIR/pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
    pg_dump "$DATABASE_URL" | gzip > "$PRE_RESTORE_BACKUP"
    echo "Pre-restore backup created: $PRE_RESTORE_BACKUP"

    echo "Restoring database..."
    gunzip < "$backup_file" | psql "$DATABASE_URL"

    if [ $? -eq 0 ]; then
        echo "Database restored successfully!"
        echo ""
        echo "Starting application..."
        sudo systemctl start toolkitrag

        echo ""
        echo "Waiting for application to start..."
        sleep 5

        if curl -s http://localhost:8000/health | grep -q "healthy"; then
            echo "✓ Application started successfully"
        else
            echo "✗ Application health check failed"
            echo "Check logs: sudo journalctl -u toolkitrag -n 50"
        fi
    else
        echo "ERROR: Database restore failed!"
        echo "You can restore from pre-restore backup: $PRE_RESTORE_BACKUP"
        exit 1
    fi
}

# Function to restore files
restore_files() {
    local backup_file=$1

    if [ ! -f "$backup_file" ]; then
        echo "ERROR: Backup file not found: $backup_file"
        exit 1
    fi

    echo "WARNING: This will REPLACE uploaded files!"
    echo "Target: $UPLOADS_DIR"
    echo "Backup: $backup_file"
    echo ""
    read -p "Are you sure? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled"
        exit 0
    fi

    echo ""
    echo "Creating pre-restore backup of current files..."
    PRE_RESTORE_BACKUP="$BACKUP_DIR/pre_restore_files_$(date +%Y%m%d_%H%M%S).tar.gz"
    tar -czf "$PRE_RESTORE_BACKUP" -C /opt/toolkitrag/data uploads 2>/dev/null || echo "No existing files to backup"

    echo "Restoring files..."
    rm -rf "$UPLOADS_DIR"/*
    tar -xzf "$backup_file" -C /opt/toolkitrag/data/

    if [ $? -eq 0 ]; then
        echo "Files restored successfully!"

        # Fix permissions
        sudo chown -R deployer:deployer "$UPLOADS_DIR"
        echo "Permissions updated"
    else
        echo "ERROR: File restore failed!"
        echo "You can restore from pre-restore backup: $PRE_RESTORE_BACKUP"
        exit 1
    fi
}

# Main script
case "$1" in
    database)
        if [ -z "$2" ]; then
            list_backups database
            echo ""
            echo "Usage: $0 database <backup_file>"
            echo "Example: $0 database $BACKUP_DIR/toolkitrag_20260123_020000.sql.gz"
            exit 1
        fi
        restore_database "$2"
        ;;

    files)
        if [ -z "$2" ]; then
            list_backups files
            echo ""
            echo "Usage: $0 files <backup_file>"
            echo "Example: $0 files $BACKUP_DIR/uploads_20260123_030000.tar.gz"
            exit 1
        fi
        restore_files "$2"
        ;;

    all)
        if [ -z "$2" ] || [ -z "$3" ]; then
            echo "Usage: $0 all <database_backup> <files_backup>"
            exit 1
        fi
        restore_database "$2"
        restore_files "$3"
        ;;

    *)
        echo "ToolkitRAG Restore Script"
        echo ""
        echo "Usage: $0 [database|files|all] [backup_file(s)]"
        echo ""
        echo "Examples:"
        echo "  $0 database $BACKUP_DIR/toolkitrag_20260123_020000.sql.gz"
        echo "  $0 files $BACKUP_DIR/uploads_20260123_030000.tar.gz"
        echo "  $0 all $BACKUP_DIR/toolkitrag_20260123_020000.sql.gz $BACKUP_DIR/uploads_20260123_030000.tar.gz"
        echo ""
        list_backups database
        echo ""
        list_backups files
        exit 1
        ;;
esac
