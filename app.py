from datetime import date
from io import BytesIO
from pathlib import Path
import sqlite3

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
import pandas as pd

import analysis
import database

app = Flask(__name__)
app.secret_key = "foodprice-monitor-secret-key"

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
EXPORT_DIR = BASE_DIR / "exports"

UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)


# ==========================================
# БАСТЫ БЕТ
# ==========================================

@app.route("/")
def home():
    products = database.get_products()
    stores = database.get_stores()
    prices = analysis.get_all_prices()
    alerts = analysis.get_verification_records()

    pending_alerts_count = sum(
        1 for a in alerts if a.get("status") in ("pending", "under_review")
    )

    return render_template(
        "index.html",
        products_count=len(products),
        stores_count=len(stores),
        prices_count=len(prices),
        alerts_count=pending_alerts_count,
        recent_prices=prices[:5],
        recent_alerts=alerts[:5],
    )


# ==========================================
# ТАУАРЛАР
# ==========================================

@app.route("/products", methods=["GET", "POST"])
def products_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        standard_unit = request.form.get("standard_unit", "").strip()
        description = request.form.get("description", "").strip()

        if not name or not category or not standard_unit:
            flash("Тауар атауы, санаты және өлшем бірлігін енгізіңіз.", "error")
            return redirect(url_for("products_page"))

        try:
            database.add_product(
                name,
                category,
                standard_unit,
                description,
            )
            flash("Тауар сәтті қосылды!", "success")

        except sqlite3.IntegrityError:
            flash("Бұл тауар базада бұрыннан бар.", "error")

        except Exception as error:
            flash(f"Қате: {error}", "error")

        return redirect(url_for("products_page"))

    products = database.get_products()
    return render_template("products.html", products=products)


# ==========================================
# ДҮКЕНДЕР
# ==========================================

@app.route("/stores", methods=["GET", "POST"])
def stores_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        store_type = request.form.get("store_type", "").strip()
        region = request.form.get("region", "").strip()
        city = request.form.get("city", "").strip()
        district = request.form.get("district", "").strip()
        address = request.form.get("address", "").strip()

        if not name or not region or not city or not store_type:
            flash("Міндетті өрістерді толтырыңыз.", "error")
            return redirect(url_for("stores_page"))

        try:
            database.add_store(
                name, store_type, region, city, district, address
            )
            flash("Сауда нүктесі қосылды!", "success")

        except Exception as error:
            flash(f"Қате: {error}", "error")

        return redirect(url_for("stores_page"))

    stores = database.get_stores()
    return render_template("stores.html", stores=stores)


# ==========================================
# БАҒАЛАР
# ==========================================

@app.route("/prices", methods=["GET", "POST"])
def prices_page():
    products = database.get_products()
    stores = database.get_stores()

    if request.method == "POST":
        try:
            product_id = int(request.form.get("product_id", 0))
            store_id = int(request.form.get("store_id", 0))
            package_price = float(request.form.get("package_price", 0))
            package_quantity = float(request.form.get("package_quantity", 0))
            package_unit = request.form.get("package_unit", "").strip().lower()
            observation_date = request.form.get("observation_date", "").strip()
            source = request.form.get("source", "Қолмен енгізілді").strip()
            comment = request.form.get("comment", "").strip()

            if not package_unit or not observation_date:
                raise ValueError("Өлшем бірлігі мен бақылау күнін енгізіңіз.")

            if package_price <= 0 or package_quantity <= 0:
                raise ValueError("Баға мен мөлшер нөлден үлкен болуы керек.")

            selected_product = next(
                (p for p in products if p["id"] == product_id),
                None,
            )
            if not selected_product:
                raise ValueError("Тауар табылмады.")

            selected_store = next(
                (s for s in stores if s["id"] == store_id),
                None,
            )
            if not selected_store:
                raise ValueError("Дүкен табылмады.")

            standard_unit = selected_product["standard_unit"]

            normalized_price = analysis.calculate_normalized_price(
                package_price,
                package_quantity,
                package_unit,
                standard_unit,
            )

            conn = database.get_connection()
            try:
                duplicate = conn.execute(
                    """
                    SELECT id FROM price_records
                    WHERE product_id = ?
                      AND store_id = ?
                      AND observation_date = ?
                      AND package_quantity = ?
                      AND package_unit = ?
                    """,
                    (
                        product_id,
                        store_id,
                        observation_date,
                        package_quantity,
                        package_unit,
                    ),
                ).fetchone()
            finally:
                conn.close()

            if duplicate:
                raise ValueError(
                    "Бұл тауар осы дүкенде осы күні және осындай қаптамамен тіркелген."
                )

            database.add_price_record(
                product_id,
                store_id,
                package_price,
                package_quantity,
                package_unit,
                normalized_price,
                standard_unit,
                observation_date,
                source,
                comment,
            )

            flash(
                f"Баға сақталды! Стандартты баға: {normalized_price} тг/{standard_unit}",
                "success",
            )

            # Жаңа бағаны алдыңғы бағамен салыстыру
            analysis.detect_price_changes()

        except Exception as error:
            flash(f"Қате: {error}", "error")

        return redirect(url_for("prices_page"))

    prices = analysis.get_all_prices()

    return render_template(
        "prices.html",
        products=products,
        stores=stores,
        prices=prices,
        today=date.today().isoformat(),
    )


