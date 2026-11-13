
import sqlite3
from pathlib import Path
from contextlib import contextmanager

# ==========================================
# 1. DATABASE PATH
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "food_prices.db"


# ==========================================
# 2. DATABASE CONNECTION
# ==========================================

@contextmanager
def get_connection():
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    # Foreign keys қосу
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# ==========================================
# 3. CREATE DATABASE TABLES
# ==========================================

def init_db():

    with get_connection() as conn:

        cursor = conn.cursor()

        # PRODUCTS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                standard_unit TEXT NOT NULL
                    CHECK (standard_unit IN ('kg', 'liter', 'piece')),
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # STORES TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                store_type TEXT NOT NULL,
                region TEXT NOT NULL,
                city TEXT NOT NULL,
                district TEXT,
                address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # PRICE RECORDS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                product_id INTEGER NOT NULL,
                store_id INTEGER NOT NULL,

                package_price REAL NOT NULL CHECK (package_price > 0),
                package_quantity REAL NOT NULL CHECK (package_quantity > 0),

                package_unit TEXT NOT NULL
                    CHECK (package_unit IN ('g', 'kg', 'ml', 'liter', 'piece')),

                normalized_price REAL NOT NULL CHECK (normalized_price > 0),
                normalized_unit TEXT NOT NULL
                    CHECK (normalized_unit IN ('kg', 'liter', 'piece')),

                observation_date DATE NOT NULL,
                source TEXT,
                comment TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (store_id) REFERENCES stores(id),

                UNIQUE (
                    product_id,
                    store_id,
                    package_price,
                    package_quantity,
                    package_unit,
                    observation_date
                )
            )
        """)

        # VERIFICATION RECORDS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                price_record_id INTEGER NOT NULL UNIQUE,

                previous_price REAL,
                current_price REAL NOT NULL,
                percentage_change REAL NOT NULL,

                reason TEXT NOT NULL,

                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (
                        status IN (
                            'pending',
                            'under_review',
                            'verified',
                            'dismissed'
                        )
                    ),

                specialist_comment TEXT,
                final_conclusion TEXT,
                responsible_employee TEXT,

                reviewed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (price_record_id)
                    REFERENCES price_records(id)
            )
        """)

        # USERS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                full_name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,

                role TEXT NOT NULL
                    CHECK (
                        role IN (
                            'monitoring_specialist',
                            'analyst',
                            'manager'
                        )
                    ),

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # INDEXES FOR FASTER SEARCH
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_product
            ON price_records(product_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_store
            ON price_records(store_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_date
            ON price_records(observation_date)
        """)

        print("Database initialized successfully!")


# ==========================================
# 4. ADD PRODUCT
# ==========================================

def add_product(name, category, standard_unit, description=""):

    with get_connection() as conn:

        cursor = conn.execute("""
            INSERT INTO products
            (name, category, standard_unit, description)
            VALUES (?, ?, ?, ?)
        """, (name, category, standard_unit, description))

        return cursor.lastrowid


# ==========================================
# 5. ADD STORE
# ==========================================

def add_store(name, store_type, region, city,
              district="", address=""):

    with get_connection() as conn:

        cursor = conn.execute("""
            INSERT INTO stores
            (name, store_type, region, city, district, address)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, store_type, region, city, district, address))

        return cursor.lastrowid


# ==========================================
# 6. GET ALL PRODUCTS
# ==========================================

def get_products():

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT * FROM products
            ORDER BY name
        """).fetchall()

        return [dict(row) for row in rows]


# ==========================================
# 7. GET ALL STORES
# ==========================================

def get_stores():

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT * FROM stores
            ORDER BY name
        """).fetchall()

        return [dict(row) for row in rows]


# ==========================================
# 8. ADD PRICE RECORD
# ==========================================

def add_price_record(
    product_id,
    store_id,
    package_price,
    package_quantity,
    package_unit,
    normalized_price,
    normalized_unit,
    observation_date,
    source="Manual entry",
    comment=""
):

    with get_connection() as conn:

        cursor = conn.execute("""
            INSERT INTO price_records (
                product_id,
                store_id,
                package_price,
                package_quantity,
                package_unit,
                normalized_price,
                normalized_unit,
                observation_date,
                source,
                comment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product_id,
            store_id,
            package_price,
            package_quantity,
            package_unit,
            normalized_price,
            normalized_unit,
            observation_date,
            source,
            comment
        ))

        return cursor.lastrowid


# ==========================================
# 9. GET PRICE RECORDS
# ==========================================

def get_price_records():

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT
                p.id,
                pr.name AS product_name,
                s.name AS store_name,
                s.city,
                p.package_price,
                p.package_quantity,
                p.package_unit,
                p.normalized_price,
                p.normalized_unit,
                p.observation_date,
                p.source

            FROM price_records p

            JOIN products pr ON p.product_id = pr.id
            JOIN stores s ON p.store_id = s.id

            ORDER BY p.observation_date DESC
        """).fetchall()

        return [dict(row) for row in rows]


# ==========================================
# 10. ADD VERIFICATION RECORD
# ==========================================

def add_verification_record(
    price_record_id,
    previous_price,
    current_price,
    percentage_change,
    reason
):

    with get_connection() as conn:

        cursor = conn.execute("""
            INSERT INTO verification_records (
                price_record_id,
                previous_price,
                current_price,
                percentage_change,
                reason
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            price_record_id,
            previous_price,
            current_price,
            percentage_change,
            reason
        ))

        return cursor.lastrowid


# ==========================================
# 11. INITIALIZE DATABASE
# ==========================================

if __name__ == "__main__":
    init_db()
