"""
Migration 001: Add follow_up_question and previous_conversation_id columns to conversations table
"""


def upgrade(connection):
    """Add the new columns to the conversations table"""
    cursor = connection.cursor()
    try:
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

