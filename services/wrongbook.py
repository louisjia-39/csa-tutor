import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("wrongbook.db")

def _conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS wrongbook (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            unit TEXT,
            topic TEXT,
            question TEXT,
            user_answer TEXT,
            correct_answer TEXT,
            explanation TEXT,
            mistake_type TEXT,
            next_drill TEXT
        )
        """)
        c.commit()

def add_entry(unit, topic, question, user_answer, correct_answer, explanation, mistake_type, next_drill):
    with _conn() as c:
        c.execute("""
        INSERT INTO wrongbook
        (created_at, unit, topic, question, user_answer, correct_answer, explanation, mistake_type, next_drill)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            unit, topic, question, user_answer, correct_answer, explanation, mistake_type, next_drill
        ))
        c.commit()

def list_entries(limit=200):
    with _conn() as c:
        rows = c.execute("""
        SELECT id, created_at, unit, topic, question, user_answer, correct_answer, mistake_type
        FROM wrongbook ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    return rows

def get_entry(entry_id: int):
    with _conn() as c:
        row = c.execute("SELECT * FROM wrongbook WHERE id=?", (entry_id,)).fetchone()
    return row
