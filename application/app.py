import hashlib
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

import boto3
import pymysql
from botocore.config import Config
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import CSRFProtect
from pymysql.cursors import DictCursor
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash


AWS_CONFIG = Config(
    retries={"total_max_attempts": 4, "mode": "standard"},
    connect_timeout=5,
    read_timeout=10,
    user_agent_appid="cloud-appointment/1.0",
)

TRACKED_ENDPOINTS = {
    "index",
    "stats",
    "login",
    "register",
    "dashboard",
    "profile",
    "appointments",
    "appointment_new",
    "appointment_edit",
}
VISITOR_COOKIE = "portfolio_visitor"


def required_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def load_database_secret():
    aws_session = boto3.Session(region_name=required_env("AWS_REGION"))
    secrets = aws_session.client("secretsmanager", config=AWS_CONFIG)
    response = secrets.get_secret_value(SecretId=required_env("DB_SECRET_ARN"))
    return json.loads(response["SecretString"])


def database_settings(secret):
    return {
        "host": secret.get("host", required_env("DB_HOST")),
        "port": int(secret.get("port", os.environ.get("DB_PORT", "3306"))),
        "user": secret["username"],
        "password": secret["password"],
        "database": secret.get("dbname", required_env("DB_NAME")),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "connect_timeout": 8,
        "read_timeout": 10,
        "write_timeout": 10,
        "ssl": {"ca": required_env("RDS_CA_BUNDLE"), "check_hostname": True},
    }


@contextmanager
def database(app):
    connection = pymysql.connect(**app.config["DATABASE"])
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_schema(app):
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            email VARCHAR(255) NOT NULL,
            display_name VARCHAR(120) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_users_email (email)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            user_id BIGINT UNSIGNED NOT NULL,
            service_name VARCHAR(120) NOT NULL,
            provider_name VARCHAR(120) NOT NULL,
            appointment_at DATETIME NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'Scheduled',
            notes TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_appointments_user_date (user_id, appointment_at),
            CONSTRAINT fk_appointments_user FOREIGN KEY (user_id)
                REFERENCES users (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS visitor_profiles (
            visitor_id CHAR(36) NOT NULL,
            first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            browser_language VARCHAR(32) NULL,
            browser_timezone VARCHAR(80) NULL,
            location_shared BOOLEAN NOT NULL DEFAULT FALSE,
            approximate_latitude DECIMAL(5, 2) NULL,
            approximate_longitude DECIMAL(6, 2) NULL,
            PRIMARY KEY (visitor_id),
            KEY idx_visitor_profiles_last_seen (last_seen)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS visitor_events (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            visitor_id CHAR(36) NOT NULL,
            path VARCHAR(255) NOT NULL,
            referrer_host VARCHAR(255) NULL,
            instance_id VARCHAR(32) NOT NULL,
            availability_zone VARCHAR(32) NOT NULL,
            visited_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_visitor_events_time (visited_at),
            KEY idx_visitor_events_path (path),
            KEY idx_visitor_events_visitor (visitor_id),
            CONSTRAINT fk_visitor_events_profile FOREIGN KEY (visitor_id)
                REFERENCES visitor_profiles (visitor_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ]
    with database(app) as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)


def initialize_schema_with_retry(app):
    """Initialize database objects without coupling process health to RDS startup."""
    delay_seconds = 5
    for attempt in range(1, 13):
        try:
            initialize_schema(app)
            app.config["DATABASE_AVAILABLE"] = True
            app.logger.info("Database schema is ready")
            return
        except pymysql.MySQLError:
            app.config["DATABASE_AVAILABLE"] = False
            app.logger.warning(
                "Database schema initialization attempt %s failed; retrying in %ss",
                attempt,
                delay_seconds,
                exc_info=True,
            )
            time.sleep(delay_seconds)
            delay_seconds = min(delay_seconds * 2, 60)
    app.logger.error("Database schema initialization exhausted all retries")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="Authentication required"), 401
            flash("Sign in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def current_user(app):
    if "user_id" not in session or not app.config["DATABASE_AVAILABLE"]:
        return None
    try:
        with database(app) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, email, display_name, created_at FROM users WHERE id = %s",
                    (session["user_id"],),
                )
                return cursor.fetchone()
    except pymysql.MySQLError:
        app.logger.warning("Current-user lookup failed", exc_info=True)
        return None


def visitor_id_from_request():
    candidate = request.cookies.get(VISITOR_COOKIE, "")
    try:
        return str(uuid.UUID(candidate))
    except ValueError:
        return str(uuid.uuid4())


def record_page_view(app, visitor_id):
    referrer_host = urlparse(request.referrer or "").hostname
    with database(app) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO visitor_profiles (visitor_id)
                VALUES (%s)
                ON DUPLICATE KEY UPDATE last_seen = CURRENT_TIMESTAMP
                """,
                (visitor_id,),
            )
            cursor.execute(
                """
                INSERT INTO visitor_events
                    (visitor_id, path, referrer_host, instance_id, availability_zone)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    visitor_id,
                    request.path[:255],
                    referrer_host[:255] if referrer_host else None,
                    os.environ.get("INSTANCE_ID", "local-development")[:32],
                    os.environ.get("AVAILABILITY_ZONE", "local")[:32],
                ),
            )


