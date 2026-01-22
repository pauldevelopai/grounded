#!/usr/bin/env python3
"""
Setup script for local PostgreSQL database without Docker.

This script helps you set up the toolkitrag database and user.
Run this after you've configured PostgreSQL authentication.
"""

import sys
import subprocess
import os

def run_command(cmd, description, check=True):
    """Run a shell command and print the result."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    print(f"Command: {cmd}\n")

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr, file=sys.stderr)

    if check and result.returncode != 0:
        print(f"\n❌ Failed: {description}")
        return False
    elif result.returncode == 0:
        print(f"\n✅ Success: {description}")
        return True
    else:
        print(f"\n⚠️  Warning: {description} (non-zero exit code but continuing)")
        return True

def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║  ToolkitRAG Local Database Setup                         ║
╚══════════════════════════════════════════════════════════╝

This script will help you set up the local PostgreSQL database.

PREREQUISITES:
1. PostgreSQL 15+ is installed and running
2. You can connect to PostgreSQL as a superuser (postgres)
3. You have the superuser password ready

""")

    # Check if PostgreSQL is running
    if not run_command("pg_isready -h localhost", "Check if PostgreSQL is running", check=False):
        print("\n❌ PostgreSQL is not running!")
        print("Please start PostgreSQL first:")
        print("  brew services start postgresql@15")
        print("  OR")
        print("  sudo /Library/PostgreSQL/15/bin/pg_ctl start -D /Library/PostgreSQL/15/data")
        sys.exit(1)

    print("\n" + "="*60)
    print("  PostgreSQL Setup Methods")
    print("="*60)
    print("""
Choose how you want to set up the database:

1. I have the postgres user password (recommended)
2. I'll set it up manually using pgAdmin or other tool
3. Skip database setup (already done)

""")

    choice = input("Enter choice (1-3): ").strip()

    if choice == "1":
        print("\n📝 You'll be prompted for the postgres password in the next step...")
        input("Press Enter to continue...")

        # Create SQL file if it doesn't exist
        sql_file = "setup_db.sql"
        if not os.path.exists(sql_file):
            print(f"❌ {sql_file} not found!")
            sys.exit(1)

        cmd = f"psql -U postgres -f {sql_file}"
        print(f"\nRunning: {cmd}")
        print("(You'll be prompted for the postgres user password)\n")

        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            print("\n❌ Database setup failed!")
            print("Please check the error above and try again.")
            print("\nAlternatively, use Option 2 to set up manually.")
            sys.exit(1)

    elif choice == "2":
        print("\n📋 Manual Setup Instructions:")
        print("""
Please run these SQL commands as a PostgreSQL superuser:

    CREATE USER toolkitrag WITH PASSWORD 'changeme';
    CREATE DATABASE toolkitrag OWNER toolkitrag;
    \\c toolkitrag
    CREATE EXTENSION vector;
    GRANT ALL ON SCHEMA public TO toolkitrag;

You can use:
  - pgAdmin (GUI tool)
  - psql command line: psql -U postgres
  - Any other PostgreSQL client

""")
        input("Press Enter once you've completed the manual setup...")

    elif choice == "3":
        print("\n⏭️  Skipping database setup...")
    else:
        print("\n❌ Invalid choice!")
        sys.exit(1)

    # Test database connection
    print("\n" + "="*60)
    print("  Testing Database Connection")
    print("="*60)

    test_cmd = "PGPASSWORD=changeme psql -h localhost -U toolkitrag -d toolkitrag -c 'SELECT version();'"
    if not run_command(test_cmd, "Test database connection"):
        print("\n❌ Could not connect to the database!")
        print("Please verify:")
        print("  1. Database 'toolkitrag' exists")
        print("  2. User 'toolkitrag' exists with password 'changeme'")
        print("  3. User has proper permissions")
        sys.exit(1)

    # Check for vector extension
    print("\n" + "="*60)
    print("  Checking pgvector Extension")
    print("="*60)

    vector_cmd = "PGPASSWORD=changeme psql -h localhost -U toolkitrag -d toolkitrag -c '\\dx vector'"
    if not run_command(vector_cmd, "Check for pgvector extension", check=False):
        print("\n⚠️  pgvector extension might not be installed properly")
        print("Try creating it manually:")
        print("  PGPASSWORD=changeme psql -h localhost -U toolkitrag -d toolkitrag -c 'CREATE EXTENSION vector;'")

    # Update .env file
    print("\n" + "="*60)
    print("  Updating .env File")
    print("="*60)

    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            content = f.read()

        # Replace db with localhost in DATABASE_URL
        new_content = content.replace(
            "DATABASE_URL=postgresql://toolkitrag:changeme@db:5432/toolkitrag",
            "DATABASE_URL=postgresql://toolkitrag:changeme@localhost:5432/toolkitrag"
        )

        if new_content != content:
            with open(env_file, 'w') as f:
                f.write(new_content)
            print("✅ Updated DATABASE_URL in .env file (changed 'db' to 'localhost')")
        else:
            print("ℹ️  .env file already configured for local database")
    else:
        print("⚠️  .env file not found - you may need to create it")

    # Install Python dependencies
    print("\n" + "="*60)
    print("  Python Dependencies")
    print("="*60)
    print("\nDo you want to install Python dependencies now?")
    print("(This will run: pip install -r requirements.txt)")

    if input("Install dependencies? (y/n): ").strip().lower() == 'y':
        if not run_command("pip install -r requirements.txt", "Install Python dependencies"):
            print("\n⚠️  Dependency installation had issues. You may need to fix them manually.")
    else:
        print("\n⏭️  Skipping dependency installation")
        print("Run manually later: pip install -r requirements.txt")

    # Run migrations
    print("\n" + "="*60)
    print("  Database Migrations")
    print("="*60)
    print("\nDo you want to run database migrations now?")
    print("(This will run: alembic upgrade head)")

    if input("Run migrations? (y/n): ").strip().lower() == 'y':
        if not run_command("alembic upgrade head", "Run database migrations"):
            print("\n⚠️  Migrations had issues. Check the errors above.")
        else:
            print("\n✅ All migrations completed successfully!")
    else:
        print("\n⏭️  Skipping migrations")
        print("Run manually later: alembic upgrade head")

    # Final summary
    print("\n" + "="*60)
    print("  Setup Complete!")
    print("="*60)
    print("""
✅ Next Steps:

1. Start the application:
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

2. Open your browser:
   http://localhost:8000

3. Run tests:
   pytest tests/ -v

4. Create a user account:
   http://localhost:8000/auth/register

5. Ingest toolkit documents (if needed):
   python scripts/ingest.py

For more details, see LOCAL_SETUP.md

Happy coding! 🚀
""")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