# ==========================================
# АНАЛИТИКА
# ==========================================

@app.route("/analytics")
def analytics_page():
    products = database.get_products()
    prices = analysis.get_all_prices()

    selected_product = request.args.get("product_id", "").strip()
    selected_city = request.args.get("city", "").strip()

    product_id = int(selected_product) if selected_product.isdigit() else None

    statistics = analysis.get_price_statistics(
        product_id=product_id,
        city=selected_city or None,
    )

    cities = sorted({p["city"] for p in prices if p.get("city")})

    # График деректерін таңдалған сүзгіге сай сүзу
    filtered_prices = prices
    if product_id is not None:
        filtered_prices = [
            p for p in filtered_prices if p.get("product_id") == product_id
        ]
    if selected_city:
        filtered_prices = [
            p for p in filtered_prices if p.get("city") == selected_city
        ]

    chart_labels = [p["store_name"] for p in filtered_prices]
    chart_values = [p["normalized_price"] for p in filtered_prices]

    return render_template(
        "analytics.html",
        products=products,
        cities=cities,
        statistics=statistics,
        selected_product=selected_product,
        selected_city=selected_city,
        chart_labels=chart_labels,
        chart_values=chart_values,
    )


# ==========================================
# ТЕКСЕРУ ЖҮЙЕСІ
# ==========================================

@app.route("/verification", methods=["GET", "POST"])
def verification_page():
    if request.method == "POST":
        try:
            verification_id = int(request.form["verification_id"])
            status = request.form["status"].strip()
            specialist_comment = request.form.get("specialist_comment", "").strip()
            final_conclusion = request.form.get("final_conclusion", "").strip()

            analysis.update_verification(
                verification_id,
                status,
                specialist_comment,
                final_conclusion,
            )

            flash("Тексеру нәтижесі сақталды!", "success")

        except Exception as error:
            flash(f"Қате: {error}", "error")

        return redirect(url_for("verification_page"))

    alerts = analysis.get_verification_records()
    return render_template("verification.html", alerts=alerts)


# ==========================================
# EXCEL IMPORT
# ==========================================

@app.route("/import", methods=["GET", "POST"])
def import_page():
    if request.method == "POST":
        file = request.files.get("file")

        if not file or not file.filename:
            flash("Excel файлын таңдаңыз.", "error")
            return redirect(url_for("import_page"))

        if not file.filename.lower().endswith((".xlsx", ".xls")):
            flash("Тек Excel файлын (.xlsx, .xls) жүктеуге болады.", "error")
            return redirect(url_for("import_page"))

        file_path = UPLOAD_DIR / "imported_prices.xlsx"
        file.save(file_path)

        imported = 0
        errors = []

        try:
            df = pd.read_excel(file_path)

            required = [
                "product_id",
                "store_id",
                "package_price",
                "package_quantity",
                "package_unit",
                "observation_date",
            ]

            if not all(column in df.columns for column in required):
                raise ValueError(
                    "Excel бағандары дұрыс емес. Қажетті бағандар: "
                    + ", ".join(required)
                )

            products = database.get_products()
            stores = database.get_stores()
            product_map = {p["id"]: p for p in products}
            store_ids = {s["id"] for s in stores}

            for index, row in df.iterrows():
                try:
                    if pd.isna(row["product_id"]) or pd.isna(row["store_id"]):
                        raise ValueError("product_id немесе store_id бос.")

                    product_id = int(row["product_id"])
                    store_id = int(row["store_id"])

                    if product_id not in product_map:
                        raise ValueError(f"Тауар ID ({product_id}) табылмады.")
                    if store_id not in store_ids:
                        raise ValueError(f"Дүкен ID ({store_id}) табылмады.")

                    package_price = float(row["package_price"])
                    package_quantity = float(row["package_quantity"])

                    if package_price <= 0 or package_quantity <= 0:
                        raise ValueError("Баға мен мөлшер 0-ден үлкен болуы тиіс.")

                    package_unit = str(row["package_unit"]).strip().lower()
                    obs_date = str(row["observation_date"]).strip()[:10]
                    standard_unit = product_map[product_id]["standard_unit"]

                    normalized_price = analysis.calculate_normalized_price(
                        package_price,
                        package_quantity,
                        package_unit,
                        standard_unit,
                    )

                    database.add_price_record(
                        product_id,
                        store_id,
                        package_price,
                        package_quantity,
                        package_unit,
                        normalized_price,
                        standard_unit,
                        obs_date,
                        "Excel импорт",
                        "",
                    )

                    imported += 1

                except Exception as error:
                    errors.append(f"{index + 2}-жол: {error}")

            if imported > 0:
                analysis.detect_price_changes()

            flash(
                f"{imported} жазба импортталды. Қате жолдар саны: {len(errors)}",
                "success" if imported > 0 else "error",
            )

        except Exception as error:
            flash(f"Импорт қатесі: {error}", "error")

        finally:
            if file_path.exists():
                file_path.unlink()

        return render_template("import.html", errors=errors)

    return render_template("import.html", errors=[])


