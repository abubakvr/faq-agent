# Database Migrations

This directory contains database migration files that automatically update the database schema when needed.

## How It Works

1. **Automatic Execution**: Migrations run automatically on application startup
2. **Tracking**: Applied migrations are tracked in the `schema_migrations` table
3. **Idempotent**: Migrations check if changes already exist before applying them
4. **Safe**: Migrations use transactions and rollback on errors

## Creating a New Migration

1. Create a new file in this directory following the naming pattern:

   ```
   002_your_migration_name.py
   003_another_migration.py
   ```

2. Use this template:

```python
"""
Migration 002: Your migration description
"""


def upgrade(connection):
    """Apply the migration"""
    with connection.cursor() as cursor:
        # Check if change already exists
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='your_table' AND column_name='your_column'
        """)
        if not cursor.fetchone():
            # Apply your changes
            cursor.execute("""
                ALTER TABLE your_table
                ADD COLUMN your_column TYPE
            """)
            print("  ✓ Added column: your_column")
        else:
            print("  - Column your_column already exists, skipping")

    connection.commit()


def downgrade(connection):
    """Rollback the migration (optional)"""
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE your_table DROP COLUMN IF EXISTS your_column")
    connection.commit()
```

## Running Migrations Manually

You can also run migrations manually:

```bash
python migrate.py
```

## Migration Best Practices

1. **Always check if changes exist** before applying them (idempotent)
2. **Use transactions** - migrations are automatically wrapped in transactions
3. **Print progress** - Use print statements to show what's happening
4. **Handle errors gracefully** - Check for existence before modifying
5. **Use descriptive names** - Migration filenames should clearly describe what they do

## Current Migrations

- `001_add_follow_up_columns.py`: Adds `follow_up_question` and `previous_conversation_id` columns to the `conversations` table
