# ═══════════════════════════════════════════════════════════════════
# server.py — serveur HTTP threadé + handler
# ═══════════════════════════════════════════════════════════════════
import os
import re
import json
import time
import random
import shutil
import hashlib
import datetime
import mimetypes
import threading
import subprocess
import http.server
import socketserver
import urllib.parse

import config
from config import (BASE_DIR, MEDIA_DIR, PORT, THUMB_DIR, TRASH_DIR,
                    SVAULT_EXT, EXT_LEN, SCRAMBLE_SIZE, PURGATORY_KEY,
                    MIME_MAP, INDEX_LOCK)
import database
from database import (db_exec, db_fetch, db_fetchone, is_obfuscated_video,
                      get_effective_quota, get_all_unique_names,
                      update_views, toggle_like, toggle_vault, set_rating,
                      set_note, add_hist, sync_tags, sync_names)
import media
from media import (INDEX_HTML, WITCH_UI_HTML, GALLERY_MANIFEST, GALLERY_ICON_SVG,
                   color_distance, get_stats, indexer, live_degrade_image,
                   live_degrade_video, _gallery_icon_png)
import witch_game
from witch_game import (WITCHES, ITEMS, TACTICS, ROLE_COUNTER_HINT,
                        new_game, load_game, save_game, room_obj, visible_exits,
                        lock_msg, rest, use_item, add_xp, resolve_combat,
                        apply_combat, MAP)
import workers
from workers import equalize_video_views_task
from security import (xor_chunk, lock_database, unlock_purgatory_file)
from media import _witch_icon_png


class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    def handle_error(self, request, client_address): pass


class GalleryHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def send_json(self, data, code=200):
        b = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        try:
            parsed_url = urllib.parse.urlparse(self.path)
            path = parsed_url.path
            q = urllib.parse.parse_qs(parsed_url.query)

            if path in ('/', '/index.html'):
                # FIX: HTML embarqué (fichier unique) — plus de dépendance à index.html
                b = INDEX_HTML.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return

            if path == '/api/batch':
                if not config.SESSION_KEY_ACTIVE and not config.BURN_MODE_SERVER:
                    self.send_json({'files': [], 'locked': True})
                    return
                mode = q.get('mode', ['all'])[0]
                sort = q.get('sort', ['unseen'])[0]
                minr = int(q.get('minr', ['0'])[0])
                limit = int(q.get('limit', ['999999'])[0])
                color_filter = q.get('color', [''])[0]
                vault_req = q.get('vault', ['false'])[0] == 'true'
                demo_filter = q.get('demo', ['all'])[0]

                with INDEX_LOCK: pool = list(config.MEDIA_FILES)

                rows = db_fetch("SELECT path, views, rating, liked, r, g, b, corrupted, vault, phash, faces_data, demographics FROM media")
                db_cache = {r[0]: {
                    'views': r[1], 'rating': r[2], 'liked': bool(r[3]),
                    'color': [r[4],r[5],r[6]] if r[4] != -1 else None,
                    'corrupted': bool(r[7]), 'vault': bool(r[8]), 'phash': r[9],
                    'faces_data': r[10], 'demographics': r[11]
                } for r in rows}
                def get_d(f): return db_cache.get(f, {'views':0,'rating':0,'liked':False,'color':None,'corrupted':False,'vault':False,'phash':'','faces_data':'','demographics':''})

                if vault_req: pool = [f for f in pool if get_d(f)['vault']]
                else: pool = [f for f in pool if not get_d(f)['corrupted'] and not get_d(f)['vault']]

                if mode == 'narcisse': pool = [f for f in pool if get_d(f)['faces_data'] not in ('', '[]')]
                elif mode == 'fav': pool = [f for f in pool if get_d(f)['liked']]
                elif mode == 'video': pool = [f for f in pool if is_obfuscated_video(f)]
                elif mode == 'image': pool = [f for f in pool if not is_obfuscated_video(f)]
                elif mode == 'hist':
                    hist_rows = [x[0] for x in db_fetch("SELECT path FROM history ORDER BY ts DESC LIMIT 3000")]
                    pool = [f for f in hist_rows if f in pool]

                if minr > 0: pool = [f for f in pool if get_d(f)['rating'] >= minr]
                if demo_filter != 'all': pool = [f for f in pool if get_d(f)['demographics'] == demo_filter]

                if color_filter:
                    t_col = tuple(map(int, color_filter.split(',')))
                    pool = [f for f in pool if get_d(f)['color'] is not None]
                    pool.sort(key=lambda x: color_distance(get_d(x)['color'], t_col))
                else:
                    if sort == 'date': pool.sort(key=lambda x: config.FILE_CTIME.get(x, 0), reverse=True)
                    elif sort == 'date_asc': pool.sort(key=lambda x: config.FILE_CTIME.get(x, 0))
                    elif sort == 'size': pool.sort(key=lambda x: config.FILE_SIZE.get(x, 0), reverse=True)
                    elif sort == 'size_asc': pool.sort(key=lambda x: config.FILE_SIZE.get(x, 0))
                    elif sort == 'name': pool.sort(key=lambda x: os.path.basename(x).lower())
                    elif sort == 'namedesc': pool.sort(key=lambda x: os.path.basename(x).lower(), reverse=True)
                    elif sort == 'rate': random.shuffle(pool); pool.sort(key=lambda x: get_d(x)['rating'], reverse=True)
                    elif sort == 'unseen': random.shuffle(pool); pool.sort(key=lambda x: get_d(x)['views'])
                    elif sort == 'viewed': random.shuffle(pool); pool.sort(key=lambda x: get_d(x)['views'], reverse=True)
                    else: random.shuffle(pool)

                limited = pool[:limit]
                if limited:
                    tags_rows, names_rows, notes_rows = [], [], []
                    for i in range(0, len(limited), 900):
                        chunk = limited[i:i+900]
                        ph = ','.join('?' * len(chunk))
                        tags_rows.extend(db_fetch(f"SELECT path, tag  FROM tags  WHERE path IN ({ph})", chunk))
                        names_rows.extend(db_fetch(f"SELECT path, name FROM names WHERE path IN ({ph})", chunk))
                        notes_rows.extend(db_fetch(f"SELECT path, note FROM media WHERE path IN ({ph})", chunk))
                else: tags_rows = names_rows = notes_rows = []

                tags_map, names_map = {}, {}
                for p, t in tags_rows: tags_map.setdefault(p, []).append(t)
                for p, n in names_rows: names_map.setdefault(p, []).append(n)
                notes_map = {p: note for p, note in notes_rows}

                res = []
                for f in limited:
                    d = get_d(f)
                    res.append({
                        'file': f'/f/{config.FILE_INDEX_R.get(f, "")}',
                        'liked': d['liked'], 'tags': tags_map.get(f, []), 'names': names_map.get(f, []),
                        'rating': d['rating'], 'note': notes_map.get(f, ''), 'views': d['views'], 'video': is_obfuscated_video(f),
                        'faces_data': d['faces_data'], 'demographics': d['demographics'],
                        'size': config.FILE_SIZE.get(f, 0),
                        'ctime': config.FILE_CTIME.get(f, 0)
                    })
                self.send_json(res)
                return

            if path == '/api/all_names': return self.send_json(get_all_unique_names())
            if path == '/api/audio': return self.send_json([f'/f/{config.FILE_INDEX_R.get(p,"")}' for p in list(config.AUDIO_FILES)])
            if path == '/api/stats': return self.send_json(get_stats())

            if path == '/api/config_get':
                rows = db_fetch("SELECT key, value FROM global_config WHERE key IN ('purgatory_base', 'purgatory_mult')")
                conf = {r[0]: r[1] for r in rows}
                return self.send_json(conf)

            if path == '/api/purgatory':
                now = time.time()
                rows = db_fetch("SELECT original_path, delete_time FROM purgatory")
                res = []
                for r in rows:
                    orig_path = r[0]
                    del_time = r[1]
                    fid = hashlib.md5(orig_path.encode('utf-8')).hexdigest()[:16]
                    res.append({
                        'fid': fid,
                        'name': os.path.basename(orig_path),
                        'restore_in': max(0, del_time - now)
                    })
                return self.send_json(res)

            if path == '/api/purgatory_media':
                try:
                    fid_req = q.get('fid', [''])[0]
                    if not fid_req:
                        self.send_error(400, "Missing fid"); return
                    rows = db_fetch("SELECT path, original_path FROM purgatory")
                    dead_path = None; orig_ext = ''
                    for r in rows:
                        p_dead, o_path = r[0], r[1]
                        if hashlib.md5(o_path.encode('utf-8')).hexdigest()[:16] == fid_req:
                            dead_path = p_dead
                            base = o_path[:-EXT_LEN] if o_path.endswith(SVAULT_EXT) else o_path
                            orig_ext = os.path.splitext(base)[1].lower()
                            break
                    if not dead_path or not os.path.exists(dead_path):
                        self.send_error(404, "Not Found"); return
                    with open(dead_path, 'rb') as f:
                        data = bytearray(f.read())
                    lock_size = min(1024 * 1024, len(data))
                    chunk = bytearray(data[:lock_size])
                    chunk.reverse()
                    key_len = len(PURGATORY_KEY)
                    for i in range(len(chunk)):
                        chunk[i] ^= PURGATORY_KEY[i % key_len]
                    data[:lock_size] = chunk
                    xor_end = min(SCRAMBLE_SIZE, len(data))
                    data[:xor_end] = bytearray(xor_chunk(bytes(data[:xor_end]), 0))
                    mime = MIME_MAP.get(orig_ext, 'application/octet-stream')
                    b = bytes(data)
                    self.send_response(200)
                    self.send_header('Content-Type', mime)
                    self.send_header('Content-Length', str(len(b)))
                    self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                    self.end_headers()
                    self.wfile.write(b)
                except (BrokenPipeError, ConnectionResetError): pass
                except Exception: self.send_error(500, "Erreur décryptage")
                return

            # === ROUTES DU JEU "LES TREIZE VOILES" ===
            if path == '/witch' or path == '/witch/':
                b = WITCH_UI_HTML.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers(); self.wfile.write(b); return

            if path == '/witch/manifest.json':
                manifest = json.dumps({
                    "name":"Les Treize Voiles","short_name":"Treize Voiles",
                    "id":"/witch","scope":"/witch","start_url":"/witch",
                    "display":"fullscreen","display_override":["fullscreen","standalone"],
                    "orientation":"portrait",
                    "background_color":"#0a0710","theme_color":"#120c1a",
                    "icons":[
                        {"src":"/witch/icon.svg","sizes":"any","type":"image/svg+xml","purpose":"any"},
                        {"src":"/witch/icon-192.png","sizes":"192x192","type":"image/png","purpose":"any maskable"},
                        {"src":"/witch/icon-512.png","sizes":"512x512","type":"image/png","purpose":"any maskable"}
                    ]
                }).encode('utf-8')
                self.send_response(200); self.send_header('Content-Type','application/manifest+json')
                self.send_header('Content-Length', str(len(manifest))); self.end_headers()
                self.wfile.write(manifest); return

            if path == '/witch/icon.svg':
                svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
                       '<rect width="512" height="512" fill="#120c1a"/>'
                       '<circle cx="256" cy="256" r="170" fill="none" stroke="#b388ff" stroke-width="6" opacity="0.9"/>'
                       '<circle cx="256" cy="256" r="120" fill="none" stroke="#b388ff" stroke-width="3" opacity="0.5"/>'
                       '<path d="M256 96 L296 232 L256 416 L216 232 Z" fill="#b388ff" opacity="0.85"/>'
                       '<text x="256" y="300" font-size="150" text-anchor="middle" fill="#e8e0f0" font-family="Georgia,serif">XIII</text>'
                       '</svg>').encode('utf-8')
                self.send_response(200); self.send_header('Content-Type','image/svg+xml')
                self.send_header('Cache-Control','max-age=86400')
                self.send_header('Content-Length', str(len(svg))); self.end_headers()
                self.wfile.write(svg); return

            if path in ('/witch/icon-192.png','/witch/icon-512.png'):
                png = _witch_icon_png()
                if png:
                    self.send_response(200); self.send_header('Content-Type','image/png')
                    self.send_header('Cache-Control','max-age=86400')
                    self.send_header('Content-Length', str(len(png))); self.end_headers()
                    self.wfile.write(png); return
                self.send_error(404); return

            if path == '/witch/sw.js':
                sw_content = ("const C='voiles-v1';\n"
                    "self.addEventListener('install', e => self.skipWaiting());\n"
                    "self.addEventListener('activate', e => e.waitUntil(clients.claim()));\n"
                    "self.addEventListener('fetch', e => { e.respondWith(fetch(e.request).catch(()=>caches.match(e.request))); });\n").encode('utf-8')
                self.send_response(200); self.send_header('Content-Type','application/javascript')
                self.send_header('Content-Length', str(len(sw_content))); self.end_headers()
                self.wfile.write(sw_content); return

            if path == '/manifest.json':
                b = json.dumps(GALLERY_MANIFEST).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/manifest+json')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers(); self.wfile.write(b); return

            if path == '/icon.svg':
                b = GALLERY_ICON_SVG.encode('utf-8')
                self.send_response(200); self.send_header('Content-Type', 'image/svg+xml')
                self.send_header('Cache-Control', 'max-age=86400')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers(); self.wfile.write(b); return

            if path in ('/icon-192.png', '/icon-512.png'):
                size = 192 if path == '/icon-192.png' else 512
                png = _gallery_icon_png(size)
                if png:
                    self.send_response(200); self.send_header('Content-Type', 'image/png')
                    self.send_header('Cache-Control', 'max-age=86400')
                    self.send_header('Content-Length', str(len(png)))
                    self.end_headers(); self.wfile.write(png); return
                # Repli : renvoyer le SVG si Pillow est absent
                b = GALLERY_ICON_SVG.encode('utf-8')
                self.send_response(200); self.send_header('Content-Type', 'image/svg+xml')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers(); self.wfile.write(b); return

            if path == '/sw.js':
                sw_content = ("self.addEventListener('install', e => self.skipWaiting());\nself.addEventListener('activate', e => e.waitUntil(clients.claim()));\nself.addEventListener('fetch', e => e.respondWith(fetch(e.request)));\n").encode('utf-8')
                self.send_response(200); self.send_header('Content-Type', 'application/javascript'); self.end_headers(); self.wfile.write(sw_content)
                return

            if path.startswith('/t/') or path.startswith('/f/'):
                try:
                    fid = path[3:]
                    fp = config.FILE_INDEX.get(fid)
                    if fp:
                        if path.startswith('/t/'):
                            thumb_path = os.path.join(THUMB_DIR, fid + ".jpg")
                            if os.path.exists(thumb_path):
                                self._serve_file_with_range(thumb_path, 'image/jpeg', is_thumb=True)
                                return
                            if is_obfuscated_video(os.path.basename(fp)):
                                self.send_error(404, "Miniature Vidéo En Attente")
                                return
                        if os.path.exists(fp):
                            ext = os.path.splitext(fp[:-EXT_LEN])[1].lower()
                            mime = MIME_MAP.get(ext) or mimetypes.guess_type(fp[:-EXT_LEN])[0] or 'application/octet-stream'
                            self._serve_file_with_range(fp, mime, is_thumb=False)
                            return
                    if path.startswith('/t/'):
                        thumb_path = os.path.join(THUMB_DIR, fid + ".jpg")
                        if os.path.exists(thumb_path):
                            self._serve_file_with_range(thumb_path, 'image/jpeg', is_thumb=True)
                            return
                except Exception: pass
                self.send_error(404, "Not Found")
                return

            self.send_error(404, "Not Found")
        except BrokenPipeError: pass
        except Exception: pass

    CHUNK = 1024 * 1024

    def _serve_file_with_range(self, fp, ct, is_thumb=False):
        try:
            file_size = os.path.getsize(fp)
            fh = open(fp, 'rb')
        except OSError: return

        try:
            raw_range = self.headers.get('Range', '').strip()
            start, end, is_range = 0, file_size - 1, False

            if raw_range and file_size > 0:
                m = re.fullmatch(r'[Bb]ytes=(\d+)?-(\d+)?', raw_range)
                if m and (m.group(1) is not None or m.group(2) is not None):
                    s_str, e_str = m.group(1), m.group(2)
                    if s_str is None: start = max(0, file_size - int(e_str))
                    elif e_str is None: start = int(s_str)
                    else: start, end = int(s_str), int(e_str)
                    end = min(end, file_size - 1)
                    is_range = True

            length = end - start + 1
            self.send_response(206 if is_range else 200)
            self.send_header('Content-Type', ct)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(length))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            if is_range: self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
            self.end_headers()

            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(self.CHUNK, remaining))
                if not chunk: break
                if not is_thumb:
                    chunk = xor_chunk(chunk, fh.tell() - len(chunk))
                self.wfile.write(chunk)
                remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError): pass
        finally: fh.close()

    def do_POST(self):
        try:
            try:
                n = int(self.headers.get('Content-Length', 0))
                d = json.loads(self.rfile.read(n)) if n else {}
            except (json.JSONDecodeError, ValueError):
                self.send_json({'ok': False, 'err': 'JSON invalide'}, code=400)
                return
            path = urllib.parse.urlparse(self.path).path
            fp_db = None
            if d.get('file') and str(d.get('file')).startswith('/f/'):
                fp_db = config.FILE_INDEX.get(d.get('file')[3:])

            # --- ENDPOINT : DÉGRADATION INCRÉMENTALE (image OU vidéo) ---
            # Appelé en continu pendant le visionnage : corrompt le fichier sur
            # disque en place, pour que le client recharge le média dégradé
            # SANS avoir besoin de naviguer (next/prev).
            if path == '/api/degrade_live':
                wear_ratio = float(d.get('wear_ratio', 0.0))
                resp = {'ok': True}
                if fp_db and os.path.exists(fp_db):
                    base = fp_db[:-EXT_LEN] if fp_db.endswith(SVAULT_EXT) else fp_db
                    ext = os.path.splitext(base)[1].lower()
                    if ext in config.VID_EXTS:
                        live_degrade_video(fp_db, wear_ratio)
                        resp['video_version'] = media.get_video_degrade_version(fp_db)
                    else:
                        resp['changed'] = live_degrade_image(fp_db, wear_ratio)
                self.send_json(resp)

            # === API DU JEU "LES TREIZE VOILES" ===
            elif path.startswith('/witch/api/'):
                action = path[len('/witch/api/'):]
                profile = str(d.get('profile', 'default'))

                if action == 'meta':
                    # Expose witches (avec rôle/hint/niveau), items, tactics, et assets médias
                    with INDEX_LOCK:
                        imgs = [config.FILE_INDEX_R[f] for f in config.MEDIA_FILES if not is_obfuscated_video(f) and f in config.FILE_INDEX_R]
                        vids = [config.FILE_INDEX_R[f] for f in config.MEDIA_FILES if is_obfuscated_video(f) and f in config.FILE_INDEX_R]
                    witches_out = {}
                    for w in WITCHES:
                        witches_out[w['id']] = {
                            'id': w['id'], 'nom': w['nom'], 'niveau': w['niveau'],
                            'desc': w['desc'], 'intro': w['intro'], 'win': w['win'],
                            'roleLabel': w['role'], 'counter': w['counter'],
                            'hint': ROLE_COUNTER_HINT.get(w['role'], ''),
                        }
                    self.send_json({
                        'witches': witches_out, 'items': ITEMS, 'tactics': TACTICS,
                        'assets': {'images': imgs, 'videos': vids},
                    }); return

                if action == 'new':
                    st = new_game(d.get('origin', 'intrus'))
                    save_game(BASE_DIR, profile, st)
                    self.send_json({'state': st}); return

                if action == 'load':
                    st = load_game(BASE_DIR, profile)
                    self.send_json({'state': st}); return

                if action == 'save':
                    st = d.get('state')
                    if st: save_game(BASE_DIR, profile, st)
                    self.send_json({'ok': True}); return

                # actions nécessitant l'état serveur courant
                st = load_game(BASE_DIR, profile)
                if not st:
                    self.send_json({'ok': False, 'msg': 'Pas de partie'}); return

                if action == 'room':
                    zone, rid, room = room_obj(st['room'])
                    if not room:
                        self.send_json({'ok': False, 'msg': 'Salle introuvable'}); return
                    z = MAP.get(zone, {})
                    rout = {'nom': room['nom'], 'desc': room['desc'],
                            'witch': room.get('witch'), 'search': room.get('search')}
                    self.send_json({'state': st, 'room': rout,
                                    'zoneName': z.get('nom', zone), 'zoneColor': z.get('color', '#2a2030'),
                                    'exits': visible_exits(st)}); return

                if action == 'move':
                    to = d.get('to')
                    exits = {e['key']: e for e in visible_exits(st)}
                    if to not in exits:
                        self.send_json({'ok': False, 'msg': 'Sortie inconnue', 'state': st}); return
                    if exits[to]['locked']:
                        self.send_json({'ok': False, 'msg': lock_msg(exits[to]['reason']), 'state': st}); return
                    st['room'] = to
                    if to not in st['visited']:
                        st['visited'].append(to)
                    save_game(BASE_DIR, profile, st)
                    self.send_json({'ok': True, 'state': st}); return

                if action == 'search':
                    zone, rid, room = room_obj(st['room'])
                    flag = 'searched_' + st['room']
                    found = None
                    if room and room.get('search') and not st['flags'].get(flag):
                        found = room['search']
                        if found not in st['inventory']:
                            st['inventory'].append(found)
                        st['flags'][flag] = True
                        add_xp(st, 4)
                    save_game(BASE_DIR, profile, st)
                    self.send_json({'state': st, 'found': found}); return

                if action == 'rest':
                    g = rest(st)
                    save_game(BASE_DIR, profile, st)
                    self.send_json({'state': st, 'gain': g}); return

                if action == 'use_item':
                    iid = d.get('item')
                    msg = use_item(st, iid)
                    save_game(BASE_DIR, profile, st)
                    self.send_json({'state': st, 'msg': msg}); return

                if action == 'combat':
                    wid = d.get('witch'); tactic = d.get('tactic')
                    prev_lvl = st['level']
                    if tactic == '__ember__' and 'ember' in st['inventory']:
                        st['inventory'].remove('ember')
                        w = next(x for x in WITCHES if x['id'] == wid)
                        outcome = {'witch': wid, 'result': 'win', 'will_delta': 0,
                                   'grip_delta': 0, 'xp': 8 + w['niveau'] * 4, 'text': w['win'], 'correct': True}
                        apply_combat(st, wid, outcome)
                    else:
                        outcome = resolve_combat(st, wid, tactic)
                        apply_combat(st, wid, outcome)
                    outcome['levelup'] = st['level'] > prev_lvl
                    outcome['marked'] = (wid in st['marks'])
                    save_game(BASE_DIR, profile, st)
                    self.send_json({'state': st, 'outcome': outcome}); return

                self.send_json({'ok': False, 'msg': 'Action inconnue'}, code=404); return

            elif path == '/api/burn_enter':
                config.BURN_MODE_SERVER = True
                indexer()
                self.send_json({'ok': True})

            elif path == '/api/burn_exit':
                config.BURN_MODE_SERVER = False
                self.send_json({'ok': True})

            elif path == '/api/config_set':
                p_base = str(d.get('purgatory_base', '0'))
                p_mult = str(d.get('purgatory_mult', '1.0'))
                db_exec("UPDATE global_config SET value=? WHERE key='purgatory_base'", (p_base,))
                db_exec("UPDATE global_config SET value=? WHERE key='purgatory_mult'", (p_mult,))
                self.send_json({'ok': True})

            elif path == '/api/secure_backup':
                def backup_task():
                    try:
                        subprocess.run(['rclone', 'sync', MEDIA_DIR, 'secret_drive:Backup/SonicShield', '--exclude', f'*{TRASH_DIR}*', '--exclude', f'*{THUMB_DIR}*'], timeout=600)
                    except Exception: pass
                threading.Thread(target=backup_task, daemon=True).start()
                self.send_json({'ok': True})

            elif path == '/api/like': self.send_json({'liked': toggle_like(fp_db)} if fp_db else {'liked': False})
            elif path == '/api/vault': self.send_json({'vaulted': toggle_vault(fp_db)} if fp_db else {'vaulted': False})
            elif path == '/api/rate': set_rating(fp_db, d['stars']); self.send_json({'ok': True})
            elif path == '/api/tag': sync_tags(fp_db, d['tags']); self.send_json({'ok': True})
            elif path == '/api/name': sync_names(fp_db, d['names']); self.send_json({'ok': True})
            elif path == '/api/note': set_note(fp_db, d['note']); self.send_json({'ok': True})
            elif path == '/api/hist': add_hist(fp_db); self.send_json({'ok': True})
            elif path == '/api/view': self.send_json({'ok': True, 'views': update_views(fp_db, d.get('add', 1)) if fp_db else 0})

            elif path == '/api/reset_views':
                if fp_db:
                    db_exec("UPDATE media SET views=0 WHERE path=?", (fp_db,))
                self.send_json({'ok': True, 'views': 0})

            elif path == '/api/save_faces':
                if fp_db:
                    db_exec("UPDATE media SET faces_data=?, demographics=? WHERE path=?", (json.dumps(d.get('faces', [])), d.get('demographics', ''), fp_db))
                self.send_json({'ok': True})

            elif path == '/api/ping_time':
                ping_sec = d.get('ping_seconds', 10)
                db_exec("UPDATE global_stats SET value = value + ? WHERE key = 'total_time'", (ping_sec,))

                if config.SESSION_KEY_ACTIVE:
                    today = datetime.date.today().isoformat()
                    row = db_fetchone("SELECT value FROM global_config WHERE key='last_reset_date'")
                    last_date = row[0] if row else ''
                    if last_date != today:
                        db_exec("UPDATE global_config SET value=? WHERE key='last_reset_date'", (today,))
                        db_exec("UPDATE global_stats SET value=0 WHERE key='daily_time'")

                    db_exec("UPDATE global_stats SET value = value + ? WHERE key = 'daily_time'", (ping_sec,))
                    row = db_fetchone("SELECT value FROM global_stats WHERE key='daily_time'")
                    daily_time = row[0] if row else 0
                    eff_quota = get_effective_quota()
                    remaining = max(0, eff_quota - daily_time)

                    if daily_time >= eff_quota:
                        def do_lockdown():
                            if config.LOCKDOWN_TRIGGERED: return
                            config.LOCKDOWN_TRIGGERED = True
                            config.SESSION_KEY_ACTIVE = False
                            time.sleep(3)
                            lock_database()
                        threading.Thread(target=do_lockdown, daemon=True).start()
                        self.send_json({'ok': True, 'locked': True, 'remaining': 0, 'quota': eff_quota})
                    else:
                        self.send_json({'ok': True, 'locked': False, 'remaining': remaining, 'quota': eff_quota})
                else:
                    self.send_json({'ok': True, 'locked': True, 'remaining': 0})

            elif path == '/api/equalize_views':
                threading.Thread(target=equalize_video_views_task, daemon=True).start()
                self.send_json({'ok': True})
            elif path == '/api/reindex':
                threading.Thread(target=indexer, daemon=True).start()
                self.send_json({'ok': True})
            elif path == '/api/purge_db':
                db_exec("DELETE FROM media"); db_exec("DELETE FROM tags"); db_exec("DELETE FROM names"); db_exec("DELETE FROM history")
                self.send_json({'ok': True})
            elif path == '/api/corrupt':
                if fp_db:
                    db_exec("INSERT OR IGNORE INTO media (path) VALUES (?)", (fp_db,))
                    db_exec("UPDATE media SET corrupted=1 WHERE path=?", (fp_db,))
                self.send_json({'ok': True})

            # --- AMNISTIE GÉNÉRALE ---
            elif path == '/api/purgatory_amnistie':
                rows = db_fetch("SELECT path, original_path FROM purgatory")
                count = 0
                for r in rows:
                    p_dead, o_path = r[0], r[1]
                    try:
                        unlock_purgatory_file(p_dead)
                        os.makedirs(os.path.dirname(o_path), exist_ok=True)
                        shutil.move(p_dead, o_path)
                        db_exec("DELETE FROM purgatory WHERE path=?", (p_dead,))
                        count += 1
                    except Exception: pass
                indexer()
                self.send_json({'ok': True, 'count': count})

            # --- EXÉCUTION DÉFINITIVE (SUPPRESSION) ---
            elif path == '/api/purgatory_execute':
                fid_req = d.get('fid', '')
                rows = db_fetch("SELECT path, original_path FROM purgatory")
                found = False
                for r in rows:
                    p_dead, o_path = r[0], r[1]
                    if hashlib.md5(o_path.encode('utf-8')).hexdigest()[:16] == fid_req:
                        found = True
                        try:
                            os.remove(p_dead)
                            db_exec("DELETE FROM purgatory WHERE path=?", (p_dead,))
                            self.send_json({'ok': True})
                        except Exception as e:
                            self.send_json({'ok': False, 'err': str(e)})
                        break
                if not found:
                    self.send_json({'ok': False, 'err': 'Fichier non trouvé'})

            elif path == '/api/purgatory_force_restore':
                fid_req = d.get('fid', '')
                rows = db_fetch("SELECT path, original_path FROM purgatory")
                found = False
                for r in rows:
                    p_dead, o_path = r[0], r[1]
                    if hashlib.md5(o_path.encode('utf-8')).hexdigest()[:16] == fid_req:
                        found = True
                        try:
                            unlock_purgatory_file(p_dead)
                            os.makedirs(os.path.dirname(o_path), exist_ok=True)
                            shutil.move(p_dead, o_path)
                            db_exec("DELETE FROM purgatory WHERE path=?", (p_dead,))
                            indexer()
                            self.send_json({'ok': True})
                        except Exception as e:
                            self.send_json({'ok': False, 'err': str(e)})
                        break
                if not found:
                    self.send_json({'ok': False, 'err': 'Fichier non trouvé'})

            elif path == '/api/delete':
                # Dette de temps DÉSACTIVÉE : suppression simple (corbeille ou définitif).
                # Plus de calcul de pénalité, plus de purgatoire à délai variable.
                try:
                    if fp_db and os.path.exists(fp_db):
                        if d.get('hard') == True:
                            os.remove(fp_db)
                        else:
                            # Soft delete -> corbeille (réversible, voir /api/restore_from_trash)
                            dest = os.path.join(TRASH_DIR, f"{int(time.time()*1000)}____{os.path.basename(fp_db)}")
                            shutil.move(fp_db, dest)
                        with INDEX_LOCK:
                            if fp_db in config.MEDIA_FILES: config.MEDIA_FILES.remove(fp_db)
                            if fp_db in config.AUDIO_FILES: config.AUDIO_FILES.remove(fp_db)
                    self.send_json({'ok': True})
                except Exception as e: self.send_json({'ok': False, 'err': str(e)})

            elif path == '/api/alert_intrusion':
                # FIX: endpoint manquant (appelé par le client après 3 PIN erronés)
                stamp = datetime.datetime.now().isoformat()
                print(f"🚨 [INTRUSION] {stamp} — 3 codes PIN erronés.")
                try:
                    with open("intrusions.log", "a", encoding="utf-8") as lf:
                        lf.write(f"{stamp} intrusion detectee\n")
                except Exception: pass
                self.send_json({'ok': True})

            else:
                # FIX: toute requête POST non reconnue répond maintenant (avant: aucune réponse)
                self.send_json({'ok': False, 'err': 'Endpoint inconnu'}, code=404)

        except BrokenPipeError: pass
        except Exception: pass
