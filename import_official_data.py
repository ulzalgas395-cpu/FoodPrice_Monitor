from datetime import datetime
from pathlib import Path
import sqlite3
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "raw"
DB_DIR = BASE_DIR / "database"
DB_PATH = DB_DIR / "food_prices.db"

# Папкалар жоқ болса автоматты түрде жасау
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "retail": {
        "file": "kyzylorda_retail_prices.xlsx",
        "url": "https://stat.gov.kz/api/iblock/element/region/520443/file/kk/",
        "title": "ҰСБ — Қызылорда облысындағы бөлшек сауда бағалары",
        "period": "2026 жылғы қазан",
        "date": "2026-10-01",
    },
    "market": {
        "file": "kyzylorda_market_prices.xlsx",
        "url": "https://stat.gov.kz/api/iblock/element/region/520391/file/kk/",
        "title": "ҰСБ — Қызылорда облысы базарларындағы орташа бағалар",
        "period": "2026 жылғы қазан",
        "date": "2026-10-01",
    },
    "national": {
        "file": "national_food_prices.xlsx",
        "url": "https://stat.gov.kz/api/iblock/element/472102/file/kk/",
        "title": "ҰСБ — Қазақстан бойынша ӘМАТ орташа бағалары",
        "period": "2026 жылғы 11 қараша",
        "date": "2026-11-11",
    },
}


def clean_number(value):
    """Excel ұяшығынан санды қауіпсіз алу."""
    if pd.isna(value):
        return None

    text = str(value).strip().replace(" ", "").replace(",", ".")

    if text.lower() in ["", "-", "...", "х", "x", "nan"]:
        return None

    try:
        number = float(text)
        if number <= 0:
            return None
        return number
    except ValueError:
        return None


def detect_unit(value):
    """Өлшем бірлігін стандарттау."""
    text = str(value).strip().lower()

    if any(k in text for k in ["кг", "килограмм", "килограм"]):
        return "kg"
    if any(k in text for k in ["л", "литр"]):
        return "liter"
    if any(k in text for k in ["дана", "шт", "штука"]):
        return "piece"

    return "unknown"


def create_table(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS official_price_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            area TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT NOT NULL,
            observation_date TEXT NOT NULL,
            period TEXT,
            data_type TEXT NOT NULL,
            source_title TEXT NOT NULL,
            source_url TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            UNIQUE(product_name, area, observation_date, data_type, source_url)
        )
    """
    )
    connection.commit()


def save_record(connection, product, area, price, unit, source_key):
    source = SOURCES[source_key]

    connection.execute(
        """
        INSERT OR REPLACE INTO official_price_records (
            product_name, area, price, unit,
            observation_date, period, data_type,
            source_title, source_url, imported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            str(product).strip(),
            str(area).strip(),
            price,
            unit,
            source["date"],
            source["period"],
            source_key,
            source["title"],
            source["url"],
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def import_market(connection):
    path = DATA_DIR / SOURCES["market"]["file"]
    df = pd.read_excel(path, sheet_name="1", header=None)

    count = 0
    # 4-жолда аймақтардың атауы, 5-жолдан бастап тауарлар
    for row_index in range(5, len(df)):
        product = df.iloc[row_index, 0]
        unit = detect_unit(df.iloc[row_index, 1])

        if pd.isna(product) or unit == "unknown":
            continue

        for column in range(2, len(df.columns)):
            area = df.iloc[4, column]
            price = clean_number(df.iloc[row_index, column])

            if pd.isna(area) or price is None:
                continue

            save_record(connection, product, area, price, unit, "market")
            count += 1

    return count


def import_retail(connection):
    path = DATA_DIR / SOURCES["retail"]["file"]
    df = pd.read_excel(path, sheet_name="1", header=None)

    count = 0
    current_unit = "unknown"

    # 3-жолда аудандардың атауы, одан кейін тауарлар
    for row_index in range(4, len(df)):
        product = df.iloc[row_index, 0]

        if pd.isna(product):
            continue

        product_text = str(product).strip().lower()

        # Бөлім тақырыбынан өлшем бірлігін анықтау
        if any(k in product_text for k in ["кг", "килограм"]):
            current_unit = "kg"
            continue
        elif "литр" in product_text or "л." in product_text:
            current_unit = "liter"
            continue
        elif any(k in product_text for k in ["дана", "шт"]):
            current_unit = "piece"
            continue

        if current_unit == "unknown":
            continue

        for column in range(1, len(df.columns)):
            area = df.iloc[3, column]
            price = clean_number(df.iloc[row_index, column])

            if pd.isna(area) or price is None:
                continue

            save_record(connection, product, area, price, current_unit, "retail")
            count += 1

    return count


def import_national(connection):
    path = DATA_DIR / SOURCES["national"]["file"]
    df = pd.read_excel(path, sheet_name="5", header=None)

    count = 0

    # 2-жолда қалалар, 3-жолдан бастап тауарлар
    for row_index in range(3, len(df)):
        product = df.iloc[row_index, 0]

        if pd.isna(product):
            continue

        for column in range(2, len(df.columns)):
            city = df.iloc[2, column]
            price = clean_number(df.iloc[row_index, column])

            if pd.isna(city) or price is None:
                continue

            save_record(connection, product, city, price, "kg", "national")
            count += 1

    return count


def main():
    print("=" * 55)
    print("FOODPRICE MONITOR — РЕСМИ ДЕРЕКТЕР ИМПОРТЫ")
    print("=" * 55)

    for source in SOURCES.values():
        file_path = DATA_DIR / source["file"]
        if not file_path.exists():
            print(f"❌ Файл табылмады: {file_path}")
            print(
                f"   (Деректерді '{DATA_DIR}' папкасына жүктеп қойғаныңызға көз жеткізіңіз)"
            )
            return

    connection = sqlite3.connect(DB_PATH)

    try:
        create_table(connection)

        print("\n⏳ Деректерді импорттау жүріп жатыр...")
        market_count = import_market(connection)
        retail_count = import_retail(connection)
        national_count = import_national(connection)

        connection.commit()

        total = market_count + retail_count + national_count

        print("\n✅ Импорт сәтті аяқталды!")
        print(f" • Базар бағалары: {market_count}")
        print(f" • Бөлшек сауда бағалары: {retail_count}")
        print(f" • Қазақстан бойынша бағалар: {national_count}")
        print("-" * 40)
        print(f"📦 Жалпы импортталған жазбалар: {total}")

        print("\n📍 Қызылорда қаласы/облысы бойынша мысалдар:")
        rows = connection.execute(
            """
            SELECT product_name, area, price, unit, period, data_type
            FROM official_price_records
            WHERE area LIKE '%Қызылорда%'
            ORDER BY product_name
            LIMIT 10
        """
        ).fetchall()

        if rows:
            for row in rows:
                print(
                    f" - {row[0]} | {row[1]} | {row[2]} тг/{row[3]} | {row[4]} ({row[5]})"
                )
        else:
            print(
                " (Қызылорда бойынша жазбалар әлі табылмады, сүзгіні немесе аймақ атауын тексеріңіз)"
            )

    except Exception as error:
        connection.rollback()
        print("❌ Импорт кезінде қате орын алды:", error)

    finally:
        connection.close()


if __name__ == "__main__":
    main()