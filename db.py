import sqlite3
from contextlib import closing

import os

BOUND_CHATS_FILE = "bound_chats.txt"

def save_bound_chat_id(chat_id):
    try:
        chats = load_bound_chat_ids()
        if chat_id not in chats:
            chats.append(chat_id)
            with open(BOUND_CHATS_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(str(c) for c in chats))
    except Exception as e:
        print(f"[DEBUG] Ошибка сохранения чата: {e}")

def load_bound_chat_ids():
    if not os.path.exists(BOUND_CHATS_FILE):
        return []
    try:
        with open(BOUND_CHATS_FILE, "r", encoding="utf-8") as f:
            return [int(line.strip()) for line in f if line.strip().lstrip("-").isdigit()]
    except Exception as e:
        print(f"[DEBUG] Ошибка загрузки чатов: {e}")
        return []

def delete_bound_chat_id(chat_id):
    try:
        chats = load_bound_chat_ids()
        if chat_id in chats:
            chats.remove(chat_id)
            with open(BOUND_CHATS_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(str(c) for c in chats))
    except Exception as e:
        print(f"[DEBUG] Ошибка удаления чата: {e}")

DB_FILE = "bot.db"

def init_db():
    with closing(sqlite3.connect(DB_FILE)) as conn, conn, closing(conn.cursor()) as cursor:
        # Таблица пользователей
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT
        )
        """)

        # Таблица чатов
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            title TEXT,
            chat_type TEXT,
            UNIQUE(chat_id, user_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        conn.commit()

def get_or_create_user(telegram_user):
    """Создает пользователя, если его нет"""
    with closing(sqlite3.connect(DB_FILE)) as conn, closing(conn.cursor()) as cursor:
        cursor.execute("""
            INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        """, (telegram_user.id, telegram_user.username, telegram_user.first_name, telegram_user.last_name))
        conn.commit()
        cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_user.id,))
        return cursor.fetchone()[0]

def add_chat(user_id, chat_id, title, chat_type):
    """Сохраняет чат для конкретного пользователя"""
    with closing(sqlite3.connect(DB_FILE)) as conn, closing(conn.cursor()) as cursor:
        cursor.execute("""
            INSERT OR IGNORE INTO chats (chat_id, user_id, title, chat_type)
            VALUES (?, ?, ?, ?)
        """, (chat_id, user_id, title, chat_type))
        conn.commit()

def remove_chat(user_id, chat_id):
    """Удаляет чат пользователя"""
    with closing(sqlite3.connect(DB_FILE)) as conn, closing(conn.cursor()) as cursor:
        cursor.execute("""
            DELETE FROM chats WHERE user_id = ? AND chat_id = ?
        """, (user_id, chat_id))
        conn.commit()

def get_user_chats(user_id):
    """Возвращает все чаты пользователя"""
    with closing(sqlite3.connect(DB_FILE)) as conn, closing(conn.cursor()) as cursor:
        cursor.execute("""
            SELECT chat_id, title, chat_type FROM chats WHERE user_id = ?
        """, (user_id,))
        return cursor.fetchall()
