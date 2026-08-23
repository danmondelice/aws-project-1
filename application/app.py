import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

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
    ]
    with database(app) as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Sign in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def current_user(app):
    if "user_id" not in session:
        return None
    with database(app) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, email, display_name, created_at FROM users WHERE id = %s",
                (session["user_id"],),
            )
            return cursor.fetchone()


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
    )
    CSRFProtect(app)
    initialize_schema(app)

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
        return render_template("index.html")

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
            return jsonify(status="ready", database="connected")
        except pymysql.MySQLError:
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
