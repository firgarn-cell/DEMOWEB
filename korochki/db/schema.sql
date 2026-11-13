-- Схема БД портала «Корочки.есть» (КОД 09.02.07-3-2026)
-- Импортируйте в СУБД и постройте ER-диаграмму средствами Workbench / DBeaver / pgAdmin.

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    login         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    full_name     TEXT    NOT NULL,
    phone         TEXT    NOT NULL,
    email         TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'user'
                      CHECK (role IN ('user', 'admin'))
);

CREATE TABLE courses (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    title     TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE applications (
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

-- Админ создаётся приложением: Admin / KorokNET (пароль хешируется).
