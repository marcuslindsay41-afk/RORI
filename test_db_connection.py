import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("✗ DATABASE_URL environment variable is not set (see .env.example)")
    sys.exit(1)

try:
    # Test direct connection
    conn = psycopg2.connect(DATABASE_URL)
    print("✓ Direct psycopg2 connection successful")
    
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    version = cursor.fetchone()
    print(f"PostgreSQL version: {version[0]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"✗ Direct connection failed: {e}")

try:
    # Test SQLAlchemy connection
    from app.models.models import engine, SessionLocal
    print("✓ SQLAlchemy imports successful")
    
    session = SessionLocal()
    print("✓ SQLAlchemy session created")
    
    session.execute("SELECT 1")
    print("✓ SQLAlchemy query executed")
    
    session.close()
    print("✓ SQLAlchemy session closed")
    
except Exception as e:
    print(f"✗ SQLAlchemy connection failed: {e}")
    import traceback
    traceback.print_exc()
