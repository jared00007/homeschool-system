import os
import sqlite3
from pathlib import Path

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None


ROOT = Path(__file__).resolve().parent
LOCAL_DB = ROOT / "homeschool.db"

SCHEMA = {
    "students": """
        CREATE TABLE IF NOT EXISTS students (
            id BIGINT PRIMARY KEY,
            name TEXT NOT NULL,
            grade TEXT,
            school_year TEXT
        )
    """,
    "log_entries": """
        CREATE TABLE IF NOT EXISTS log_entries (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            entry_date TEXT NOT NULL,
            subject TEXT NOT NULL,
            hours REAL NOT NULL,
            description TEXT,
            day_type TEXT DEFAULT 'Instruction',
            status TEXT DEFAULT 'approved',
            submitted_at TEXT
        )
    """,
    "assignments": """
        CREATE TABLE IF NOT EXISTS assignments (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            assign_date TEXT NOT NULL,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            score REAL,
            max_score REAL,
            notes TEXT,
            photo_path TEXT,
            submitted_at TEXT
        )
    """,
    "assessments": """
        CREATE TABLE IF NOT EXISTS assessments (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            assessment_date TEXT NOT NULL,
            assessment_type TEXT,
            evaluator TEXT,
            result TEXT,
            notes TEXT
        )
    """,
    "settings": """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """,
    "student_electives": """
        CREATE TABLE IF NOT EXISTS student_electives (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            school_year TEXT,
            elective_name TEXT NOT NULL,
            selected_date TEXT
        )
    """,
    "student_books": """
        CREATE TABLE IF NOT EXISTS student_books (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            school_year TEXT,
            title TEXT NOT NULL,
            author TEXT,
            ties_to TEXT,
            link TEXT,
            status TEXT DEFAULT 'planned',
            selected_date TEXT,
            finished_date TEXT,
            finished_at TEXT,
            notes TEXT
        )
    """,
    "accounts": """
        CREATE TABLE IF NOT EXISTS accounts (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            service_name TEXT NOT NULL,
            url TEXT,
            username TEXT,
            password TEXT,
            status TEXT DEFAULT 'not_started',
            notes TEXT
        )
    """,
    "elective_pool": """
        CREATE TABLE IF NOT EXISTS elective_pool (
            id BIGINT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            resource_name TEXT,
            url TEXT,
            description TEXT
        )
    """,
    "book_pool": """
        CREATE TABLE IF NOT EXISTS book_pool (
            id BIGINT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT,
            ties_to TEXT,
            link TEXT
        )
    """,
    "proposals": """
        CREATE TABLE IF NOT EXISTS proposals (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            school_year TEXT,
            prop_type TEXT NOT NULL,
            title TEXT NOT NULL,
            secondary TEXT,
            url TEXT,
            description TEXT,
            status TEXT DEFAULT 'pending',
            parent_note TEXT,
            submitted_date TEXT,
            reviewed_date TEXT,
            submitted_at TEXT
        )
    """,
    "fun_project_pool": """
        CREATE TABLE IF NOT EXISTS fun_project_pool (
            id BIGINT PRIMARY KEY,
            title TEXT NOT NULL,
            subject TEXT,
            description TEXT
        )
    """,
    "student_fun_projects": """
        CREATE TABLE IF NOT EXISTS student_fun_projects (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            school_year TEXT,
            title TEXT NOT NULL,
            subject TEXT,
            description TEXT,
            status TEXT DEFAULT 'planned',
            selected_date TEXT,
            finished_date TEXT,
            finished_at TEXT,
            notes TEXT
        )
    """,
    "health_habits": """
        CREATE TABLE IF NOT EXISTS health_habits (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            log_date TEXT NOT NULL,
            exercise INTEGER DEFAULT 0,
            water INTEGER DEFAULT 0,
            sleep INTEGER DEFAULT 0,
            nutrition INTEGER DEFAULT 0,
            journal TEXT,
            day_rating INTEGER,
            mood_rating INTEGER,
            lesson_hard INTEGER,
            lesson_hard_notes TEXT
        )
    """,
    "holidays": """
        CREATE TABLE IF NOT EXISTS holidays (
            id BIGINT PRIMARY KEY,
            school_year TEXT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            label TEXT NOT NULL
        )
    """,
    "parent_checkins": """
        CREATE TABLE IF NOT EXISTS parent_checkins (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            checkin_date TEXT NOT NULL,
            notes TEXT
        )
    """,
    "national_parks": """
        CREATE TABLE IF NOT EXISTS national_parks (
            id BIGINT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            state TEXT,
            lat TEXT,
            lon TEXT,
            booklet_url TEXT,
            region TEXT
        )
    """,
    "major_cities": """
        CREATE TABLE IF NOT EXISTS major_cities (
            id BIGINT PRIMARY KEY,
            name TEXT NOT NULL,
            state TEXT,
            lat TEXT,
            lon TEXT
        )
    """,
    "travel_entries": """
        CREATE TABLE IF NOT EXISTS travel_entries (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            school_year TEXT,
            entry_date TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            photo_path TEXT,
            tag_state TEXT,
            tag_park_id BIGINT,
            tag_city_id BIGINT,
            badge_earned INTEGER DEFAULT 0,
            submitted_at TEXT
        )
    """,
    "link_reports": """
        CREATE TABLE IF NOT EXISTS link_reports (
            id BIGINT PRIMARY KEY,
            student_id BIGINT NOT NULL,
            report_date TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            parent_note TEXT,
            resolved_date TEXT,
            submitted_at TEXT
        )
    """,
}


def get_connection_string():
    return os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")


def migrate():
    if psycopg2 is None:
        raise RuntimeError("psycopg2-binary is required. Install dependencies first.")

    conn_str = get_connection_string()
    if not conn_str:
        raise RuntimeError("Set DATABASE_URL or SUPABASE_DB_URL before running this script.")

    if not LOCAL_DB.exists():
        raise FileNotFoundError(f"Local database not found at {LOCAL_DB}")

    sqlite_conn = sqlite3.connect(LOCAL_DB)
    pg_conn = psycopg2.connect(conn_str)
    pg_conn.autocommit = False
    pg_cursor = pg_conn.cursor()

    try:
        for table_name, ddl in SCHEMA.items():
            pg_cursor.execute(ddl)

        for table_name in SCHEMA:
            rows = sqlite_conn.execute(f"SELECT * FROM {table_name}").fetchall()
            if not rows:
                continue
            cols = [c[1] for c in sqlite_conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
            placeholders = ", ".join(["%s"] * len(cols))
            col_sql = ", ".join(cols)
            insert_sql = f"INSERT INTO {table_name} ({col_sql}) VALUES ({placeholders})"
            for row in rows:
                pg_cursor.execute(insert_sql, row)

        pg_conn.commit()
        print(f"Migrated {len(SCHEMA)} tables from {LOCAL_DB} to cloud database.")
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        pg_cursor.close()
        pg_conn.close()
        sqlite_conn.close()


if __name__ == "__main__":
    migrate()
