#!/bin/bash

# ToolkitRAG Database Backup Script
# Schedule with cron: 0 2 * * * /opt/toolkitrag/deployment/backup-database.sh

set -e

# Configuration
BACKUP_DIR="/opt/toolkitrag/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/toolkitrag_$DATE.sql.gz"
RETENTION_DAYS=30

# Load database URL from .env
if [ -f /etc/toolkitrag/.env ]; then
    export $(grep -v '^#' /etc/toolkitrag/.env | grep DATABASE_URL | xargs)
else
    echo "ERROR: /etc/toolkitrag/.env not found"
    exit 1
fi

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Create backup
echo "$(date): Starting database backup..."

pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"

# Check if backup was successful
if [ $? -eq 0 ] && [ -f "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "$(date): Backup successful: $BACKUP_FILE ($BACKUP_SIZE)"

    # Delete old backups
    find "$BACKUP_DIR" -name "toolkitrag_*.sql.gz" -mtime +$RETENTION_DAYS -delete
    echo "$(date): Deleted backups older than $RETENTION_DAYS days"

    # Optional: Upload to S3 (uncomment and configure)
    # if command -v aws >/dev/null 2>&1; then
    #     aws s3 cp "$BACKUP_FILE" s3://your-bucket/backups/database/ --storage-class STANDARD_IA
    #     echo "$(date): Uploaded to S3"
    # fi

    # Optional: Upload to Backblaze B2 (uncomment and configure)
    # if command -v b2 >/dev/null 2>&1; then
    #     b2 upload-file your-bucket-name "$BACKUP_FILE" "backups/database/$(basename $BACKUP_FILE)"
    #     echo "$(date): Uploaded to Backblaze B2"
    # fi

    exit 0
else
    echo "$(date): ERROR: Backup failed!"
    exit 1
fi
