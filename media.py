# ═══════════════════════════════════════════════════════════════════
# media.py — frontend HTML, gestion/indexation des médias, dégradations,
#            icônes PWA, manifest, statistiques
# ═══════════════════════════════════════════════════════════════════
import os
import io
import time
import zlib
import struct
import random
import shutil
import hashlib
import binascii
import datetime
import threading
import subprocess

import config
from config import (BASE_DIR, MEDIA_DIR, TRASH_DIR, CORRUPT_DIR, THUMB_DIR,
                    PURGATORY_DIR, BACKUP_DIR,
                    SVAULT_EXT, EXT_LEN, SCRAMBLE_SIZE, IMG_EXTS, VID_EXTS,
                    INDEX_LOCK, FILE_INDEX_LOCK, DB_LOCK, HAS_PILLOW)
import database
from database import (db_exec, db_fetch, is_target_media, is_obfuscated_media,
                      is_obfuscated_audio, is_obfuscated_video)
from security import xor_chunk

if HAS_PILLOW:
    from PIL import Image, ImageEnhance


# ─── Frontend ──────────────────────────────────────────────────────
_FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


def load_text(name):
    with open(os.path.join(_FRONTEND_DIR, name), encoding="utf-8") as f:
        return f.read()


INDEX_HTML = load_text("index.html")
WITCH_UI_HTML = load_text("witch.html")


# ─── Hash perceptuel / couleur ─────────────────────────────────────
def color_distance(c1, c2):
    try:
        r1, g1, b1 = c1
        r2, g2, b2 = c2
        rmean = int((r1 + r2) / 2)
        r = r1 - r2
        g = g1 - g2
        b = b1 - b2
        return (((512 + rmean) * r * r) >> 8) + 4 * g * g + (((767 - rmean) * b * b) >> 8)
    except (TypeError, ValueError, IndexError):
        return float('inf')


def calc_dhash(img):
    try:
        img = img.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
        diff = []
        for row in range(8):
            for col in range(8):
                pixel_left = img.getpixel((col, row))
                pixel_right = img.getpixel((col + 1, row))
                diff.append('1' if pixel_left > pixel_right else '0')
        return ''.join(diff)
    except Exception:
        return ''


def get_stats():
    try:
        with INDEX_LOCK:
            videos = sum(1 for f in config.MEDIA_FILES if is_obfuscated_video(f))
            images = len(config.MEDIA_FILES) - videos
            audios = len(config.AUDIO_FILES)
            total_files = images + videos + audios

        row = database.db_fetchone("SELECT SUM(liked), SUM(vault) FROM media")
        liked = row[0] or 0
        vault = row[1] or 0
        history = database.db_fetchone("SELECT COUNT(*) FROM history")[0]
        total_time = database.db_fetchone("SELECT value FROM global_stats WHERE key='total_time'")[0]

        return {
            'total_files': total_files, 'images': images, 'videos': videos,
            'audios': audios, 'liked': liked, 'vault': vault, 'history': history,
            'total_time': total_time
        }
    except Exception:
        return {}


# ─── Indexation / scan ─────────────────────────────────────────────
def scan_obfuscate():
    for r_dir, _, fs in os.walk(MEDIA_DIR):
        if TRASH_DIR in r_dir or CORRUPT_DIR in r_dir or THUMB_DIR in r_dir or PURGATORY_DIR in r_dir or BACKUP_DIR in r_dir:
            continue
        for f in fs:
            if f.endswith('.dead'):
                continue
            old_p = os.path.abspath(os.path.join(r_dir, f))
            if f.endswith('.svault') or is_target_media(f):
                new_p = old_p[:-7] + SVAULT_EXT if f.endswith('.svault') else old_p + SVAULT_EXT
                try:
                    with open(old_p, 'r+b') as fh:
                        header = fh.read(SCRAMBLE_SIZE)
                        fh.seek(0)
                        fh.write(xor_chunk(header, 0))
                    os.rename(old_p, new_p)
                    db_exec("UPDATE media   SET path=? WHERE path=?", (new_p, old_p))
                    db_exec("UPDATE tags    SET path=? WHERE path=?", (new_p, old_p))
                    db_exec("UPDATE names   SET path=? WHERE path=?", (new_p, old_p))
                    db_exec("UPDATE history SET path=? WHERE path=?", (new_p, old_p))
                except Exception:
                    pass


