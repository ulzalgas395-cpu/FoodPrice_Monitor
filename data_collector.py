
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def import_prices_from_excel(file_path):
    """
    Excel баға файлын оқиды.
    Міндетті бағандар:
    product_id, store_id, package_price, package_quantity,
    package_unit, observation_date
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError("Excel файлы табылмады.")

    df = pd.read_excel(file_path)

    required_columns = [
        "product_id",
        "store_id",
        "package_price",
        "package_quantity",
        "package_unit",
        "observation_date"
    ]

    missing = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            "Excel файлында мына бағандар жоқ: "
            + ", ".join(missing)
        )

    return df


def export_prices_to_excel(records, output_path):
    """Баға жазбаларын Excel форматына сақтайды."""

    df = pd.DataFrame(records)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_excel(output_path, index=False)

    return output_path
