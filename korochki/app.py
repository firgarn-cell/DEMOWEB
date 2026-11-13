"""
Портал «Корочки.есть» — реализация ДЭ КОД 09.02.07-3-2026
Модули 1–2: БД, регистрация, авторизация, заявки, админ, дизайн, слайдер.
Запуск: python app.py
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "korochki.db"

app = Flask(__name__)
app.secret_key = "korochki-demo-exam-2026-change-me"

# --- Валидация (требования КОД) ---
RE_LOGIN = re.compile(r"^[A-Za-z0-9]{6,}$")
RE_FIO = re.compile(r"^[А-Яа-яЁё]+(?:\s[А-Яа-яЁё]+)*$")
RE_PHONE = re.compile(r"^8\(\d{3}\)\d{3}-\d{2}-\d{2}$")
RE_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
RE_DATE_DMY = re.compile(r"^(0[1-9]|[12]\d|3[01])\.(0[1-9]|1[0-2])\.\d{4}$")

COURSES = [
    "Основы алгоритмизации и программирования",
    "Основы веб-дизайна",
    "Основы проектирования баз данных",
]

STATUSES = ("Новая", "Идет обучение", "Обучение завершено")
PAYMENT_LABELS = {
    "cash": "Наличными",
    "phone_transfer": "Переводом по номеру телефона",
}


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            login         TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            full_name     TEXT    NOT NULL,
            phone         TEXT    NOT NULL,
            email         TEXT    NOT NULL,
            role          TEXT    NOT NULL DEFAULT 'user'
                              CHECK (role IN ('user', 'admin'))
        );

        CREATE TABLE IF NOT EXISTS courses (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            title    TEXT NOT NULL UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS applications (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            course_name    TEXT    NOT NULL,
            start_date     TEXT    NOT NULL,
            payment_method TEXT    NOT NULL
                               CHECK (payment_method IN ('cash', 'phone_transfer')),
            status         TEXT    NOT NULL DEFAULT 'Новая'
                               CHECK (status IN ('Новая', 'Идет обучение', 'Обучение завершено')),
            review_text    TEXT,
            created_at     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    # Курсы
    for title in COURSES:
        db.execute(
            "INSERT OR IGNORE INTO courses (title, is_active) VALUES (?, 1)",
            (title,),
        )
    # Админ Admin / KorokNET
    admin = db.execute("SELECT id FROM users WHERE login = ?", ("Admin",)).fetchone()
    if not admin:
        db.execute(
            """
            INSERT INTO users (login, password_hash, full_name, phone, email, role)
            VALUES (?, ?, ?, ?, ?, 'admin')
            """,
            (
                "Admin",
                generate_password_hash("KorokNET"),
                "Администратор Портала",
                "8(900)000-00-00",
                "admin@korochki.local",
            ),
        )
    db.commit()
    db.close()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Сначала войдите в систему.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Сначала войдите в систему.", "error")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Доступ только для администратора.", "error")
            return redirect(url_for("my_applications"))
        return view(*args, **kwargs)

    return wrapped


def current_user():
    if "user_id" not in session:
        return None
    return get_db().execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()


def parse_date_dmy(value: str) -> str | None:
    """ДД.ММ.ГГГГ → YYYY-MM-DD; также принимает YYYY-MM-DD."""
    value = value.strip()
    if RE_DATE_DMY.match(value):
        d, m, y = value.split(".")
        return f"{y}-{m}-{d}"
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        return None


def format_date_dmy(iso: str) -> str:
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return iso


app.jinja_env.filters["dmy"] = format_date_dmy
app.jinja_env.filters["pay"] = lambda k: PAYMENT_LABELS.get(k, k)


# ---------- Страницы ----------


@app.route("/")
def index():
    if "user_id" in session:
        if session.get("role") == "admin":
            return redirect(url_for("admin_panel"))
        return redirect(url_for("my_applications"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    errors: dict[str, str] = {}
    form = {
        "login": "",
        "password": "",
        "full_name": "",
        "phone": "",
        "email": "",
    }

    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in form}
        form["password"] = request.form.get("password") or ""

        if not RE_LOGIN.match(form["login"]):
            errors["login"] = "Логин: латиница и цифры, не менее 6 символов."
        if len(form["password"]) < 8:
            errors["password"] = "Пароль: минимум 8 символов."
        if not RE_FIO.match(form["full_name"]):
            errors["full_name"] = "ФИО: только кириллица и пробелы."
        if not RE_PHONE.match(form["phone"]):
            errors["phone"] = "Телефон в формате 8(XXX)XXX-XX-XX."
        if not RE_EMAIL.match(form["email"]):
            errors["email"] = "Некорректный адрес электронной почты."

        db = get_db()
        if not errors:
            exists = db.execute(
                "SELECT id FROM users WHERE login = ?", (form["login"],)
            ).fetchone()
            if exists:
                errors["login"] = "Такой логин уже занят."

        if not errors:
            db.execute(
                """
                INSERT INTO users (login, password_hash, full_name, phone, email, role)
                VALUES (?, ?, ?, ?, ?, 'user')
                """,
                (
                    form["login"],
                    generate_password_hash(form["password"]),
                    form["full_name"],
                    form["phone"],
                    form["email"],
                ),
            )
            db.commit()
            flash("Пользователь создан. Войдите в систему.", "ok")
            return redirect(url_for("login"))

    return render_template("register.html", form=form, errors=errors)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    login_value = ""

    if request.method == "POST":
        login_value = (request.form.get("login") or "").strip()
        password = request.form.get("password") or ""
        user = get_db().execute(
            "SELECT * FROM users WHERE login = ?", (login_value,)
        ).fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            error = "Неверный логин или пароль."
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["login"] = user["login"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            flash(f"Добро пожаловать, {user['full_name']}!", "ok")
            if user["role"] == "admin":
                return redirect(url_for("admin_panel"))
            return redirect(url_for("my_applications"))

    return render_template("login.html", error=error, login_value=login_value)


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "ok")
    return redirect(url_for("login"))


@app.route("/applications")
@login_required
def my_applications():
    rows = get_db().execute(
        """
        SELECT * FROM applications
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],),
    ).fetchall()
    return render_template("applications.html", applications=rows)