def scan_and_move_corrupted():
    rows = db_fetch("SELECT path FROM media WHERE corrupted=1")
    for row in rows:
        db_path = row[0]
        if os.path.exists(db_path):
            try:
                shutil.move(db_path, os.path.join(CORRUPT_DIR, f"{int(time.time()*1000)}____{os.path.basename(db_path)}"))
            except Exception:
                pass
        db_exec("DELETE FROM media WHERE path=?", (db_path,))
        db_exec("DELETE FROM tags WHERE path=?", (db_path,))
        db_exec("DELETE FROM names WHERE path=?", (db_path,))
        db_exec("DELETE FROM history WHERE path=?", (db_path,))

    for r_dir, _, fs in os.walk(MEDIA_DIR):
        if TRASH_DIR in r_dir or CORRUPT_DIR in r_dir or THUMB_DIR in r_dir or PURGATORY_DIR in r_dir or BACKUP_DIR in r_dir:
            continue
        for f in fs:
            if is_obfuscated_media(f) or is_obfuscated_audio(f):
                fp = os.path.abspath(os.path.join(r_dir, f))
                try:
                    if os.path.getsize(fp) == 0:
                        shutil.move(fp, os.path.join(CORRUPT_DIR, f"{int(time.time()*1000)}____{f}"))
                        db_exec("DELETE FROM media WHERE path=?", (fp,))
                except Exception:
                    pass


def indexer():
    with INDEX_LOCK:
        all_f = [
            (r, f) for r, _, fs in os.walk(MEDIA_DIR)
            if TRASH_DIR not in r and CORRUPT_DIR not in r and THUMB_DIR not in r and PURGATORY_DIR not in r and BACKUP_DIR not in r
            for f in fs
        ]
        config.MEDIA_FILES = [os.path.abspath(os.path.join(r, f)) for r, f in all_f if is_obfuscated_media(f)]
        config.AUDIO_FILES = [os.path.abspath(os.path.join(r, f)) for r, f in all_f if is_obfuscated_audio(f)]

    with FILE_INDEX_LOCK:
        config.FILE_INDEX.clear()
        config.FILE_INDEX_R.clear()
        config.FILE_CTIME.clear()
        config.FILE_SIZE.clear()

        for p in config.MEDIA_FILES + config.AUDIO_FILES:
            fid = hashlib.md5(p.encode('utf-8')).hexdigest()[:16]
            config.FILE_INDEX[fid] = p
            config.FILE_INDEX_R[p] = fid
            try:
                stat_info = os.stat(p)
                config.FILE_CTIME[p] = getattr(stat_info, 'st_birthtime', stat_info.st_ctime)
                config.FILE_SIZE[p] = stat_info.st_size
            except Exception:
                config.FILE_CTIME[p] = 0
                config.FILE_SIZE[p] = 0


# ─── Sauvegarde / restauration d'originaux ─────────────────────────
def _backup_path(filepath):
    fid = hashlib.md5(os.path.abspath(filepath).encode('utf-8')).hexdigest()[:16]
    return os.path.join(BACKUP_DIR, fid + ".bak")


def backup_original_once(filepath):
    bkp = _backup_path(filepath)
    try:
        if not os.path.exists(bkp) and os.path.exists(filepath):
            shutil.copy2(filepath, bkp)
    except Exception:
        pass
    return bkp


def restore_from_backup(filepath):
    bkp = _backup_path(filepath)
    try:
        if os.path.exists(bkp):
            shutil.copy2(bkp, filepath)
            return True
    except Exception:
        pass
    return False


