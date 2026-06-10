# ═══════════════════════════════════════════════════════════════════
# workers.py — tâches en arrière-plan
# ═══════════════════════════════════════════════════════════════════
import os
import io
import time
import shutil
import datetime
import threading
import subprocess

import config
from config import (PORT, THUMB_DIR, BG_BATCH_SIZE, SCRAMBLE_SIZE, MEDIA_DIR,
                    DB_LOCK_FILE, INDEX_LOCK, HAS_PILLOW)
import database
from database import db_exec, db_fetch, is_obfuscated_video
import media
from media import (scan_obfuscate, indexer, check_and_set_wallpaper, calc_dhash,
                   degrade_media_permanently)
from security import xor_chunk, unlock_purgatory_file, unlock_database_file

if HAS_PILLOW:
    from PIL import Image


def equalize_video_views_task():
    try:
        rows = db_fetch("SELECT path, views, views_eq FROM media WHERE views > 0")
        for r in rows:
            p = r[0]
            views = r[1]
            views_eq = r[2] if r[2] is not None else 0
            if views_eq == 1:
                continue
            if is_obfuscated_video(p):
                fid = config.FILE_INDEX_R.get(p)
                if not fid:
                    continue
                local_url = f"http://127.0.0.1:{PORT}/f/{fid}"
                try:
                    res = subprocess.run(
                        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                         '-of', 'default=noprint_wrappers=1:nokey=1', local_url],
                        capture_output=True, text=True, timeout=10
                    )
                    if res.stdout.strip():
                        duration = float(res.stdout.strip())
                        if duration > 1.0:
                            new_views = int(views * duration)
                            db_exec("UPDATE media SET views=?, views_eq=1 WHERE path=?", (new_views, p))
                        else:
                            db_exec("UPDATE media SET views_eq=1 WHERE path=?", (p,))
                except Exception:
                    pass
    except Exception:
        pass


def reindex_bg():
    while True:
        scan_obfuscate()
        indexer()
        check_and_set_wallpaper()
        time.sleep(300)


def bg_worker():
    while True:
        try:
            with INDEX_LOCK:
                files = list(config.MEDIA_FILES)
            rows = db_fetch("SELECT path FROM media WHERE (r != -1 AND phash != '') AND corrupted = 0")
            analyzed_files = set(r[0] for r in rows)

            processed_in_batch = 0
            for f in files:
                fid = config.FILE_INDEX_R.get(f)
                if not fid:
                    continue

                thumb_path = os.path.join(THUMB_DIR, fid + ".jpg")
                needs_thumb = not os.path.exists(thumb_path)
                needs_analysis = f not in analyzed_files

                if not needs_thumb and not needs_analysis:
                    continue
                if processed_in_batch >= BG_BATCH_SIZE:
                    break

                r_col, g_col, b_col, phash_str = None, None, None, ""
                temp_img = os.path.join(THUMB_DIR, f"temp_{fid}.jpg")
                local_url = f"http://127.0.0.1:{PORT}/f/{fid}"

                if is_obfuscated_video(f):
                    if needs_thumb or needs_analysis:
                        subprocess.run(
                            ['ffmpeg', '-y', '-threads', '1', '-ss', '00:00:01', '-i', local_url,
                             '-vframes', '1', '-q:v', '2', '-s', '320x320', '-preset', 'ultrafast', temp_img],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
                        if os.path.exists(temp_img):
                            if needs_thumb:
                                shutil.copy(temp_img, thumb_path)
                            if needs_analysis and HAS_PILLOW:
                                try:
                                    with Image.open(temp_img) as img:
                                        img_rgb = img.convert('RGB')
                                        r_col, g_col, b_col = img_rgb.resize((1, 1)).getpixel((0, 0))
                                        phash_str = calc_dhash(img_rgb)
                                except Exception:
                                    pass
                            try:
                                os.remove(temp_img)
                            except Exception:
                                pass
                else:
                    if HAS_PILLOW:
                        try:
                            with open(f, 'rb') as fh:
                                buf = bytearray(fh.read())
                            buf[:SCRAMBLE_SIZE] = xor_chunk(buf[:SCRAMBLE_SIZE], 0)
                            with Image.open(io.BytesIO(buf)) as img:
                                img.thumbnail((320, 320))
                                img_rgb = img.convert('RGB') if img.mode != 'RGB' else img
                                if needs_thumb:
                                    img_rgb.save(thumb_path, "JPEG")
                                if needs_analysis:
                                    r_col, g_col, b_col = img_rgb.resize((1, 1)).getpixel((0, 0))
                                    phash_str = calc_dhash(img_rgb)
                        except Exception:
                            pass
                    elif needs_thumb:
                        subprocess.run(
                            ['ffmpeg', '-y', '-threads', '1', '-i', local_url,
                             '-vframes', '1', '-q:v', '2', '-s', '320x320', thumb_path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )

                if needs_analysis and r_col is not None:
                    db_exec("INSERT OR IGNORE INTO media (path) VALUES (?)", (f,))
                    db_exec("UPDATE media SET r=?, g=?, b=?, phash=? WHERE path=?", (r_col, g_col, b_col, phash_str, f))

                processed_in_batch += 1
                time.sleep(0.5)

            if processed_in_batch == 0:
                time.sleep(15)
            else:
                time.sleep(5)
        except Exception:
            time.sleep(15)


def resurrection_worker():
    while True:
        try:
            now = time.time()
            rows = db_fetch("SELECT path, original_path FROM purgatory WHERE delete_time <= ?", (now,))

            if rows:
                pending = {os.path.basename(r[0]): r for r in rows}
                for r_dir, _, fs in os.walk(MEDIA_DIR):
                    for f in fs:
                        if f in pending:
                            current_path = os.path.join(r_dir, f)
                            db_path, orig_path = pending[f]
                            try:
                                unlock_purgatory_file(current_path)
                                os.makedirs(os.path.dirname(orig_path), exist_ok=True)
                                shutil.move(current_path, orig_path)
                                degrade_media_permanently(orig_path)
                            except Exception:
                                pass

                for r in rows:
                    db_exec("DELETE FROM purgatory WHERE path=?", (r[0],))
                indexer()
        except Exception:
            pass
        time.sleep(60)


def daily_reset_worker():
    while True:
        time.sleep(30)
        if os.path.exists(DB_LOCK_FILE):
            try:
                with open(DB_LOCK_FILE) as f:
                    unlock_ts = float(f.read().strip())
                if time.time() >= unlock_ts:
                    unlock_database_file()
                    try:
                        db_exec("UPDATE global_stats SET value=0 WHERE key='daily_time'")
                        today = datetime.date.today().isoformat()
                        db_exec("UPDATE global_config SET value=? WHERE key='last_reset_date'", (today,))
                    except Exception:
                        pass
                    config.SESSION_KEY_ACTIVE  = True
                    config.LOCKED_UNTIL        = 0.0
                    config.LOCKDOWN_TRIGGERED  = False
                    threading.Thread(target=reindex_bg, daemon=True).start()
                    print("🔓 [QUOTA] Déverrouillage automatique à minuit.")
            except Exception as e:
                print(f"⚠️  [QUOTA] erreur : {e}")
