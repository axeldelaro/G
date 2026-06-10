# ═══════════════════════════════════════════════════════════════════
# database.py — init/connexion DB, helpers d'accès, CRUD média
# ═══════════════════════════════════════════════════════════════════
import os
import time
import json
import sqlite3
import datetime

import config
from config import (DB_FILE, DB_LOCK, DB_LOCK_FILE, INDEX_LOCK,
                    NIGHT_QUOTA, DAILY_QUOTA, SVAULT_EXT, EXT_LEN,
                    ALL_EXTS, AUD_EXTS, VID_EXTS)
import security
from security import unlock_database_file

# Connexion sqlite globale (utilisée uniquement par ce module).
db = None


def is_night_hours():
    h = datetime.datetime.now().hour
    return h == 23 or h < 6


def get_effective_quota():
    return NIGHT_QUOTA if is_night_hours() else DAILY_QUOTA


def is_target_media(f):
    return f.lower().endswith(ALL_EXTS + AUD_EXTS) and not f.endswith(SVAULT_EXT) and not f.endswith('.svault')


def is_obfuscated_media(f):
    return f.endswith(SVAULT_EXT) and f[:-EXT_LEN].lower().endswith(ALL_EXTS)


def is_obfuscated_video(f):
    return f.endswith(SVAULT_EXT) and f[:-EXT_LEN].lower().endswith(VID_EXTS)


def is_obfuscated_audio(f):
    return f.endswith(SVAULT_EXT) and f[:-EXT_LEN].lower().endswith(AUD_EXTS)


def init_db():
    global db
    with DB_LOCK:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")

        c.execute('''CREATE TABLE IF NOT EXISTS media (
            path TEXT PRIMARY KEY,
            views INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            liked INTEGER DEFAULT 0,
            r INTEGER DEFAULT -1,
            g INTEGER DEFAULT -1,
            b INTEGER DEFAULT -1)''')

        columns = [
            ("corrupted", "INTEGER DEFAULT 0"), ("vault", "INTEGER DEFAULT 0"),
            ("phash", "TEXT DEFAULT ''"), ("views_eq", "INTEGER DEFAULT 0"),
            ("faces_data", "TEXT DEFAULT ''"), ("demographics", "TEXT DEFAULT ''"),
            ("burn_regions", "TEXT DEFAULT '[]'")
        ]
        for col, default in columns:
            try:
                c.execute(f"ALTER TABLE media ADD COLUMN {col} {default}")
            except sqlite3.OperationalError:
                pass

        c.execute("CREATE TABLE IF NOT EXISTS tags (path TEXT, tag TEXT, UNIQUE(path, tag))")
        c.execute("CREATE TABLE IF NOT EXISTS names (path TEXT, name TEXT, UNIQUE(path, name))")
        c.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, ts REAL)")

        c.execute("CREATE TABLE IF NOT EXISTS global_stats (key TEXT PRIMARY KEY, value INTEGER DEFAULT 0)")
        c.execute("INSERT OR IGNORE INTO global_stats (key, value) VALUES ('total_time', 0)")
        c.execute("INSERT OR IGNORE INTO global_stats (key, value) VALUES ('daily_time', 0)")

        c.execute("CREATE TABLE IF NOT EXISTS global_config (key TEXT PRIMARY KEY, value TEXT DEFAULT '')")
        c.execute("INSERT OR IGNORE INTO global_config (key, value) VALUES ('last_reset_date', '')")
        c.execute("INSERT OR IGNORE INTO global_config (key, value) VALUES ('purgatory_base', '0')")
        c.execute("INSERT OR IGNORE INTO global_config (key, value) VALUES ('purgatory_mult', '1.0')")

        c.execute("CREATE TABLE IF NOT EXISTS purgatory (path TEXT PRIMARY KEY, original_path TEXT, delete_time REAL)")

        c.execute("CREATE INDEX IF NOT EXISTS idx_tags_path ON tags(path)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_names_path ON names(path)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_hist_path ON history(path)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_hist_ts ON history(ts)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_purg_orig ON purgatory(original_path)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_media_liked ON media(liked)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_media_vault ON media(vault)")

        conn.commit()
        db = conn
        return conn


