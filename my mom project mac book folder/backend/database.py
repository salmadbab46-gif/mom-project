import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "research_data.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            subjects TEXT NOT NULL,
            created_at TEXT NOT NULL,
            total_articles INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            title TEXT,
            authors TEXT,
            year INTEGER,
            abstract TEXT,
            summary TEXT,
            key_points TEXT,
            source TEXT,
            source_url TEXT,
            source_type TEXT,
            reliability_score REAL DEFAULT 0,
            subjects TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
    """)
    conn.commit()
    conn.close()

def save_session(session_id: str, subjects: list):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO sessions (id, subjects, created_at) VALUES (?, ?, ?)",
        (session_id, json.dumps(subjects), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def save_article(session_id: str, article: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO articles
        (id, session_id, title, authors, year, abstract, summary, key_points,
         source, source_url, source_type, reliability_score, subjects, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        article.get("id"),
        session_id,
        article.get("title"),
        json.dumps(article.get("authors", [])),
        article.get("year"),
        article.get("abstract"),
        article.get("summary"),
        json.dumps(article.get("key_points", [])),
        article.get("source"),
        article.get("source_url"),
        article.get("source_type"),
        article.get("reliability_score", 0),
        json.dumps(article.get("subjects", [])),
        datetime.now().isoformat()
    ))
    conn.execute(
        "UPDATE sessions SET total_articles = total_articles + 1 WHERE id = ?",
        (session_id,)
    )
    conn.commit()
    conn.close()

def get_sessions():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_session_articles(session_id: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM articles WHERE session_id = ? ORDER BY reliability_score DESC",
        (session_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["authors"] = json.loads(d["authors"] or "[]")
        d["key_points"] = json.loads(d["key_points"] or "[]")
        d["subjects"] = json.loads(d["subjects"] or "[]")
        result.append(d)
    return result

init_db()
