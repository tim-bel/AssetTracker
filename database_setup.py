import sqlite3

def setup_database():
    """
    Creates the SQLite database and the assets table, adding new columns if they don't exist.
    """
    try:
        conn = sqlite3.connect('assets.db')
        cursor = conn.cursor()

        create_table_query = """
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type TEXT NOT NULL,
            name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            serial_or_license_key TEXT,
            purchase_date TEXT,
            purchase_price REAL,
            warranty_or_sub_start TEXT,
            warranty_or_sub_end TEXT,
            location TEXT,
            vendor TEXT,
            bought_at TEXT,
            notes TEXT,
            barcode TEXT,
            manufacturer TEXT,
            model TEXT,
            description TEXT,
            image_url TEXT,
            -- Fields for Insurance Use Case
            rcv REAL,                         -- Replacement Cost Value
            useful_life_years INTEGER,        -- Expected useful life in years
            acv_override REAL                 -- Manual ACV override
        );
        """
        cursor.execute(create_table_query)

        columns_to_add = {
            "purchase_price": "REAL",
            "barcode": "TEXT",
            "manufacturer": "TEXT",
            "model": "TEXT",
            "description": "TEXT",
            "image_url": "TEXT",
            "quantity": "INTEGER DEFAULT 1",
            "rcv": "REAL",
            "useful_life_years": "INTEGER",
            "acv_override": "REAL"
        }

        cursor.execute("PRAGMA table_info(assets)")
        existing_columns = [row[1] for row in cursor.fetchall()]

        for column, col_type_full in columns_to_add.items():
            if column not in existing_columns:
                try:
                    col_type = col_type_full.split(" DEFAULT")[0]
                    cursor.execute(f"ALTER TABLE assets ADD COLUMN {column} {col_type}")
                    print(f"Column '{column}' added to 'assets' table.")
                    if "DEFAULT 1" in col_type_full and column == "quantity":
                        cursor.execute(f"UPDATE assets SET {column} = 1 WHERE {column} IS NULL")
                        print(f"Default value set for new column '{column}' where it was NULL.")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        print(f"Column '{column}' already exists in 'assets' table (detected by ALTER).")
                    else:
                        raise e

        conn.commit()
        print("Database 'assets.db' and table 'assets' schema checked/updated successfully for insurance features.")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    setup_database()