def database_stats_snapshot(app):
    with database(app) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS page_views,
                       COUNT(DISTINCT visitor_id) AS unique_visitors,
                       COALESCE(SUM(visited_at >= NOW() - INTERVAL 24 HOUR), 0) AS views_24h,
                       MIN(visited_at) AS tracking_since
                FROM visitor_events
                """
            )
            traffic = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS registered_users FROM users")
            users = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS appointments FROM appointments")
            appointments = cursor.fetchone()
            cursor.execute(
                """
                SELECT path, COUNT(*) AS views
                FROM visitor_events
                GROUP BY path ORDER BY views DESC, path ASC LIMIT 5
                """
            )
            popular_routes = cursor.fetchall()
            cursor.execute(
                """
                SELECT browser_timezone AS timezone, COUNT(*) AS visitors
                FROM visitor_profiles
                WHERE browser_timezone IS NOT NULL
                GROUP BY browser_timezone ORDER BY visitors DESC, timezone ASC LIMIT 5
                """
            )
            timezones = cursor.fetchall()
            cursor.execute(
                """
                SELECT COUNT(*) AS location_shares
                FROM visitor_profiles WHERE location_shared = TRUE
                """
            )
            locations = cursor.fetchone()

    snapshot = {
        **traffic,
        **users,
        **appointments,
        **locations,
        "popular_routes": popular_routes,
        "timezones": timezones,
        "instance_id": os.environ.get("INSTANCE_ID", "local-development"),
        "availability_zone": os.environ.get("AVAILABILITY_ZONE", "local"),
    }
    for key in (
        "page_views",
        "unique_visitors",
        "views_24h",
        "registered_users",
        "appointments",
        "location_shares",
    ):
        snapshot[key] = int(snapshot.get(key) or 0)
    return snapshot


def stats_snapshot(app):
    unavailable = {
        "page_views": 0,
        "unique_visitors": 0,
        "views_24h": 0,
        "registered_users": 0,
        "appointments": 0,
        "location_shares": 0,
        "tracking_since": None,
        "popular_routes": [],
        "timezones": [],
        "instance_id": os.environ.get("INSTANCE_ID", "local-development"),
        "availability_zone": os.environ.get("AVAILABILITY_ZONE", "local"),
        "database_available": False,
    }
    if not app.config["DATABASE_AVAILABLE"]:
        return unavailable
    try:
        snapshot = database_stats_snapshot(app)
        snapshot["database_available"] = True
        return snapshot
    except pymysql.MySQLError:
        app.config["DATABASE_AVAILABLE"] = False
        app.logger.warning("Statistics database query failed", exc_info=True)
        return unavailable


def create_app():
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    secret = load_database_secret()
    key_material = f"{secret['username']}:{secret['password']}:{required_env('DB_SECRET_ARN')}"
    app.secret_key = hashlib.sha256(key_material.encode()).digest()
    app.config.update(
        DATABASE=database_settings(secret),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=3600,
        DATABASE_AVAILABLE=False,
    )
    CSRFProtect(app)
    threading.Thread(
        target=initialize_schema_with_retry,
        args=(app,),
        name="schema-initializer",
        daemon=True,
    ).start()

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.after_request
    def anonymous_analytics(response):
        visitor_id = visitor_id_from_request()
        if (
            request.method == "GET"
            and request.endpoint in TRACKED_ENDPOINTS
            and response.status_code < 400
            and app.config["DATABASE_AVAILABLE"]
        ):
            try:
                record_page_view(app, visitor_id)
            except pymysql.MySQLError:
                app.logger.warning("Page-view analytics write failed", exc_info=True)
        if request.cookies.get(VISITOR_COOKIE) != visitor_id:
            response.set_cookie(
                VISITOR_COOKIE,
                visitor_id,
                max_age=31536000,
                httponly=True,
                secure=app.config["SESSION_COOKIE_SECURE"],
                samesite="Lax",
            )
        return response

    @app.context_processor
    def inject_context():
        return {
            "current_user": current_user(app),
            "runtime": {
                "instance_id": os.environ.get("INSTANCE_ID", "local-development"),
                "availability_zone": os.environ.get("AVAILABILITY_ZONE", "local"),
            },
        }

    @app.get("/")
    def index():
        return render_template("index.html", stats=stats_snapshot(app))

    @app.get("/stats")
    def stats():
        return render_template("stats.html", stats=stats_snapshot(app))

    @app.get("/api/stats")
    def stats_api():
        snapshot = stats_snapshot(app)
        if snapshot["tracking_since"]:
            snapshot["tracking_since"] = snapshot["tracking_since"].isoformat()
        return jsonify(snapshot)

    @app.post("/api/telemetry")
    def telemetry_api():
        if not app.config["DATABASE_AVAILABLE"]:
            return jsonify(error="Database temporarily unavailable"), 503
        payload = request.get_json(silent=True) or {}
        language = str(payload.get("language", ""))[:32] or None
        timezone = str(payload.get("timezone", ""))[:80] or None
        visitor_id = visitor_id_from_request()

        latitude = payload.get("latitude")
        longitude = payload.get("longitude")
        location_shared = latitude is not None and longitude is not None
        if location_shared:
            try:
                latitude = round(float(latitude), 2)
                longitude = round(float(longitude), 2)
            except (TypeError, ValueError):
                return jsonify(error="Invalid coordinates"), 400
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return jsonify(error="Coordinates outside valid range"), 400

        try:
            with database(app) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                    """
                    INSERT INTO visitor_profiles
                        (visitor_id, browser_language, browser_timezone,
                         location_shared, approximate_latitude, approximate_longitude)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        last_seen = CURRENT_TIMESTAMP,
                        browser_language = COALESCE(VALUES(browser_language), browser_language),
                        browser_timezone = COALESCE(VALUES(browser_timezone), browser_timezone),
                        location_shared = location_shared OR VALUES(location_shared),
                        approximate_latitude = COALESCE(VALUES(approximate_latitude), approximate_latitude),
                        approximate_longitude = COALESCE(VALUES(approximate_longitude), approximate_longitude)
                    """,
                        (
                            visitor_id,
                            language,
                            timezone,
                            location_shared,
                            latitude if location_shared else None,
                            longitude if location_shared else None,
                        ),
                    )
        except pymysql.MySQLError:
            return jsonify(error="Database temporarily unavailable"), 503

        response = jsonify(
            stored=True,
            location_shared=location_shared,
            precision="approximately 1 km" if location_shared else None,
        )
        if request.cookies.get(VISITOR_COOKIE) != visitor_id:
            response.set_cookie(
                VISITOR_COOKIE,
                visitor_id,
                max_age=31536000,
                httponly=True,
                secure=app.config["SESSION_COOKIE_SECURE"],
                samesite="Lax",
            )
        return response

    @app.get("/health")
    def health():
        return jsonify(status="ok", service="cloud-appointment")

    @app.get("/ready")
    def ready():
        try:
            with database(app) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 AS ready")
                    cursor.fetchone()
            app.config["DATABASE_AVAILABLE"] = True
            return jsonify(status="ready", database="connected")
        except pymysql.MySQLError:
            app.config["DATABASE_AVAILABLE"] = False
            return jsonify(status="not-ready", database="unavailable"), 503

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            display_name = request.form.get("display_name", "").strip()
            password = request.form.get("password", "")
            if not email or not display_name or len(password) < 10:
                flash("Enter a name, email, and password of at least 10 characters.", "danger")
            else:
                try:
                    with database(app) as connection:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "INSERT INTO users (email, display_name, password_hash) VALUES (%s, %s, %s)",
                                (email, display_name, generate_password_hash(password)),
                            )
                            user_id = cursor.lastrowid
                    session.clear()
                    session["user_id"] = user_id
                    flash("Your workspace is ready.", "success")
                    return redirect(url_for("dashboard"))
                except pymysql.err.IntegrityError:
                    flash("An account with that email already exists.", "danger")
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            with database(app) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                    user = cursor.fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                flash(f"Welcome back, {user['display_name']}.", "success")
                return redirect(url_for("dashboard"))
            flash("Email or password is incorrect.", "danger")
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("index"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        with database(app) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total,
                           COALESCE(SUM(status = 'Scheduled'), 0) AS scheduled,
                           MIN(CASE WHEN appointment_at >= NOW() AND status = 'Scheduled'
                               THEN appointment_at END) AS next_appointment
                    FROM appointments WHERE user_id = %s
                    """,
                    (session["user_id"],),
                )
                summary = cursor.fetchone()
        return render_template("dashboard.html", summary=summary)

    @app.get("/profile")
    @login_required
    def profile():
        return render_template("profile.html")

    @app.get("/appointments")
    @login_required
    def appointments():
        records = appointment_records(app)
        return render_template("appointments.html", appointments=records)

    @app.route("/appointments/new", methods=["GET", "POST"])
    @login_required
    def appointment_new():
        if request.method == "POST":
            service_name = request.form.get("service_name", "").strip()
            provider_name = request.form.get("provider_name", "").strip()
            try:
                appointment_at = datetime.fromisoformat(request.form["appointment_at"])
            except (KeyError, ValueError):
                flash("Choose a valid appointment date and time.", "danger")
            else:
                if not service_name or not provider_name:
                    flash("Service and provider are required.", "danger")
                    return render_template("appointment_form.html", appointment=None)
                with database(app) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO appointments
                                (user_id, service_name, provider_name, appointment_at, notes)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (
                                session["user_id"],
                                service_name[:120],
                                provider_name[:120],
                                appointment_at,
                                request.form.get("notes", "").strip()[:2000],
                            ),
                        )
                flash("Appointment scheduled.", "success")
                return redirect(url_for("appointments"))
        return render_template("appointment_form.html", appointment=None)

    @app.route("/appointments/<int:appointment_id>/edit", methods=["GET", "POST"])
    @login_required
    def appointment_edit(appointment_id):
        with database(app) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM appointments WHERE id = %s AND user_id = %s",
                    (appointment_id, session["user_id"]),
                )
                appointment = cursor.fetchone()
                if not appointment:
                    abort(404)
                if request.method == "POST":
                    service_name = request.form.get("service_name", "").strip()
                    provider_name = request.form.get("provider_name", "").strip()
                    status = request.form.get("status", "Scheduled")
                    try:
                        appointment_at = datetime.fromisoformat(request.form["appointment_at"])
                    except (KeyError, ValueError):
                        flash("Choose a valid appointment date and time.", "danger")
                    else:
                        if not service_name or not provider_name or status not in {
                            "Scheduled",
                            "Completed",
                            "Cancelled",
                        }:
                            flash("Enter valid appointment details.", "danger")
                            return render_template("appointment_form.html", appointment=appointment)
                        cursor.execute(
                            """
                            UPDATE appointments SET service_name = %s, provider_name = %s,
                                appointment_at = %s, status = %s, notes = %s
                            WHERE id = %s AND user_id = %s
                            """,
                            (
                                service_name[:120],
                                provider_name[:120],
                                appointment_at,
                                status,
                                request.form.get("notes", "").strip()[:2000],
                                appointment_id,
                                session["user_id"],
                            ),
                        )
                        flash("Appointment updated.", "success")
                        return redirect(url_for("appointments"))
        return render_template("appointment_form.html", appointment=appointment)

    @app.post("/appointments/<int:appointment_id>/delete")
    @login_required
    def appointment_delete(appointment_id):
        with database(app) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM appointments WHERE id = %s AND user_id = %s",
                    (appointment_id, session["user_id"]),
                )
        flash("Appointment deleted.", "success")
        return redirect(url_for("appointments"))

    @app.get("/api/appointments")
    @login_required
    def appointments_api():
        records = appointment_records(app)
        return jsonify(
            appointments=[
                {**record, "appointment_at": record["appointment_at"].isoformat()}
                for record in records
            ]
        )

    return app


def appointment_records(app):
    with database(app) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, service_name, provider_name, appointment_at, status, notes
                FROM appointments WHERE user_id = %s ORDER BY appointment_at
                """,
                (session["user_id"],),
            )
            return cursor.fetchall()