# ==========================================
# EXCEL EXPORT
# ==========================================

@app.route("/export")
def export_page():
    records = analysis.get_all_prices()

    if not records:
        flash("Экспорттау үшін баға жазбалары жоқ.", "error")
        return redirect(url_for("prices_page"))

    df = pd.DataFrame(records)
    output_path = EXPORT_DIR / "foodprice_report.xlsx"
    df.to_excel(output_path, index=False, engine="openpyxl")

    return send_file(
        output_path,
        as_attachment=True,
        download_name="foodprice_report.xlsx",
    )


# ==========================================
# РЕСМИ ДЕРЕКТЕР ЖӘНЕ АНАЛИТИКА
# ==========================================

@app.route("/official-analytics")
def official_analytics():
    connection = database.get_connection()

    try:
        products = connection.execute(
            """
            SELECT DISTINCT product_name
            FROM official_price_records
            ORDER BY product_name
            """
        ).fetchall()

        default_product = products[0][0] if products else ""
        selected_product = request.args.get("product", default_product)
        selected_type = request.args.get("type", "national")

        allowed_types = ["national", "retail", "market"]
        if selected_type not in allowed_types:
            selected_type = "national"

        rows = connection.execute(
            """
            SELECT area, AVG(price), MIN(price), MAX(price), COUNT(*)
            FROM official_price_records
            WHERE product_name = ? AND data_type = ?
            GROUP BY area
            ORDER BY AVG(price) DESC
            """,
            (selected_product, selected_type),
        ).fetchall()

        labels = [row[0] for row in rows]
        average_prices = [round(row[1], 2) for row in rows]

        highest = max(rows, key=lambda row: row[1]) if rows else None
        lowest = min(rows, key=lambda row: row[1]) if rows else None

        return render_template(
            "official_analytics.html",
            products=products,
            selected_product=selected_product,
            selected_type=selected_type,
            rows=rows,
            labels=labels,
            average_prices=average_prices,
            highest=highest,
            lowest=lowest,
        )

    finally:
        connection.close()


@app.route("/export-official")
def export_official():
    connection = database.get_connection()

    try:
        df = pd.read_sql_query(
            """
            SELECT
                product_name AS 'Тауар',
                area AS 'Аймақ',
                price AS 'Бағасы',
                unit AS 'Өлшем бірлігі',
                observation_date AS 'Бақылау күні',
                period AS 'Кезең',
                data_type AS 'Дерек түрі',
                source_title AS 'Дереккөз',
                source_url AS 'Дереккөз сілтемесі'
            FROM official_price_records
            ORDER BY observation_date DESC
            """,
            connection,
        )

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(
                writer,
                index=False,
                sheet_name="Ресми бағалар",
            )

        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="official_food_prices.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    finally:
        connection.close()


@app.route("/official-data")
def official_data():
    connection = database.get_connection()

    try:
        products = connection.execute(
            """
            SELECT DISTINCT product_name
            FROM official_price_records
            ORDER BY product_name
            """
        ).fetchall()

        areas = connection.execute(
            """
            SELECT DISTINCT area
            FROM official_price_records
            ORDER BY area
            """
        ).fetchall()

        selected_product = request.args.get("product", "").strip()
        selected_area = request.args.get("area", "").strip()
        selected_type = request.args.get("type", "").strip()

        sql = """
            SELECT product_name, area, price, unit,
                   observation_date, period, data_type,
                   source_title, source_url
            FROM official_price_records
            WHERE 1=1
        """
        params = []

        if selected_product:
            sql += " AND product_name = ?"
            params.append(selected_product)

        if selected_area:
            sql += " AND area = ?"
            params.append(selected_area)

        if selected_type:
            sql += " AND data_type = ?"
            params.append(selected_type)

        sql += " ORDER BY observation_date DESC, product_name LIMIT 500"

        records = connection.execute(sql, params).fetchall()

        total = connection.execute(
            "SELECT COUNT(*) FROM official_price_records"
        ).fetchone()[0]

        return render_template(
            "official_data.html",
            records=records,
            products=products,
            areas=areas,
            selected_product=selected_product,
            selected_area=selected_area,
            selected_type=selected_type,
            total=total,
        )

    finally:
        connection.close()


# ==========================================
# 404 ҚАТЕ БЕТІ
# ==========================================

@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


# ==========================================
# SERVER START
# ==========================================

if __name__ == "__main__":
    database.init_db()
    app.run(debug=True)