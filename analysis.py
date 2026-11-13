
import sqlite3
from pathlib import Path
from statistics import median

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "database" / "food_prices.db"


# ==========================================
# 1. БАҒАНЫ СТАНДАРТТЫ ӨЛШЕМГЕ АЙНАЛДЫРУ
# ==========================================

def calculate_normalized_price(
    package_price,
    package_quantity,
    package_unit,
    standard_unit
):
    """
    Қаптаманың бағасын 1 кг, 1 литр немесе 1 дана бағасына айналдырады.
    Мысалы: 900 г = 450 теңге -> 500 теңге/кг.
    """

    package_price = float(package_price)
    package_quantity = float(package_quantity)

    if package_price <= 0 or package_quantity <= 0:
        raise ValueError("Баға мен мөлшер нөлден үлкен болуы керек.")

    package_unit = package_unit.lower()
    standard_unit = standard_unit.lower()

    if standard_unit == "kg":
        if package_unit == "g":
            quantity = package_quantity / 1000
        elif package_unit == "kg":
            quantity = package_quantity
        else:
            raise ValueError("Бұл тауар үшін грамм немесе килограмм енгізіңіз.")

    elif standard_unit == "liter":
        if package_unit == "ml":
            quantity = package_quantity / 1000
        elif package_unit == "liter":
            quantity = package_quantity
        else:
            raise ValueError("Бұл тауар үшін мл немесе литр енгізіңіз.")

    elif standard_unit == "piece":
        if package_unit != "piece":
            raise ValueError("Дана өлшеміндегі тауарға piece енгізіңіз.")
        quantity = package_quantity

    else:
        raise ValueError("Стандартты өлшем дұрыс емес.")

    return round(package_price / quantity, 2)


# ==========================================
# 2. БАЗАМЕН БАЙЛАНЫС
# ==========================================

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ==========================================
# 3. БАҒАЛАРДЫ АЛУ
# ==========================================

def get_all_prices():
    conn = get_connection()

    try:
        rows = conn.execute("""
            SELECT
                pr.id,
                pr.product_id,
                p.name AS product_name,
                p.standard_unit,
                s.name AS store_name,
                s.city,
                s.region,
                pr.package_price,
                pr.package_quantity,
                pr.package_unit,
                pr.normalized_price,
                pr.normalized_unit,
                pr.observation_date
            FROM price_records pr
            JOIN products p ON pr.product_id = p.id
            JOIN stores s ON pr.store_id = s.id
            ORDER BY pr.observation_date DESC
        """).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


# ==========================================
# 4. БАҒАЛАРДЫ СТАТИСТИКАЛЫҚ ТАЛДАУ
# ==========================================

def get_price_statistics(product_id=None, city=None):
    conn = get_connection()

    try:
        query = """
            SELECT
                p.name AS product_name,
                p.standard_unit,
                s.city,
                pr.normalized_price
            FROM price_records pr
            JOIN products p ON pr.product_id = p.id
            JOIN stores s ON pr.store_id = s.id
            WHERE 1=1
        """

        params = []

        if product_id:
            query += " AND p.id = ?"
            params.append(product_id)

        if city:
            query += " AND s.city = ?"
            params.append(city)

        rows = conn.execute(query, params).fetchall()

        if not rows:
            return None

        prices = [row["normalized_price"] for row in rows]

        return {
            "product_name": rows[0]["product_name"],
            "unit": rows[0]["standard_unit"],
            "count": len(prices),
            "minimum": round(min(prices), 2),
            "maximum": round(max(prices), 2),
            "average": round(sum(prices) / len(prices), 2),
            "median": round(median(prices), 2)
        }

    finally:
        conn.close()


# ==========================================
# 5. БАҒАНЫҢ ӨЗГЕРУІН ТЕКСЕРУ
# ==========================================

