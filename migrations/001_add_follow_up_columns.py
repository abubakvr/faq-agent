"""
Migration 001: Add follow_up_question and previous_conversation_id columns to conversations table
"""


def upgrade(connection):
    """Add the new columns to the conversations table"""
    cursor = connection.cursor()
    try:
        # Check if conversations table exists, create it if not
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'conversations'
            )
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            print("  → Creating conversations table...")
            cursor.execute("""
                CREATE TABLE conversations (
                    id SERIAL PRIMARY KEY,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create indexes (matching SQLAlchemy model)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_conversations_id ON conversations(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_conversations_question ON conversations(question)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_conversations_created_at ON conversations(created_at)")
            print("  ✓ Created conversations table")
        
        # Check if columns exist before adding
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='conversations' AND column_name='follow_up_question'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE conversations 
                ADD COLUMN follow_up_question TEXT
            """)
            print("  ✓ Added column: follow_up_question")
        else:
            print("  - Column follow_up_question already exists, skipping")
        
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='conversations' AND column_name='previous_conversation_id'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE conversations 
                ADD COLUMN previous_conversation_id INTEGER
            """)
            print("  ✓ Added column: previous_conversation_id")
        else:
            print("  - Column previous_conversation_id already exists, skipping")
        
        # Add index for previous_conversation_id if it doesn't exist
        cursor.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename='conversations' AND indexname='idx_conversations_previous_id'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                CREATE INDEX idx_conversations_previous_id 
                ON conversations(previous_conversation_id)
            """)
            print("  ✓ Added index: idx_conversations_previous_id")
        else:
            print("  - Index idx_conversations_previous_id already exists, skipping")
        
        connection.commit()
    except Exception as e:
        connection.rollback()
        raise
    finally:
        cursor.close()


def downgrade(connection):
    """Remove the columns (if needed for rollback)"""
    cursor = connection.cursor()
    try:
        cursor.execute("DROP INDEX IF EXISTS idx_conversations_previous_id")
        cursor.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS previous_conversation_id")
        cursor.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS follow_up_question")
        connection.commit()
    except Exception as e:
        connection.rollback()
        raise
    finally:
        cursor.close()

