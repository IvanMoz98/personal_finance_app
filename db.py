"""Accès à la base SQLite (fichier finance.db)."""
import os
import sqlite3
import sys
from pathlib import Path

APP_NAME = "Mes Finances"


def _default_db_path() -> Path:
    """En développement : à côté du code. Dans l'application packagée : dossier de données
    de l'utilisateur (le contenu de l'exécutable est en lecture seule / temporaire)."""
    if not getattr(sys, "frozen", False):
        return Path(__file__).with_name("finance.db")
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "finance.db"


DB_PATH = Path(os.environ.get("FINANCE_DB") or _default_db_path())

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#4f6bed'
);

-- kind : 'expense' (dépense), 'income' (revenu), 'transfer' (virement interne, exclu des stats)
CREATE TABLE IF NOT EXISTS categories (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#888888',
    kind  TEXT NOT NULL DEFAULT 'expense'
);

-- amount < 0 : débit, amount > 0 : crédit
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    label       TEXT NOT NULL,
    amount      REAL NOT NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    recurring   INTEGER NOT NULL DEFAULT 0,
    note        TEXT NOT NULL DEFAULT '',
    hash        TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);

-- Règles d'auto-catégorisation : si le libellé contient `pattern`
CREATE TABLE IF NOT EXISTS rules (
    id          INTEGER PRIMARY KEY,
    pattern     TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    recurring   INTEGER  -- NULL = ne pas toucher, 0/1 = forcer
);
"""

DEFAULT_CATEGORIES = [
    ("Maison", "#2a78d6", "expense"),
    ("Courses", "#eb6834", "expense"),
    ("Transport", "#1baf7a", "expense"),
    ("Loisirs", "#eda100", "expense"),
    ("Restaurants", "#e87ba4", "expense"),
    ("Santé", "#008300", "expense"),
    ("Abonnements", "#4a3aa7", "expense"),
    ("Impôts & taxes", "#e34948", "expense"),
    ("Shopping", "#8d6e63", "expense"),
    ("Divers", "#8a8984", "expense"),
    ("Salaire", "#1baf7a", "income"),
    ("Autres revenus", "#2a78d6", "income"),
    ("Virement interne", "#b5b4ae", "transfer"),
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO categories(name, color, kind) VALUES (?, ?, ?)",
                DEFAULT_CATEGORIES,
            )
        if conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
            conn.execute("INSERT INTO accounts(name) VALUES ('Compte courant')")