def check_startup_lock():
    """Vérification du lock fichier au démarrage (après init_db)."""
    if os.path.exists(DB_LOCK_FILE):
        try:
            with open(DB_LOCK_FILE) as _lf:
                _unlock_ts = float(_lf.read().strip())
            if time.time() < _unlock_ts:
                config.SESSION_KEY_ACTIVE = False
                config.LOCKED_UNTIL = _unlock_ts
                print(f"🔒 [QUOTA] Galerie verrouillée jusqu'à minuit.")
            else:
                unlock_database_file()
                print("🔓 [QUOTA] Verrou expiré, déverrouillage automatique.")
        except Exception:
            pass

    if is_night_hours():
        print(f"🌙 [QUOTA] Fenêtre 23h–6h détectée : quota réduit.")


def db_exec(query, args=()):
    with DB_LOCK:
        c = db.cursor()
        c.execute(query, args)
        db.commit()


def db_fetch(query, args=()):
    with DB_LOCK:
        c = db.cursor()
        c.execute(query, args)
        return c.fetchall()


def db_fetchone(query, args=()):
    with DB_LOCK:
        c = db.cursor()
        c.execute(query, args)
        return c.fetchone()


def update_views(path, add):
    with DB_LOCK:
        c = db.cursor()
        c.execute("INSERT INTO media (path, views) VALUES (?, ?) "
                  "ON CONFLICT(path) DO UPDATE SET views = views + ?",
                  (path, add, add))
        db.commit()
        c.execute("SELECT views FROM media WHERE path=?", (path,))
        res = c.fetchone()
        return res[0] if res else 0


def toggle_like(path):
    db_exec("INSERT OR IGNORE INTO media (path) VALUES (?)", (path,))
    res = db_fetchone("SELECT liked FROM media WHERE path=?", (path,))
    liked = not bool(res[0]) if res else True
    db_exec("UPDATE media SET liked = ? WHERE path=?", (1 if liked else 0, path))
    return liked


def toggle_vault(path):
    db_exec("INSERT OR IGNORE INTO media (path) VALUES (?)", (path,))
    res = db_fetchone("SELECT vault FROM media WHERE path=?", (path,))
    is_vault = not bool(res[0]) if res else True
    db_exec("UPDATE media SET vault = ? WHERE path=?", (1 if is_vault else 0, path))
    return is_vault


def set_rating(path, r):
    db_exec("INSERT OR IGNORE INTO media (path) VALUES (?)", (path,))
    db_exec("UPDATE media SET rating=? WHERE path=?", (r, path))


def set_note(path, n):
    db_exec("INSERT OR IGNORE INTO media (path) VALUES (?)", (path,))
    db_exec("UPDATE media SET note=? WHERE path=?", (n, path))


def get_burn_regions(path):
    res = db_fetchone("SELECT burn_regions FROM media WHERE path=?", (path,))
    if not res or not res[0]:
        return []
    try:
        return json.loads(res[0])
    except (ValueError, TypeError):
        return []


def set_burn_regions(path, regions):
    db_exec("INSERT OR IGNORE INTO media (path) VALUES (?)", (path,))
    db_exec("UPDATE media SET burn_regions=? WHERE path=?", (json.dumps(regions), path))


def add_hist(path):
    db_exec("INSERT INTO history (path, ts) VALUES (?, ?)", (path, time.time()))


def sync_tags(path, tags):
    with DB_LOCK:
        c = db.cursor()
        c.execute("DELETE FROM tags WHERE path=?", (path,))
        if tags:
            c.executemany("INSERT OR IGNORE INTO tags (path, tag) VALUES (?, ?)", [(path, t) for t in tags])
        db.commit()


def sync_names(path, names):
    with DB_LOCK:
        c = db.cursor()
        c.execute("DELETE FROM names WHERE path=?", (path,))
        if names:
            c.executemany("INSERT OR IGNORE INTO names (path, name) VALUES (?, ?)", [(path, n) for n in names])
        db.commit()


def get_all_unique_names():
    return [r[0] for r in db_fetch("SELECT DISTINCT name FROM names ORDER BY name COLLATE NOCASE")]
