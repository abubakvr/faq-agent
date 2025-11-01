"""
Database migration system for automatic schema updates.
Runs migrations on startup to ensure database schema matches the models.
"""

import os
import importlib.util
from pathlib import Path
import psycopg2
from urllib.parse import quote_plus
from dotenv import load_dotenv, find_dotenv

# Load environment variables
_dotenv_path = find_dotenv(usecwd=True)
if _dotenv_path:
    load_dotenv(_dotenv_path)
else:
    load_dotenv()

# Database connection
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Validate required database environment variables
if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD]):
    missing = [key for key, value in {
        "DB_HOST": DB_HOST,
        "DB_PORT": DB_PORT,
        "DB_NAME": DB_NAME,
        "DB_USER": DB_USER,
        "DB_PASSWORD": DB_PASSWORD
    }.items() if not value]
    raise RuntimeError(f"Missing required database environment variables: {', '.join(missing)}")

# URL-encode password to handle special characters
def get_db_connection():
    """Get a direct psycopg2 connection for migrations"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


def create_migrations_table(connection):
    """Create the migrations tracking table if it doesn't exist"""
    cursor = connection.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                migration_name VARCHAR(255) UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()
    finally:
        cursor.close()


def get_applied_migrations(connection):
    """Get list of already applied migrations"""
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT migration_name FROM schema_migrations ORDER BY id")
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()


def mark_migration_applied(connection, migration_name):
    """Mark a migration as applied"""
    cursor = connection.cursor()
    try:
        cursor.execute("""
            INSERT INTO schema_migrations (migration_name) 
            VALUES (%s) 
            ON CONFLICT (migration_name) DO NOTHING
        """, (migration_name,))
        connection.commit()
    finally:
        cursor.close()


def load_migration_module(migration_file):
    """Dynamically load a migration file"""
    spec = importlib.util.spec_from_file_location("migration", migration_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migrations():
    """Run all pending migrations"""
    # Get migrations directory relative to project root (parent of scripts)
    migrations_dir = Path(__file__).parent.parent / "migrations"
    
    if not migrations_dir.exists():
        print("Migrations directory not found, skipping migrations")
        return
    
    # Get all migration files sorted by name
    migration_files = sorted(migrations_dir.glob("*.py"))
    migration_files = [f for f in migration_files if f.name != "__init__.py"]
    
    if not migration_files:
        print("No migration files found")
        return
    
    print("Running database migrations...")
    
    connection = get_db_connection()
    try:
        # Create migrations tracking table
        create_migrations_table(connection)
        
        # Get applied migrations
        applied = set(get_applied_migrations(connection))
        
        # Run pending migrations
        ran_any = False
        for migration_file in migration_files:
            migration_name = migration_file.stem
            
            if migration_name in applied:
                print(f"  ⊗ Skipping {migration_name} (already applied)")
                continue
            
            print(f"  → Running {migration_name}...")
            try:
                migration_module = load_migration_module(migration_file)
                
                if not hasattr(migration_module, 'upgrade'):
                    print(f"    ✗ ERROR: {migration_name} does not have an 'upgrade' function")
                    continue
                
                migration_module.upgrade(connection)
                mark_migration_applied(connection, migration_name)
                print(f"    ✓ {migration_name} completed successfully")
                ran_any = True
            except Exception as e:
                print(f"    ✗ ERROR in {migration_name}: {e}")
                connection.rollback()
                raise
        
        if not ran_any:
            print("  ✓ All migrations are up to date")
        else:
            print("✓ Migration process completed")
    finally:
        connection.close()


if __name__ == "__main__":
    run_migrations()