@app.route("/applications/new", methods=["GET", "POST"])
@login_required
def new_application():
    if session.get("role") == "admin":
        flash("Администратор не подаёт заявки.", "error")
        return redirect(url_for("admin_panel"))

    errors: dict[str, str] = {}
    form = {"course_name": "", "start_date": "", "payment_method": "cash"}

    if request.method == "POST":
        form["course_name"] = (request.form.get("course_name") or "").strip()
        form["start_date"] = (request.form.get("start_date") or "").strip()
        form["payment_method"] = request.form.get("payment_method") or ""

        if form["course_name"] not in COURSES and not form["course_name"]:
            errors["course_name"] = "Укажите наименование курса."
        elif not form["course_name"]:
            errors["course_name"] = "Укажите наименование курса."

        iso_date = parse_date_dmy(form["start_date"])
        if not iso_date:
            errors["start_date"] = "Дата в формате ДД.ММ.ГГГГ."

        if form["payment_method"] not in ("cash", "phone_transfer"):
            errors["payment_method"] = "Выберите способ оплаты."

        if not errors:
            get_db().execute(
                """
                INSERT INTO applications
                    (user_id, course_name, start_date, payment_method, status)
                VALUES (?, ?, ?, ?, 'Новая')
                """,
                (
                    session["user_id"],
                    form["course_name"],
                    iso_date,
                    form["payment_method"],
                ),
            )
            get_db().commit()
            flash("Заявка отправлена администратору.", "ok")
            return redirect(url_for("my_applications"))

        form["start_date"] = form["start_date"]

    return render_template(
        "new_application.html", form=form, errors=errors, courses=COURSES
    )


@app.route("/applications/<int:app_id>/review", methods=["POST"])
@login_required
def leave_review(app_id: int):
    db = get_db()
    row = db.execute(
        "SELECT * FROM applications WHERE id = ? AND user_id = ?",
        (app_id, session["user_id"]),
    ).fetchone()
    if not row:
        flash("Заявка не найдена.", "error")
        return redirect(url_for("my_applications"))
    if row["status"] != "Обучение завершено":
        flash("Отзыв доступен только после прохождения курса.", "error")
        return redirect(url_for("my_applications"))

    text = (request.form.get("review_text") or "").strip()
    if not text:
        flash("Введите текст отзыва.", "error")
        return redirect(url_for("my_applications"))

    db.execute(
        "UPDATE applications SET review_text = ? WHERE id = ?",
        (text, app_id),
    )
    db.commit()
    flash("Спасибо! Отзыв сохранён.", "ok")
    return redirect(url_for("my_applications"))


@app.route("/admin")
@admin_required
def admin_panel():
    status_filter = (request.args.get("status") or "").strip()
    page = max(1, int(request.args.get("page") or 1))
    per_page = 5
    db = get_db()

    where = ""
    params: list = []
    if status_filter in STATUSES:
        where = "WHERE a.status = ?"
        params.append(status_filter)

    total = db.execute(
        f"SELECT COUNT(*) AS c FROM applications a {where}", params
    ).fetchone()["c"]
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    offset = (page - 1) * per_page

    rows = db.execute(
        f"""
        SELECT a.*, u.full_name, u.login, u.phone, u.email
        FROM applications a
        JOIN users u ON u.id = a.user_id
        {where}
        ORDER BY a.id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, per_page, offset],
    ).fetchall()

    return render_template(
        "admin.html",
        applications=rows,
        statuses=STATUSES,
        status_filter=status_filter,
        page=page,
        pages=pages,
        total=total,
    )


@app.route("/admin/applications/<int:app_id>/status", methods=["POST"])
@admin_required
def update_status(app_id: int):
    new_status = (request.form.get("status") or "").strip()
    if new_status not in STATUSES:
        flash("Некорректный статус.", "error")
        return redirect(url_for("admin_panel"))

    db = get_db()
    row = db.execute(
        "SELECT id FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    if not row:
        flash("Заявка не найдена.", "error")
        return redirect(url_for("admin_panel"))

    db.execute(
        "UPDATE applications SET status = ? WHERE id = ?",
        (new_status, app_id),
    )
    db.commit()
    flash(f"Статус заявки #{app_id} обновлён: «{new_status}».", "ok")
    return redirect(
        url_for(
            "admin_panel",
            status=request.form.get("return_status") or None,
            page=request.form.get("return_page") or 1,
        )
    )


@app.context_processor
def inject_globals():
    return {
        "current_login": session.get("login"),
        "current_role": session.get("role"),
        "current_name": session.get("full_name"),
    }


if __name__ == "__main__":
    init_db()
    print("БД:", DB_PATH)
    print("Админ: Admin / KorokNET")
    print("Откройте http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000)
