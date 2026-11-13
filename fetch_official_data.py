
from pathlib import Path
from datetime import datetime
import requests
import pandas as pd


# ==========================================
# ЖОБА БАПТАУЛАРЫ
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "raw"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# ҰЛТТЫҚ СТАТИСТИКА БЮРОСЫНЫҢ ФАЙЛДАРЫ
# ==========================================

SOURCES = {
    "kyzylorda_retail": {
        "url": "https://stat.gov.kz/api/iblock/element/region/520443/file/kk/",
        "filename": "kyzylorda_retail_prices.xlsx",
        "description": "Қызылорда облысындағы бөлшек сауда бағалары"
    },

    "kyzylorda_markets": {
        "url": "https://stat.gov.kz/api/iblock/element/region/520391/file/kk/",
        "filename": "kyzylorda_market_prices.xlsx",
        "description": "Қызылорда облысы базарларындағы орташа бағалар"
    },

    "national_food_prices": {
        "url": "https://stat.gov.kz/api/iblock/element/472102/file/kk/",
        "filename": "national_food_prices.xlsx",
        "description": "Қазақстан бойынша ӘМАТ орташа бағалары"
    }
}


# ==========================================
# 1. ФАЙЛДАРДЫ ЖҮКТЕУ
# ==========================================

def download_official_files():

    headers = {
        "User-Agent": "FoodPriceMonitor/1.0"
    }

    for key, source in SOURCES.items():

        file_path = DATA_DIR / source["filename"]

        print("\nЖүктелуде:", source["description"])

        try:
            response = requests.get(
                source["url"],
                headers=headers,
                timeout=40
            )

            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if "html" in content_type:
                print("Қате: сервер Excel орнына HTML қайтарды.")
                continue

            if not response.content.startswith(b"PK"):
                print("Қате: файл Excel форматына ұқсамайды.")
                print("Content-Type:", content_type)
                continue

            file_path.write_bytes(response.content)

            print("Сәтті жүктелді:", file_path)
            print("Файл көлемі:", len(response.content), "байт")

        except requests.RequestException as error:
            print("Жүктеу қатесі:", error)


# ==========================================
# 2. EXCEL ҚҰРЫЛЫМЫН ЗЕРТТЕУ
# ==========================================

def inspect_excel_files():

    print("\n")
    print("=" * 60)
    print("РЕСМИ EXCEL ФАЙЛДАРЫН ТАЛДАУ")
    print("=" * 60)

    files = list(DATA_DIR.glob("*.xlsx"))

    if not files:
        print("Жүктелген Excel файлдары жоқ.")
        return

    for file_path in files:

        print("\n" + "=" * 60)
        print("ФАЙЛ:", file_path.name)
        print("=" * 60)

        try:
            excel = pd.ExcelFile(file_path)

            print("Парақтар:", excel.sheet_names)

            for sheet_name in excel.sheet_names:

                print("\nПАРАҚ:", sheet_name)

                df = pd.read_excel(
                    file_path,
                    sheet_name=sheet_name,
                    header=None
                )

                print("Өлшемі:", df.shape)
                print("\nАлғашқы 15 жол:")

                print(
                    df.head(15).to_string(
                        index=False,
                        header=False
                    )
                )

        except Exception as error:
            print("Оқу қатесі:", error)


# ==========================================
# 3. ІСКЕ ҚОСУ
# ==========================================

if __name__ == "__main__":

    print("FOODPRICE MONITOR")
    print("Ресми деректерді жүктеу басталды.")

    download_official_files()

    inspect_excel_files()

    print("\nДайын!")
