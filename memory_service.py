import sqlite3
import os
from typing import List, Dict, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_memory.db")
MAX_MEMORY_LIMIT = 50
MIN_MEMORY_TARGET = 20


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Ma'lumotlar bazasini ishga tushirish (xotira + admin monitoring)."""
    with get_db_connection() as conn:
        # Suhbat xotirasi (har bir user uchun oxirgi 50 ta)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id ON messages (user_id)
        """)

        # Foydalanuvchilar jadvali
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Barcha so'rov-javoblar tarixi (Admin ko'rishi uchun)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                msg_type TEXT,
                prompt TEXT,
                response TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def add_message(user_id: int, role: str, content: str):
    """Xabarni xotiraga qo'shish va 50 tadan oshib ketmasligini ta'minlash."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        conn.execute("""
            DELETE FROM messages 
            WHERE user_id = ? 
            AND id NOT IN (
                SELECT id FROM messages 
                WHERE user_id = ? 
                ORDER BY id DESC 
                LIMIT ?
            )
        """, (user_id, user_id, MAX_MEMORY_LIMIT))
        conn.commit()


def get_history(user_id: int) -> List[Dict[str, str]]:
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT role, content FROM messages 
            WHERE user_id = ? 
            ORDER BY id ASC
        """, (user_id,))
        rows = cursor.fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]


def clear_history(user_id: int) -> int:
    with get_db_connection() as conn:
        cursor = conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount


def get_memory_status(user_id: int) -> Dict:
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE user_id = ?", (user_id,)
        )
        count = cursor.fetchone()["cnt"]

    percentage = round((count / MAX_MEMORY_LIMIT) * 100, 1)

    if count == 0:
        status_text = "⚪️ Bo'sh (Hech qanday xabar yo'q)"
        indicator = "⚪️"
    elif count < MIN_MEMORY_TARGET:
        status_text = f"🟡 Boshlang'ich muloqot (Min: {MIN_MEMORY_TARGET} ta)"
        indicator = "🟡"
    elif count < MAX_MEMORY_LIMIT:
        status_text = f"🟢 Faol xotira (Optimal hajm)"
        indicator = "🟢"
    else:
        status_text = "🔴 To'liq (50/50 - Yangi xabarlar eskisini yangilaydi)"
        indicator = "🔴"

    return {
        "count": count,
        "max_limit": MAX_MEMORY_LIMIT,
        "min_target": MIN_MEMORY_TARGET,
        "percentage": percentage,
        "status_text": status_text,
        "indicator": indicator,
    }


# ==================== ADMIN MONITORING FUNKSIYALARI ====================

def upsert_user(user_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]):
    """Foydalanuvchi ma'lumotlarini yangilash/saqlash."""
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, last_active)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                last_active=CURRENT_TIMESTAMP
        """, (user_id, username, first_name, last_name))
        conn.commit()


def log_interaction(user_id: int, user_name: str, msg_type: str, prompt: str, response: str):
    """Admin monitoringi uchun har bir muloqotni saqlash."""
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO logs (user_id, user_name, msg_type, prompt, response)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, user_name, msg_type, prompt, response))
        conn.commit()


def get_admin_stats() -> Dict:
    """Admin uchun statistika."""
    with get_db_connection() as conn:
        total_users = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
        total_logs = conn.execute("SELECT COUNT(*) as cnt FROM logs").fetchone()["cnt"]
        today_logs = conn.execute("""
            SELECT COUNT(*) as cnt FROM logs 
            WHERE date(created_at) = date('now')
        """).fetchone()["cnt"]

    return {
        "total_users": total_users,
        "total_logs": total_logs,
        "today_logs": today_logs,
    }


def get_recent_logs(limit: int = 10) -> List[Dict]:
    """Admin uchun so'nggi muloqotlarni olish."""
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT user_id, user_name, msg_type, prompt, response, created_at 
            FROM logs 
            ORDER BY id DESC 
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_all_user_ids() -> List[int]:
    """Barcha foydalanuvchilar ID larini olish (xabar tarqatish uchun)."""
    with get_db_connection() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
        return [r["user_id"] for r in rows]


init_db()