def _remove_if_exists(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def _is_burnable_image(filepath):
    base = filepath[:-EXT_LEN] if filepath.endswith(SVAULT_EXT) else filepath
    ext = os.path.splitext(base)[1].lower()
    return ext in IMG_EXTS and ext != '.gif'


def _decode_image(filepath):
    with open(filepath, 'rb') as f:
        header = f.read(SCRAMBLE_SIZE)
        rest = f.read()
    dec_data = xor_chunk(header, 0) + rest
    img = Image.open(io.BytesIO(dec_data))
    orig_format = (img.format or 'JPEG').upper()
    return img.convert('RGB'), orig_format


def _encode_image(filepath, img, orig_format):
    out_io = io.BytesIO()
    if orig_format == 'PNG':
        img.save(out_io, format='PNG', optimize=False)
    else:
        img.save(out_io, format='JPEG', quality=86)
    new_data = bytearray(out_io.getvalue())
    new_data[:SCRAMBLE_SIZE] = bytearray(xor_chunk(bytes(new_data[:SCRAMBLE_SIZE]), 0))
    with open(filepath, 'wb') as f:
        f.write(new_data)


# ─── Dégradations ──────────────────────────────────────────────────
def live_degrade_image(filepath, wear_ratio):
    if not HAS_PILLOW:
        return False
    if not _is_burnable_image(filepath):
        return False

    if float(wear_ratio) <= 0.05:
        return restore_from_backup(filepath)

    backup_original_once(filepath)

    try:
        img, orig_format = _decode_image(filepath)

        img = ImageEnhance.Color(img).enhance(0.94)
        img = ImageEnhance.Contrast(img).enhance(1.03)

        W, H = img.size
        shifts = random.randint(2, 3)
        for _ in range(shifts):
            band_y = random.randint(0, max(0, H - 4))
            band_h = random.randint(2, 5)
            dx = random.randint(-int(W * 0.025) - 1, int(W * 0.025) + 1)
            if dx == 0:
                continue
            region = img.crop((0, band_y, W, min(H, band_y + band_h)))
            img.paste(region, (dx, band_y))

        _encode_image(filepath, img, orig_format)
        return True
    except Exception as e:
        print(f"Erreur dégradation image: {e}")
        return False


# ─── Brûlures permanentes (Pillow) + réparation par sacrifice ──────
MAX_BURN_REGIONS = 5


def _draw_burn_region(img, rx, ry, rw, rh):
    """Carbonise une zone rectangulaire (coords normalisées 0-1) : centre
    noirci, bords roussis avec bruit organique et contour irrégulier.
    Modifie `img` en place. Effet PERMANENT (écrit sur disque par l'appelant)."""
    W, H = img.size
    x, y = int(rx * W), int(ry * H)
    w, h = max(2, int(rw * W)), max(2, int(rh * H))
    x, y = min(x, W - 1), min(y, H - 1)
    w, h = min(w, W - x), min(h, H - y)

    region = img.crop((x, y, x + w, y + h))
    pixels = region.load()
    for py in range(h):
        for px in range(w):
            nx, ny = (px - w / 2) / (w / 2 + 1e-6), (py - h / 2) / (h / 2 + 1e-6)
            d = (nx * nx + ny * ny) ** 0.5
            if d > 1.0 + random.uniform(-0.15, 0.15):
                continue
            r, g, b = pixels[px, py]
            char = max(0.0, 1.0 - d)  # 1 = centre carbonisé, 0 = bord roussi
            noise = random.randint(-10, 10)
            if char > 0.6:
                v = max(0, 5 + noise)
                pixels[px, py] = (v, v, v)
            else:
                f = char / 0.6
                pixels[px, py] = (int(r * (1 - f) + 40 * f), int(g * (1 - f) + 15 * f), int(b * (1 - f) + 5 * f))
    img.paste(region, (x, y))


def apply_burn_damage(filepath, wear_ratio):
    """Inflige une brûlure permanente supplémentaire (zone carbonisée) sur
    l'image si l'usure est suffisante. La zone (coords normalisées) est
    mémorisée en base pour permettre une réparation ciblée ultérieure via
    repair_burn_region(). Retourne la liste à jour des zones brûlées, ou
    None si l'image n'est pas brûlable."""
    if not HAS_PILLOW or not _is_burnable_image(filepath):
        return None

    regions = database.get_burn_regions(filepath)
    if len(regions) >= MAX_BURN_REGIONS:
        return regions

    backup_original_once(filepath)
    try:
        img, orig_format = _decode_image(filepath)
        rw = min(0.6, random.uniform(0.12, 0.28) * (0.5 + float(wear_ratio)))
        rh = min(0.6, random.uniform(0.12, 0.28) * (0.5 + float(wear_ratio)))
        rx = random.uniform(0, max(0.0, 1 - rw))
        ry = random.uniform(0, max(0.0, 1 - rh))
        _draw_burn_region(img, rx, ry, rw, rh)
        _encode_image(filepath, img, orig_format)
        regions.append({'x': rx, 'y': ry, 'w': rw, 'h': rh})
        database.set_burn_regions(filepath, regions)
        return regions
    except Exception as e:
        print(f"Erreur brûlure image: {e}")
        return regions


def repair_burn_region(filepath, region_index):
    """Réécrit les pixels d'une zone brûlée à partir de la sauvegarde
    d'origine (.sonic_originals) et retire la zone de la liste en base.
    Retourne la liste à jour des zones brûlées, ou None en cas d'échec."""
    if not HAS_PILLOW or not _is_burnable_image(filepath):
        return None
    regions = database.get_burn_regions(filepath)
    if region_index < 0 or region_index >= len(regions):
        return regions

    bkp = _backup_path(filepath)
    if not os.path.exists(bkp):
        return regions

    try:
        img, orig_format = _decode_image(filepath)
        backup_img, _ = _decode_image(bkp)
        W, H = img.size
        if backup_img.size != (W, H):
            backup_img = backup_img.resize((W, H))

        region = regions[region_index]
        x, y = int(region['x'] * W), int(region['y'] * H)
        w, h = max(1, int(region['w'] * W)), max(1, int(region['h'] * H))
        x, y = min(x, W - 1), min(y, H - 1)
        w, h = min(w, W - x), min(h, H - y)
        patch = backup_img.crop((x, y, x + w, y + h))
        img.paste(patch, (x, y))

        _encode_image(filepath, img, orig_format)
        regions.pop(region_index)
        database.set_burn_regions(filepath, regions)
        return regions
    except Exception as e:
        print(f"Erreur réparation brûlure: {e}")
        return regions


def sacrifice_media_violently(filepath):
    """Destruction violente d'un média, en échange d'une réparation ailleurs.
    Image : couvre une grande partie du cadre de brûlures massives en une
    seule passe. Vidéo : double passe de dégradation ffmpeg lourde. Le
    fichier garde une sauvegarde (.sonic_originals) comme tout le reste du
    système d'usure, mais devient quasi entièrement carbonisé/illisible."""
    if not os.path.exists(filepath):
        return False
    base = filepath[:-EXT_LEN] if filepath.endswith(SVAULT_EXT) else filepath
    ext = os.path.splitext(base)[1].lower()

    if ext in VID_EXTS:
        backup_original_once(filepath)
        _video_degrade_pass(filepath)
        _video_degrade_pass(filepath)
        return True

    if not HAS_PILLOW or not _is_burnable_image(filepath):
        return False

    backup_original_once(filepath)
    try:
        img, orig_format = _decode_image(filepath)
        regions = database.get_burn_regions(filepath)
        for _ in range(4):
            rw = random.uniform(0.35, 0.65)
            rh = random.uniform(0.35, 0.65)
            rx = random.uniform(0, max(0.0, 1 - rw))
            ry = random.uniform(0, max(0.0, 1 - rh))
            _draw_burn_region(img, rx, ry, rw, rh)
            regions.append({'x': rx, 'y': ry, 'w': rw, 'h': rh})
        _encode_image(filepath, img, orig_format)
        database.set_burn_regions(filepath, regions[-MAX_BURN_REGIONS:])
        return True
    except Exception as e:
        print(f"Erreur sacrifice: {e}")
        return False


_video_degrade_inflight = set()
_video_degrade_master_lock = threading.Lock()
_video_degrade_version = {}


def _video_degrade_pass(filepath):
    base = filepath[:-EXT_LEN] if filepath.endswith(SVAULT_EXT) else filepath
    ext = os.path.splitext(base)[1].lower()
    if ext not in VID_EXTS:
        return
    if not os.path.exists(filepath):
        return

    backup_original_once(filepath)

    temp_dec = filepath + ".dec.mp4"
    temp_out = filepath + ".out.mp4"
    try:
        with open(filepath, 'rb') as f:
            header = f.read(SCRAMBLE_SIZE)
            rest = f.read()
        dec_data = xor_chunk(header, 0) + rest
        with open(temp_dec, 'wb') as f:
            f.write(dec_data)

        cmd = [
            'ffmpeg', '-y', '-i', temp_dec,
            '-vf', 'noise=alls=4:allf=t',
            '-b:v', '1500k', '-c:a', 'copy', temp_out
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)

        if os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
            with open(temp_out, 'rb') as f:
                final_data = bytearray(f.read())
            final_data[:SCRAMBLE_SIZE] = bytearray(xor_chunk(bytes(final_data[:SCRAMBLE_SIZE]), 0))
            with open(filepath, 'wb') as f:
                f.write(final_data)
    except Exception as e:
        print(f"Erreur dégradation vidéo: {e}")
    finally:
        _remove_if_exists(temp_dec, temp_out)


def schedule_video_degrade(filepath):
    with _video_degrade_master_lock:
        if filepath in _video_degrade_inflight:
            return False
        _video_degrade_inflight.add(filepath)

    def worker():
        try:
            _video_degrade_pass(filepath)
        finally:
            with _video_degrade_master_lock:
                _video_degrade_inflight.discard(filepath)
                _video_degrade_version[filepath] = _video_degrade_version.get(filepath, 0) + 1

    threading.Thread(target=worker, daemon=True).start()
    return True


def get_video_degrade_version(filepath):
    return _video_degrade_version.get(filepath, 0)


def live_degrade_video(filepath, wear_ratio):
    if float(wear_ratio) <= 0.05:
        if restore_from_backup(filepath):
            _video_degrade_version[filepath] = _video_degrade_version.get(filepath, 0) + 1
        return
    schedule_video_degrade(filepath)


def degrade_media_permanently(filepath):
    backup_original_once(filepath)
    live_degrade_image(filepath, 0.4)

    base = filepath[:-EXT_LEN] if filepath.endswith(SVAULT_EXT) else filepath
    ext = os.path.splitext(base)[1].lower()
    if ext in VID_EXTS:
        temp_dec = None
        temp_out = None
        try:
            temp_dec = filepath + ".dec.mp4"
            temp_out = filepath + ".out.mp4"
            with open(filepath, 'r+b') as f:
                header = f.read(SCRAMBLE_SIZE)
                rest = f.read()
                dec_data = xor_chunk(header, 0) + rest
            with open(temp_dec, 'wb') as f:
                f.write(dec_data)

            cmd = [
                'ffmpeg', '-y', '-i', temp_dec,
                '-vf', 'noise=alls=7:allf=t',
                '-b:v', '1200k', '-c:a', 'copy', temp_out
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
                with open(temp_out, 'rb') as f:
                    final_data = bytearray(f.read())
                final_data[:SCRAMBLE_SIZE] = bytearray(xor_chunk(bytes(final_data[:SCRAMBLE_SIZE]), 0))
                with open(filepath, 'wb') as f:
                    f.write(final_data)
        except Exception:
            pass
        finally:
            _remove_if_exists(temp_dec, temp_out)


def check_and_set_wallpaper():
    if not HAS_PILLOW:
        return
    now = datetime.datetime.now()
    if 0 <= now.hour < 7:
        with INDEX_LOCK:
            images_coffre = [f for f in config.MEDIA_FILES if not is_obfuscated_video(f)]
        if not images_coffre:
            return
        img_file = random.choice(images_coffre)
        temp_wp = os.path.join(THUMB_DIR, "temp_wallpaper.jpg")
        try:
            with open(img_file, 'rb') as f:
                buf = bytearray(f.read())
            buf[:SCRAMBLE_SIZE] = xor_chunk(buf[:SCRAMBLE_SIZE], 0)
            with Image.open(io.BytesIO(buf)) as img:
                img = img.convert('RGB')
                img.save(temp_wp, "JPEG")
            subprocess.run(['termux-wallpaper', '-f', temp_wp], capture_output=True)
            os.remove(temp_wp)
        except Exception:
            pass


# ─── Icônes PWA / manifest ─────────────────────────────────────────
_WITCH_ICON_CACHE = {}


def _png_chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", binascii.crc32(tag + data) & 0xffffffff)


def _make_simple_png(size, bg=(3, 3, 5), fg=(255, 0, 255)):
    """Génère une icône PNG minimale (cadre + cercle) sans dépendance externe.
    Repli utilisé quand Pillow est absent, pour que la PWA reste installable
    (Chrome exige des icônes PNG valides, pas seulement du SVG)."""
    cx = cy = size / 2.0
    r = size * 0.30
    border = max(2, size // 40)
    margin = int(size * 0.16)
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filtre PNG "None"
        for x in range(size):
            dx, dy = x - cx, y - cy
            in_frame = margin <= x < size - margin and margin <= y < size - margin
            on_ring = in_frame and (x < margin + border or x >= size - margin - border
                                     or y < margin + border or y >= size - margin - border)
            if dx * dx + dy * dy <= r * r or on_ring:
                raw.extend(fg)
            else:
                raw.extend(bg)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    out = b'\x89PNG\r\n\x1a\n'
    out += _png_chunk(b'IHDR', ihdr)
    out += _png_chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    out += _png_chunk(b'IEND', b'')
    return out


def _witch_icon_png(size=512):
    # Génère (et met en cache) une icône PNG pour l'installation PWA.
    if size in _WITCH_ICON_CACHE:
        return _WITCH_ICON_CACHE[size]
    if not HAS_PILLOW:
        png = _make_simple_png(size, bg=(18, 12, 26), fg=(179, 136, 255))
        _WITCH_ICON_CACHE[size] = png
        return png
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (size, size), (18, 12, 26))
        dr = ImageDraw.Draw(img)
        c = size // 2
        dr.ellipse([c-int(size*0.33), c-int(size*0.33), c+int(size*0.33), c+int(size*0.33)], outline=(179,136,255), width=max(3,size//85))
        dr.ellipse([c-int(size*0.23), c-int(size*0.23), c+int(size*0.23), c+int(size*0.23)], outline=(120,90,180), width=max(2,size//170))
        dr.polygon([(c, int(size*0.19)), (int(size*0.58), c), (c, int(size*0.81)), (int(size*0.42), c)], fill=(179,136,255))
        try:
            font = ImageFont.truetype("DejaVuSerif.ttf", size//4)
        except Exception:
            font = ImageFont.load_default()
        txt = "XIII"
        try:
            bbox = dr.textbbox((0,0), txt, font=font); tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        except Exception:
            tw, th = dr.textsize(txt, font=font)
        dr.text((c - tw/2, c - th/2 + size*0.02), txt, fill=(232,224,240), font=font)
        import io as _io
        buf = _io.BytesIO(); img.save(buf, "PNG")
        _WITCH_ICON_CACHE[size] = buf.getvalue()
        return _WITCH_ICON_CACHE[size]
    except Exception:
        return None


_GALLERY_ICON_CACHE = {}


def _gallery_icon_png(size=512):
    # Icône PNG (thème magenta) pour l'installation PWA de la galerie principale.
    if size in _GALLERY_ICON_CACHE:
        return _GALLERY_ICON_CACHE[size]
    if not HAS_PILLOW:
        png = _make_simple_png(size, bg=(3, 3, 5), fg=(255, 0, 255))
        _GALLERY_ICON_CACHE[size] = png
        return png
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (size, size), (3, 3, 5))
        dr = ImageDraw.Draw(img)
        m = int(size * 0.16)
        # Cadre type "photo"
        dr.rounded_rectangle([m, m, size - m, size - m], radius=int(size*0.10),
                             outline=(255, 0, 255), width=max(3, size // 40))
        # Montagne + soleil (pictogramme galerie)
        dr.ellipse([int(size*0.30), int(size*0.30), int(size*0.42), int(size*0.42)], fill=(255, 0, 255))
        dr.polygon([(int(size*0.28), int(size*0.70)), (int(size*0.46), int(size*0.46)),
                    (int(size*0.60), int(size*0.70))], fill=(255, 0, 255))
        dr.polygon([(int(size*0.50), int(size*0.70)), (int(size*0.64), int(size*0.52)),
                    (int(size*0.74), int(size*0.70))], fill=(200, 0, 200))
        import io as _io
        buf = _io.BytesIO(); img.save(buf, "PNG")
        _GALLERY_ICON_CACHE[size] = buf.getvalue()
        return _GALLERY_ICON_CACHE[size]
    except Exception:
        return None


GALLERY_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
    '<rect width="512" height="512" fill="#030305"/>'
    '<rect x="82" y="82" width="348" height="348" rx="52" fill="none" stroke="#ff00ff" stroke-width="14"/>'
    '<circle cx="184" cy="184" r="34" fill="#ff00ff"/>'
    '<path d="M143 358 L235 235 L307 358 Z" fill="#ff00ff"/>'
    '<path d="M256 358 L329 266 L380 358 Z" fill="#c800c8"/>'
    '</svg>'
)

GALLERY_MANIFEST = {
    "name": "Gallery Pro",
    "short_name": "Gallery",
    "id": "/",
    "scope": "/",
    "start_url": "/",
    "display": "fullscreen",
    "display_override": ["fullscreen", "standalone"],
    "orientation": "portrait",
    "background_color": "#030305",
    "theme_color": "#000000",
    "icons": [
        {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
}
