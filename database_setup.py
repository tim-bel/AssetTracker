import sqlite3

def setup_database():
    """
    Creates the SQLite database and the assets table with updated columns.
    """
    try:
        # Connect to the database (this will create the file if it doesn't exist)
        conn = sqlite3.connect('assets.db')
        cursor = conn.cursor()

        # SQL statement to create the 'assets' table with the new columns
        create_table_query = """
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type TEXT NOT NULL,
            name TEXT NOT NULL,
            serial_or_license_key TEXT,
            purchase_date TEXT,
            warranty_or_sub_start TEXT,
            warranty_or_sub_end TEXT,
            location TEXT,
            vendor TEXT,
            bought_at TEXT,
            notes TEXT
        );
        """
        
        # Execute the SQL statement
        cursor.execute(create_table_query)
        
        # Commit the changes and close the connection
        conn.commit()
        print("Database 'assets.db' and table 'assets' created successfully with updated schema.")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    # Run the setup function when the script is executed directly
    setup_database()
