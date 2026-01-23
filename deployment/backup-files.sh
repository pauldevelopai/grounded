#!/bin/bash

# ToolkitRAG File Backup Script
# Schedule with cron: 0 3 * * 0 /opt/toolkitrag/deployment/backup-files.sh (weekly)

set -e

# Configuration
BACKUP_DIR="/opt/toolkitrag/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/uploads_$DATE.tar.gz"
UPLOADS_DIR="/opt/toolkitrag/data/uploads"
RETENTION_DAYS=60

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Create backup
echo "$(date): Starting file backup..."

if [ -d "$UPLOADS_DIR" ]; then
    tar -czf "$BACKUP_FILE" -C /opt/toolkitrag/data uploads

    # Check if backup was successful
    if [ $? -eq 0 ] && [ -f "$BACKUP_FILE" ]; then
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        FILE_COUNT=$(tar -tzf "$BACKUP_FILE" | wc -l)
        echo "$(date): Backup successful: $BACKUP_FILE ($BACKUP_SIZE, $FILE_COUNT files)"

        # Delete old backups
        find "$BACKUP_DIR" -name "uploads_*.tar.gz" -mtime +$RETENTION_DAYS -delete
        echo "$(date): Deleted backups older than $RETENTION_DAYS days"

        # Optional: Upload to S3
        # if command -v aws >/dev/null 2>&1; then
        #     aws s3 cp "$BACKUP_FILE" s3://your-bucket/backups/files/ --storage-class STANDARD_IA
        #     echo "$(date): Uploaded to S3"
        # fi

        # Optional: Upload to Backblaze B2
        # if command -v b2 >/dev/null 2>&1; then
        #     b2 upload-file your-bucket-name "$BACKUP_FILE" "backups/files/$(basename $BACKUP_FILE)"
        #     echo "$(date): Uploaded to Backblaze B2"
        # fi

        exit 0
    else
        echo "$(date): ERROR: Backup failed!"
        exit 1
    fi
else
    echo "$(date): ERROR: Uploads directory not found: $UPLOADS_DIR"
    exit 1
fi