def detect_price_changes(threshold=15):
    """
    Бір дүкендегі бір тауардың соңғы бағасын
    алдыңғы бағасымен салыстырады.

    Шекті мәннен асқан өзгерістер тексеруге жіберіледі.
    Бұл заң бұзушылық туралы автоматты қорытынды емес.
    """

    conn = get_connection()
    detected = []

    try:
        rows = conn.execute("""
            SELECT
                pr.id,
                pr.product_id,
                pr.store_id,
                p.name AS product_name,
                s.name AS store_name,
                pr.normalized_price,
                pr.observation_date
            FROM price_records pr
            JOIN products p ON pr.product_id = p.id
            JOIN stores s ON pr.store_id = s.id
            ORDER BY pr.product_id, pr.store_id,
                     pr.observation_date ASC, pr.id ASC
        """).fetchall()

        previous_prices = {}

        for row in rows:
            key = (row["product_id"], row["store_id"])
            current_price = float(row["normalized_price"])

            if key in previous_prices:
                previous = previous_prices[key]
                previous_price = previous["price"]

                if previous_price > 0:
                    change = (
                        (current_price - previous_price)
                        / previous_price
                    ) * 100

                    if abs(change) >= threshold:
                        existing = conn.execute("""
                            SELECT id FROM verification_records
                            WHERE price_record_id = ?
                        """, (row["id"],)).fetchone()

                        if not existing:
                            reason = (
                                f"Баға өзгерісі {change:.2f}% "
                                f"(шекті мән: {threshold}%). "
                                "Маман тексеруі қажет."
                            )

                            conn.execute("""
                                INSERT INTO verification_records (
                                    price_record_id,
                                    previous_price,
                                    current_price,
                                    percentage_change,
                                    reason
                                )
                                VALUES (?, ?, ?, ?, ?)
                            """, (
                                row["id"],
                                previous_price,
                                current_price,
                                round(change, 2),
                                reason
                            ))

                        detected.append({
                            "product": row["product_name"],
                            "store": row["store_name"],
                            "previous_price": previous_price,
                            "current_price": current_price,
                            "change": round(change, 2),
                            "date": row["observation_date"]
                        })

            previous_prices[key] = {
                "price": current_price,
                "date": row["observation_date"]
            }

        conn.commit()
        return detected

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ==========================================
# 6. ТЕКСЕРУГЕ ЖІБЕРІЛГЕН ЖАЗБАЛАР
# ==========================================

def get_verification_records():
    conn = get_connection()

    try:
        rows = conn.execute("""
            SELECT
                vr.id,
                vr.price_record_id,
                p.name AS product_name,
                s.name AS store_name,
                s.city,
                vr.previous_price,
                vr.current_price,
                vr.percentage_change,
                vr.reason,
                vr.status,
                vr.specialist_comment,
                vr.final_conclusion,
                vr.created_at
            FROM verification_records vr
            JOIN price_records pr
                ON vr.price_record_id = pr.id
            JOIN products p
                ON pr.product_id = p.id
            JOIN stores s
                ON pr.store_id = s.id
            ORDER BY vr.created_at DESC
        """).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


# ==========================================
# 7. ТЕКСЕРУ НӘТИЖЕСІН ЖАҢАРТУ
# ==========================================

def update_verification(
    verification_id,
    status,
    specialist_comment="",
    final_conclusion=""
):
    allowed_statuses = [
        "pending",
        "under_review",
        "verified",
        "dismissed"
    ]

    if status not in allowed_statuses:
        raise ValueError("Тексеру статусы дұрыс емес.")

    conn = get_connection()

    try:
        conn.execute("""
            UPDATE verification_records
            SET
                status = ?,
                specialist_comment = ?,
                final_conclusion = ?,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            status,
            specialist_comment,
            final_conclusion,
            verification_id
        ))

        conn.commit()

    finally:
        conn.close()


# ==========================================
# 8. ТЕСТ
# ==========================================

if __name__ == "__main__":

    print("=== FOODPRICE MONITOR TEST ===")

    price = calculate_normalized_price(
        package_price=450,
        package_quantity=900,
        package_unit="g",
        standard_unit="kg"
    )

    print("900 г тауардың бағасы:", price, "тг/кг")

    statistics = get_price_statistics()

    if statistics:
        print("\nБаға статистикасы:")
        print(statistics)
    else:
        print("\nБазада әзірге баға жазбалары жоқ.")

    changes = detect_price_changes()

    print("\nТексеруді қажет ететін өзгерістер:", len(changes))
    print("\nТалдау аяқталды.")
