#!/usr/bin/env python3
"""Create or update admin user for easy access."""
from sqlalchemy.orm import Session
from app.db import SessionLocal, engine
from app.models.user import User
from app.services.auth import create_user
from app.auth.password import get_password_hash

def create_admin_user():
    """Create or update admin user with easy credentials."""
    db = SessionLocal()
    
    try:
        # Easy admin credentials
        email = "admin@local.com"
        username = "admin"
        password = "admin123"  # Easy to remember for local dev
        
        # Check if user exists
        existing_user = db.query(User).filter(User.email == email).first()
        
        if existing_user:
            print(f"✓ Admin user already exists: {email}")
            # Update to ensure they're admin
            if not existing_user.is_admin:
                existing_user.is_admin = True
                db.commit()
                print(f"✓ Promoted {email} to admin")
            
            # Update password in case it changed
            existing_user.password_hash = get_password_hash(password)
            db.commit()
            print(f"✓ Password updated for {email}")
        else:
            # Create new admin user
            user = User(
                email=email,
                username=username,
                password_hash=get_password_hash(password),
                is_admin=True
            )
            db.add(user)
            db.commit()
            print(f"✓ Created admin user: {email}")
        
        print("\n" + "="*60)
        print("ADMIN LOGIN CREDENTIALS")
        print("="*60)
        print(f"URL:      http://localhost:8000/login")
        print(f"Email:    {email}")
        print(f"Password: {password}")
        print("="*60)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()
