#!/usr/bin/env python3
"""
Database migration script to add new columns (summary, images) to the Article model.
Run this after updating the code to add the new features.
"""

import sqlite3
import os

DB_PATH = "instance/articles.db"


def migrate_database():
    """Add summary and images columns to the article table."""
    
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("The database will be created automatically when you run the app.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check current columns
    cursor.execute("PRAGMA table_info(article)")
    columns = [col[1] for col in cursor.fetchall()]
    
    print(f"Current columns: {columns}")
    
    # Add summary column if it doesn't exist
    if "summary" not in columns:
        print("Adding 'summary' column...")
        cursor.execute("ALTER TABLE article ADD COLUMN summary TEXT DEFAULT ''")
        print("✓ Added summary column")
    else:
        print("✓ Summary column already exists")
    
    # Add images column if it doesn't exist
    if "images" not in columns:
        print("Adding 'images' column...")
        cursor.execute("ALTER TABLE article ADD COLUMN images TEXT DEFAULT ''")
        print("✓ Added images column")
    else:
        print("✓ Images column already exists")
    
    conn.commit()
    conn.close()
    
    print("\nMigration complete!")
    print("You can now run the app with the new features.")


if __name__ == "__main__":
    migrate_database()
