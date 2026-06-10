# ═══════════════════════════════════════════════════════════════════
# §1 — IMPORTS
# ═══════════════════════════════════════════════════════════════════
import http.server
import socketserver
import os
import random
import json
import urllib.parse
import mimetypes
import threading
import time
import shutil
import subprocess
import sys
import sqlite3
import re
import hashlib
import io
import datetime
import signal
import termios
import tty
import string

# ═══════════════════════════════════════════════════════════════════
# §2 — CONFIGURATION & CONSTANTES
# ═══════════════════════════════════════════════════════════════════

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) or "."
os.chdir(BASE_DIR)

if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
    MEDIA_DIR = os.path.abspath(sys.argv[1])
else:
    MEDIA_DIR = BASE_DIR

PORT          = 8000
DB_FILE       = "database.db"
TRASH_DIR     = ".sonic_trash"
CORRUPT_DIR   = "Corrupted_Media"
THUMB_DIR     = ".thumbnails"
PURGATORY_DIR = ".sonic_purgatory"
BACKUP_DIR    = ".sonic_originals"
INDEX_FILE    = "index.html"

SVAULT_EXT    = ".sv2"
EXT_LEN       = len(SVAULT_EXT)
XOR_KEY       = b"S0N1C_SH13LD_M4ST3R_K3Y_2026"
SCRAMBLE_SIZE = 1024
PURGATORY_KEY = hashlib.sha256(b"DEAD_ZONE_LOCK_2026_MAX_SECURITY").digest()

SESSION_KEY_ACTIVE  = True
DAILY_QUOTA         = 2700
NIGHT_QUOTA         = 1320
DB_LOCK_FILE        = DB_FILE + ".lock"
LOCKED_UNTIL        = 0.0
LOCKDOWN_TRIGGERED  = False
BURN_MODE_SERVER    = False

KILL_PHRASE     = "azertyuiop"
BG_BATCH_SIZE   = 5

IMG_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.bmp', '.tiff', '.tif')
VID_EXTS = ('.mp4', '.webm', '.mov', '.avi', '.mkv', '.m4v')
AUD_EXTS = ('.mp3', '.wav', '.ogg', '.flac', '.m4a')
ALL_EXTS = IMG_EXTS + VID_EXTS

MIME_MAP = {
    '.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime',
    '.mkv': 'video/x-matroska', '.avi': 'video/x-msvideo', '.m4v': 'video/mp4',
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.gif': 'image/gif', '.webp': 'image/webp', '.avif': 'image/avif',
    '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.flac': 'audio/flac', '.wav': 'audio/wav'
}

MEDIA_FILES     = []
AUDIO_FILES     = []
FILE_INDEX      = {}
FILE_INDEX_R    = {}
FILE_CTIME      = {}
FILE_SIZE       = {}

INDEX_LOCK      = threading.Lock()
DB_LOCK         = threading.Lock()
FILE_INDEX_LOCK = threading.Lock()

try:
    from PIL import Image, ImageEnhance
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

for _d in (TRASH_DIR, CORRUPT_DIR, THUMB_DIR, PURGATORY_DIR, BACKUP_DIR):
    os.makedirs(_d, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════
# §3 — FRONTEND HTML  (INDEX_HTML)
# ═══════════════════════════════════════════════════════════════════
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#000000">
<title>Gallery Pro</title>

<link rel="manifest" href="/manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Gallery Pro">
<link rel="apple-touch-icon" href="/icon-192.png">

<script src="https://cdn.jsdelivr.net/npm/@vladmandic/face-api/dist/face-api.js"></script>

<style>
:root { 
    --a: #ff00ff; 
    --bg: #030305; 
    --glass: rgba(15,15,20,0.85); 
    --border: rgba(255,255,255,0.08); 
    --safe-t: env(safe-area-inset-top,0px); 
    --safe-b: env(safe-area-inset-bottom,0px); 
    --fit: contain; 
}

[data-theme="neon"] { --a: #39ff14; } 
[data-theme="ice"] { --a: #00cfff; } 
[data-theme="red"] { --a: #ff3030; } 
[data-theme="gold"] { --a: #ffd700; } 
[data-theme="mono"] { --a: #ffffff; }

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body { 
    height: 100%; 
    overflow: hidden; 
    background: var(--bg); 
    color: #fff; 
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
    user-select: none; 
    -webkit-user-select: none; 
    -webkit-touch-callout: none; 
    overscroll-behavior: none; 
    touch-action: none; 
}

.pbox, .grid, select, input, textarea { touch-action: auto; }

/* AUTO-HIDE UI */
body.ui-hidden #hud-name, body.ui-hidden #stars, body.ui-hidden #nav-handle,
body.ui-hidden #quick-fx-btn, body.ui-hidden #quick-fx-hud, body.ui-hidden #time-tracker,
body.ui-hidden #stability-hud {
    opacity: 0 !important;
    pointer-events: none !important;
}
body.ui-hidden #hud-name, body.ui-hidden #time-tracker, body.ui-hidden #stability-hud { transform: translateY(-20px); }
body.ui-hidden #quick-fx-btn, body.ui-hidden #quick-fx-hud { transform: translateY(-20px); }
body.ui-hidden #stars, body.ui-hidden #nav-handle { transform: translate(-50%, 20px); }
body.ui-hidden * { cursor: none; }

#stage.ov-invert { filter: invert(1) hue-rotate(180deg); }

/* --- STABILITY HUD & WEAR FX --- */
#stability-hud { position: fixed; top: max(120px, calc(var(--safe-t) + 110px)); left: 14px; z-index: 1000; background: rgba(0,0,0,0.8); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 10px 14px; display: flex; flex-direction: column; gap: 8px; width: 180px; transition: opacity 0.4s ease, transform 0.4s cubic-bezier(0.1,0.9,0.2,1); pointer-events: none; box-shadow: 0 4px 20px rgba(0,0,0,0.8); }
.stab-lbl { font-size: 11px; font-weight: 900; color: rgba(255,255,255,0.8); letter-spacing: 2px; text-transform: uppercase; font-family: monospace; }
.stab-bar-bg { width: 100%; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; position: relative; box-shadow: inset 0 2px 5px rgba(0,0,0,1); }
.stab-bar-fill { height: 100%; width: 100%; background: #00ff80; transition: width 0.2s linear, background 0.2s linear; box-shadow: 0 0 15px rgba(0,255,128,0.8); }
.stab-val { position: absolute; right: 0; top: -18px; font-size: 12px; color: #fff; font-weight: 900; text-shadow: 0 1px 6px #000; font-family: monospace; }

@keyframes bitrot-shake {
    0% { transform: translate(0) scale(1); filter: hue-rotate(0deg); }
    20% { transform: translate(-3px, 2px) scale(1.02); filter: hue-rotate(90deg); }
    40% { transform: translate(-2px, -3px) scale(0.98); }
    60% { transform: translate(3px, 1px) scale(1.03); filter: invert(0.15); }
    80% { transform: translate(1px, -2px) scale(0.97); }
    100% { transform: translate(0) scale(1); filter: hue-rotate(0deg); }
}

@keyframes fatal-glitch {
    0% { transform: perspective(500px) translate(0) skew(0deg); filter: invert(0) blur(0); }
    10% { transform: perspective(500px) translate(-10px, 5px) skew(10deg) scale(1.05); filter: invert(1) hue-rotate(90deg) blur(2px); }
    20% { transform: perspective(500px) translate(10px, -5px) skew(-10deg) scale(0.95); filter: invert(0) brightness(2) contrast(3); }
    30% { transform: perspective(500px) translate(0) skew(0deg); filter: sepia(1) hue-rotate(-50deg); }
    100% { transform: perspective(500px) translate(0) skew(0deg); filter: invert(0); }
}

@keyframes screen-bleed {
    0%, 100% { box-shadow: inset 0 0 0 rgba(255,0,0,0); }
    50% { box-shadow: inset 0 0 80px rgba(255,0,0,0.8), inset 0 0 20px rgba(255,0,0,1); }
}

.screen-fatal { animation: screen-bleed 0.5s infinite ease-in-out; }
.wear-severe { animation: bitrot-shake 0.2s infinite; mix-blend-mode: hard-light; }
.wear-fatal { animation: fatal-glitch 0.15s infinite; mix-blend-mode: difference; }

/* BURN MODE */
body.burn-mode #stage { animation: none; filter: grayscale(1) contrast(1.6); }
body.burn-mode .slot img, body.burn-mode .slot video { filter: none !important; }

@keyframes strobeA { 0%,49%  { background:#fff; opacity:0.35; } 50%,100%{ background:#000; opacity:0; } }
@keyframes strobeB { 0%,49%  { background:#fff; opacity:0.30; } 50%,100%{ background:#000; opacity:0; } }
@keyframes strobeC { 0%,32%  { background:#fff; opacity:0.28; } 33%,65% { background:#000; opacity:0; } 66%,100%{ background:#fff; opacity:0.25; } }
@keyframes strobeD { 0%,24%  { background:#000; opacity:0.32; } 25%,49% { background:#000; opacity:0; } 50%,74% { background:#fff; opacity:0.30; } 75%,100%{ background:#000; opacity:0; } }
@keyframes burnPulse { 0% { opacity:1; text-shadow:0 0 8px #fff, 0 0 20px #aaa; } 50% { opacity:0.5; text-shadow:0 0 20px #fff, 0 0 40px #fff; } 100% { opacity:1; text-shadow:0 0 8px #fff, 0 0 25px #aaa; } }

.burn-strobe-layer { display: none; position: fixed; inset: 0; pointer-events: none; }
body.burn-mode .burn-strobe-layer { display: block; }

#burn-strobe-a { z-index: 440; mix-blend-mode: difference; animation: strobeA 0.016s steps(1) infinite; }
#burn-strobe-b { z-index: 450; mix-blend-mode: exclusion; animation: strobeB 0.020s steps(1) infinite; }
#burn-strobe-c { z-index: 460; mix-blend-mode: overlay; animation: strobeC 0.014s steps(1) infinite; }
#burn-strobe-d { z-index: 470; mix-blend-mode: hard-light; animation: strobeD 0.018s steps(1) infinite; }
#burn-strobe-js { display: none; position: fixed; inset: 0; z-index: 480; pointer-events: none; mix-blend-mode: hard-light; opacity: 0; }
body.burn-mode #burn-strobe-js { display: block; }

#mode-overlay, #login, #antidote-overlay { position: fixed; inset: 0; background: #050508; z-index: 9999999; display: none; flex-direction: column; align-items: center; justify-content: center; gap: 20px; touch-action: auto; }
#login { z-index: 999999; display: flex; }

#pin-display { font-size: 32px; letter-spacing: 18px; color: var(--a); height: 42px; text-align: center; font-weight: 300; text-shadow: 0 0 15px rgba(255,0,255,0.4); }
#keypad { display: grid; grid-template-columns: repeat(3, 72px); gap: 14px; margin-top: 5px; }

.k { width: 72px; height: 72px; border-radius: 50%; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06); color: #fff; font-size: 24px; font-weight: 400; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.15s, transform 0.1s; -webkit-tap-highlight-color: transparent; }
.k:active { background: rgba(255,255,255,0.15); transform: scale(0.9); border-color: var(--a); }

#lock-overlay { position: fixed; inset: 0; z-index: 90000; background: transparent; display: none; touch-action: none; } 
#lock-overlay.on { display: block; }

#prog { position: fixed; top: 0; left: 0; height: 3px; width: 0; background: var(--a); z-index: 2000; pointer-events: none; box-shadow: 0 1px 8px var(--a); transition: width linear; }

#stage { position: fixed; inset: 0; background: var(--bg); touch-action: none; transform-origin: center; transition: transform 0.1s ease-out, opacity 0.3s; }
.slot { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.28s ease; background: var(--bg); z-index: 1; }
.slot.on { opacity: 1; z-index: 10; }
.slot img, .slot video { width: 100%; height: 100%; object-fit: var(--fit); display: block; pointer-events: none; transition: filter 0.15s ease-out; will-change: transform, filter, opacity; transform-origin: center; }

.mask-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: var(--fit); pointer-events: none; z-index: 5; }
.smear-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: var(--fit); pointer-events: none; z-index: 2; }
.fx-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: var(--fit); pointer-events: none; z-index: 3; }
.stealth-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: var(--fit); pointer-events: none; z-index: 6; }

#antidote-board-wrap { position: fixed; inset: 0; z-index: 99999999; display: none; align-items: center; justify-content: center; background: rgba(20,0,0,0.98); flex-direction: column; padding: max(30px, var(--safe-t)) 10px max(30px, var(--safe-b)); }
#antidote-board { display: grid; gap: 0; margin: auto; max-width: 100vw; max-height: calc(100vh - 120px); }
.puzzle-piece { position: relative; overflow: hidden; cursor: pointer; box-sizing: border-box; }
.puzzle-piece.selected { outline: 3px solid #fff; outline-offset: -3px; z-index: 10; filter: brightness(1.2); }
.puzzle-content { position: absolute; top: 0; left: 0; object-fit: cover; pointer-events: none; }

#antidote-timer { color: #ff3030; font-size: 36px; font-weight: 800; text-shadow: 0 0 15px red; margin-bottom: 20px; }

@keyframes breathe { 0%,100%{filter: brightness(1) contrast(1)} 50%{filter: brightness(0.92) contrast(1.08)} } 
.breathing { animation: breathe 1s infinite ease-in-out; }

.t-r { animation: tr .3s ease forwards; } .t-l { animation: tl .3s ease forwards; } 
.t-z { animation: tz .3s ease forwards; } .t-b { animation: tb .3s ease forwards; } 
.t-f { animation: tf .3s ease forwards; } .t-g { animation: tg .3s steps(3) forwards; }

@keyframes tr { from { transform: translateX(5%); opacity: 0 } to { transform: none; opacity: 1 } } 
@keyframes tl { from { transform: translateX(-5%); opacity: 0 } to { transform: none; opacity: 1 } } 
@keyframes tz { from { transform: scale(1.07); opacity: 0 } to { transform: none; opacity: 1 } } 
@keyframes tb { from { filter: blur(14px); opacity: 0 } to { filter: none; opacity: 1 } } 
@keyframes tf { from { transform: perspective(600px) rotateY(55deg); opacity: 0 } to { transform: none; opacity: 1 } } 
@keyframes tg { 0% { clip-path: inset(0 0 100% 0) } 50% { clip-path: inset(30% 0 30% 0) } 100% { clip-path: inset(0); opacity: 1 } }

body.immersive #hud-name, body.immersive #time-tracker, body.immersive #stars, body.immersive #nav-handle, body.immersive #nav-bar,
body.immersive #quick-fx-btn, body.immersive #quick-fx-hud, body.immersive #stability-hud { opacity: 0!important; pointer-events: none!important; transform: translateY(20px); }
#hud-name, #time-tracker, #stars, #nav-handle, #nav-bar, #quick-fx-btn, #quick-fx-hud { transition: opacity 0.4s ease, transform 0.4s cubic-bezier(0.1,0.9,0.2,1); }

#hud-name { position: fixed; top: max(14px, var(--safe-t)); left: 14px; z-index: 1000; font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.9); background: rgba(0,0,0,0.4); backdrop-filter: blur(15px); border-radius: 20px; padding: 8px 16px; max-width: 65vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; box-shadow: 0 4px 15px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.08); -webkit-tap-highlight-color: transparent; } 
#hud-name:active { color: var(--a); border-color: var(--a); }

#time-tracker { position: fixed; top: max(55px, calc(var(--safe-t) + 45px)); left: 14px; z-index: 1000; font-size: 10px; font-weight: 800; color: rgba(255,255,255,0.6); background: rgba(0,0,0,0.3); backdrop-filter: blur(5px); border-radius: 10px; padding: 4px 10px; border: 1px solid rgba(255,255,255,0.05); letter-spacing: 1px; }
#purg-cost { position: fixed; top: max(88px, calc(var(--safe-t) + 78px)); left: 14px; z-index: 1000; font-size: 10px; font-weight: 800; color: #ff5050; background: rgba(30,0,0,0.65); backdrop-filter: blur(10px); border-radius: 10px; padding: 4px 12px; border: 1px solid rgba(255,48,48,0.4); letter-spacing: 0.5px; display: none; pointer-events: none; transition: opacity 0.4s ease, transform 0.4s cubic-bezier(0.1,0.9,0.2,1); }
body.immersive #purg-cost { opacity: 0!important; pointer-events: none!important; transform: translateY(20px); }

#quick-fx-btn { position: fixed; top: max(14px, var(--safe-t)); right: 14px; z-index: 1001; font-size: 13px; font-weight: 800; color: #fff; background: rgba(0,0,0,0.5); backdrop-filter: blur(15px); border-radius: 20px; padding: 8px 16px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.1); cursor: pointer; -webkit-tap-highlight-color: transparent; }
#quick-fx-btn.active { color: var(--a); border-color: var(--a); }

#quick-fx-hud { position: fixed; top: max(55px, calc(var(--safe-t) + 45px)); right: 14px; width: 240px; background: var(--glass); backdrop-filter: blur(25px); border: 1px solid var(--border); border-radius: 18px; padding: 14px; z-index: 1000; display: none; flex-direction: column; gap: 14px; box-shadow: 0 10px 40px rgba(0,0,0,0.6); touch-action: auto; transform-origin: top right; }
#quick-fx-hud.on { display: flex; animation: slideDown 0.2s cubic-bezier(0.1,0.9,0.2,1); }
@keyframes slideDown { from { opacity:0; transform: scale(0.95) translateY(-10px); } to { opacity:1; transform: scale(1) translateY(0); } }

.fx-sec { display: flex; flex-direction: column; gap: 8px; }
.fx-lbl { font-size: 11px; font-weight: 800; color: var(--a); letter-spacing: 1px; text-transform:uppercase; }
.fx-row { display: flex; align-items: center; gap: 8px; justify-content: space-between; }
.fx-row select { flex: 1; padding: 8px 10px; height: 32px; font-size: 12px; }
.fx-row input[type=range] { flex: 1; margin: 0; }
.fx-row input[type=number] { background: rgba(255,255,255,0.08); border: 1px solid var(--border); border-radius: 8px; color: #fff; padding: 6px; font-size: 13px; outline: none; }
.fx-btn { flex: 1; background: rgba(255,255,255,0.1); border: none; color: #fff; font-size: 12px; font-weight: bold; padding: 8px; border-radius: 8px; cursor: pointer; transition: 0.2s; }
.fx-btn:active { transform: scale(0.95); background: rgba(255,255,255,0.2); }
.fx-btn.active { background: var(--a); color: #000; }

#stars { position: fixed; bottom: max(85px, calc(var(--safe-b) + 80px)); left: 50%; transform: translateX(-50%); display: none; gap: 12px; z-index: 1000; background: rgba(0,0,0,0.4); padding: 8px 20px; border-radius: 30px; backdrop-filter: blur(15px); border: 1px solid rgba(255,255,255,0.08); } 
#stars.on { display: flex; } 
.star { font-size: 24px; cursor: pointer; opacity: 0.3; transition: opacity 0.15s, transform 0.1s; text-shadow: 0 2px 8px rgba(0,0,0,0.5); -webkit-tap-highlight-color: transparent; } 
.star.on { opacity: 1; color: var(--a); } 
.star:active { transform: scale(1.4); }

#nav-handle { position: fixed; bottom: max(16px, var(--safe-b)); left: 50%; transform: translateX(-50%); z-index: 1001; width: 60px; height: 5px; border-radius: 3px; background: rgba(255,255,255,0.3); cursor: pointer; transition: background 0.2s, transform 0.4s; box-shadow: 0 2px 10px rgba(0,0,0,0.5); -webkit-tap-highlight-color: transparent; } 
#nav-handle:active, #nav-handle.active { background: var(--a); }

#nav-bar { position: fixed; bottom: 0; left: 0; right: 0; z-index: 1000; background: var(--glass); backdrop-filter: blur(40px); -webkit-backdrop-filter: blur(40px); border-top: 1px solid var(--border); padding: 25px 14px calc(25px + var(--safe-b)); transform: translateY(100%); display: flex; flex-direction: column; gap: 12px; touch-action: auto; border-radius: 25px 25px 0 0; } 
#nav-bar.open { transform: translateY(0); }

.nav-grid { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; } 
.nb { background: rgba(255,255,255,0.06); border: 1px solid var(--border); color: rgba(255,255,255,0.9); font-size: 13px; font-weight: 600; padding: 14px 20px; border-radius: 20px; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); -webkit-tap-highlight-color: transparent; } 
.nb:active { transform: scale(0.94); background: rgba(255,255,255,0.12); } 
.nb.on { background: var(--a); color: #000; border-color: transparent; box-shadow: 0 6px 20px rgba(255,0,255,0.4); } 
.nb.on.ss { background: #00cfff; box-shadow: 0 6px 20px rgba(0,207,255,0.4); } 
.nb.on.lk { background: #ff9100; box-shadow: 0 6px 20px rgba(255,145,0,0.4); } 
.nb.on.mu { background: #1db954; box-shadow: 0 6px 20px rgba(29,185,84,0.4); } 

/* FIX: #burn-badge n'avait aucun style (restait visible en flux normal) */
#burn-badge { position: fixed; top: max(14px, var(--safe-t)); left: 50%; transform: translateX(-50%); z-index: 500; background: rgba(255,48,48,0.85); color:#fff; font-size:12px; font-weight:800; letter-spacing:1px; padding:8px 16px; border-radius:20px; cursor:pointer; display:none; -webkit-tap-highlight-color:transparent; box-shadow:0 4px 15px rgba(255,0,0,0.4); }
body.burn-mode #burn-badge { display:block; }

/* Badge mode (galerie) + diaporama */
#mode-badge { position: fixed; top: max(14px, var(--safe-t)); left: 14px; z-index: 480; background: rgba(76,175,80,0.85); color:#fff; font-size:11px; font-weight:800; letter-spacing:1px; padding:7px 13px; border-radius:18px; cursor:pointer; display:none; -webkit-tap-highlight-color:transparent; box-shadow:0 4px 12px rgba(76,175,80,0.35); }
#slideshow-badge { position: fixed; top: max(14px, var(--safe-t)); right: 14px; z-index: 480; background: rgba(0,0,0,0.55); color:#fff; font-size:11px; font-weight:800; letter-spacing:1px; padding:7px 13px; border-radius:18px; cursor:pointer; display:none; -webkit-tap-highlight-color:transparent; border:1px solid rgba(255,255,255,0.2); }
body.gallery-mode #slideshow-badge { display:block; }
body.slideshow-on #slideshow-badge { background: rgba(76,175,80,0.85); border-color:transparent; }

#session-counter { position: fixed; bottom: max(14px, var(--safe-b)); left: 14px; z-index: 470; background: rgba(0,0,0,0.5); color: rgba(255,255,255,0.85); font-size: 12px; font-weight: 700; padding: 6px 12px; border-radius: 16px; pointer-events: none; font-variant-numeric: tabular-nums; }
#info-overlay { position: fixed; inset: 0; z-index: 600; background: rgba(0,0,0,0.82); color: #fff; display: none; flex-direction: column; align-items: center; justify-content: center; gap: 6px; font-size: 15px; line-height: 1.9; text-align: center; padding: 40px; cursor: pointer; -webkit-tap-highlight-color: transparent; }
#info-overlay b { color: var(--a); font-size: 17px; word-break: break-all; }

#ssbadge { position: fixed; top: max(14px, var(--safe-t)); left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.6); backdrop-filter: blur(15px); border: 1px solid var(--border); border-radius: 16px; padding: 6px 14px; font-size: 11px; font-weight: 700; color: rgba(255,255,255,0.8); z-index: 1001; opacity: 0; pointer-events: none; transition: opacity 0.2s; letter-spacing: 1px; box-shadow: 0 4px 10px rgba(0,0,0,0.2); } 
#ssbadge.on { opacity: 1; }

#toast { position: fixed; top: max(65px, calc(var(--safe-t)+55px)); left: 50%; transform: translateX(-50%); background: rgba(15,15,20,0.92); backdrop-filter: blur(20px); border: 1px solid var(--border); border-radius: 24px; padding: 12px 24px; font-size: 13px; font-weight: 600; color: #fff; z-index: 800000; opacity: 0; pointer-events: none; transition: opacity 0.2s, transform 0.2s; white-space: nowrap; box-shadow: 0 8px 30px rgba(0,0,0,0.5); } 
#toast.on { opacity: 1; transform: translate(-50%, 5px); }

.panel { position: fixed; inset: 0; z-index: 5000; display: flex; align-items: flex-end; justify-content: center; background: rgba(0,0,0,0.8); backdrop-filter: blur(5px); opacity: 0; pointer-events: none; transition: opacity 0.3s ease; touch-action: auto; } 
.panel.on { opacity: 1; pointer-events: auto; }

.pbox { background: var(--glass); backdrop-filter: blur(40px); border-top: 1px solid var(--border); border-radius: 30px 30px 0 0; width: 100%; max-width: 540px; max-height: 85vh; overflow-y: auto; padding: 30px 24px calc(24px + var(--safe-b)); position: relative; animation: pup 0.4s cubic-bezier(0.1,0.9,0.2,1); scrollbar-width: none; box-shadow: 0 -10px 50px rgba(0,0,0,0.5); } 
.pbox::before { content: ''; position: absolute; top: 12px; left: 50%; transform: translateX(-50%); width: 45px; height: 5px; border-radius: 3px; background: rgba(255,255,255,0.2); } 
.pbox::-webkit-scrollbar { display: none; } 
@keyframes pup { from { transform: translateY(100%) } to { transform: none } }

.ptitle { font-size: 16px; font-weight: 800; color: var(--a); text-align: center; margin-bottom: 25px; letter-spacing: 1.5px; text-transform: uppercase; } 
.px { position: absolute; top: 18px; right: 20px; background: rgba(255,255,255,0.08); border: none; color: rgba(255,255,255,0.8); width: 34px; height: 34px; border-radius: 17px; font-size: 14px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.2s; -webkit-tap-highlight-color: transparent; } 
.px:active { background: rgba(255,255,255,0.2); color: #fff; }

.row { display: flex; justify-content: space-between; align-items: center; padding: 14px 0; border-bottom: 1px solid rgba(255,255,255,0.04); } 
.row:last-child { border: none; } 
.rl { font-size: 14px; font-weight: 500; color: rgba(255,255,255,0.9); }

.tog { width: 50px; height: 28px; border-radius: 14px; background: rgba(255,255,255,0.15); border: none; cursor: pointer; position: relative; transition: background 0.25s; flex-shrink: 0; -webkit-tap-highlight-color: transparent; } 
.tog::after { content: ''; position: absolute; top: 2px; left: 2px; width: 24px; height: 24px; border-radius: 50%; background: #fff; transition: transform 0.25s cubic-bezier(0.4,0,0.2,1); box-shadow: 0 2px 5px rgba(0,0,0,0.3); } 
.tog.on { background: var(--a); } 
.tog.on::after { transform: translateX(22px); }

.rr { display: flex; align-items: center; gap: 10px; width: 150px; } 
input[type=range] { flex: 1; -webkit-appearance: none; height: 5px; border-radius: 3px; background: rgba(255,255,255,0.15); outline: none; } 
input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; width: 22px; height: 22px; border-radius: 50%; background: var(--a); cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.4); } 
.rv { font-size: 12px; font-weight: bold; color: var(--a); width: 35px; text-align: right; flex-shrink: 0; }

select, input[type=color] { background: rgba(255,255,255,0.08); border: 1px solid var(--border); border-radius: 12px; color: #fff; padding: 10px 14px; font-size: 13px; font-weight: 500; cursor: pointer; outline: none; width: 150px; text-overflow: ellipsis; appearance: none; -webkit-appearance: none; } 
select option { background: #111; } 
input[type=color] { height: 38px; padding: 2px 5px; }

.abn { background: var(--a); border: none; color: #000; font-size: 14px; font-weight: 800; border-radius: 14px; padding: 12px 20px; cursor: pointer; transition: opacity 0.2s, transform 0.1s; box-shadow: 0 4px 15px rgba(255,0,255,0.3); -webkit-tap-highlight-color: transparent; } 
.abn:active { opacity: .8; transform: scale(0.97); }

.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; padding: 6px; } 
.gt { position: relative; width: 100%; padding-bottom: 100%; border-radius: 8px; background: #1a1a1a; overflow: hidden; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.5); -webkit-tap-highlight-color: transparent; } 
.gt img, .gt video { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; display: block; }

.gt-ov { position: absolute; inset: 0; background: rgba(255,0,255,0.2); opacity: 0; transition: opacity 0.15s; } 
.gt:active .gt-ov { opacity: 1; } 
.gt-fav { position: absolute; top: 6px; right: 6px; font-size: 12px; text-shadow: 0 1px 4px rgba(0,0,0,0.9); } 
.gt-vid { position: absolute; bottom: 6px; left: 6px; font-size: 12px; text-shadow: 0 1px 4px rgba(0,0,0,0.9); } 
.gt-rat { position: absolute; bottom: 6px; right: 6px; font-size: 10px; color: #ffd700; text-shadow: 0 1px 4px rgba(0,0,0,0.9); }

.chip { display: inline-block; background: rgba(255,0,255,0.15); border: 1px solid rgba(255,0,255,0.3); border-radius: 20px; padding: 8px 14px; font-size: 12px; font-weight: 600; color: var(--a); cursor: pointer; margin: 4px; transition: background 0.2s; -webkit-tap-highlight-color: transparent; } 
.chip:active { background: rgba(255,0,255,0.4); } 

.tag-row { display: flex; gap: 8px; margin: 10px 0 8px; } 
.tin { flex: 1; background: rgba(255,255,255,0.06); border: 1px solid var(--border); border-radius: 14px; padding: 12px 16px; color: #fff; font-size: 14px; outline: none; transition: border-color 0.2s; } 
.tin:focus { border-color: var(--a); } 

textarea { width: 100%; min-height: 100px; background: rgba(255,255,255,0.06); border: 1px solid var(--border); border-radius: 14px; color: #fff; font-size: 14px; padding: 14px; resize: vertical; outline: none; font-family: inherit; transition: border-color 0.2s; } 
textarea:focus { border-color: var(--a); }

.sg { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 15px; } 
.sc { background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 16px; padding: 16px 8px; text-align: center; } 
.sn { font-size: 26px; font-weight: 800; color: var(--a); } 
.sl { font-size: 11px; font-weight: 600; color: rgba(255,255,255,0.6); margin-top: 6px; text-transform: uppercase; letter-spacing: 0.5px; } 
.slbl { font-size: 12px; font-weight: 800; color: var(--a); letter-spacing: 1.5px; margin-bottom: 10px; margin-top: 25px; text-transform: uppercase; opacity: 0.9; } 
.slbl:first-child { margin-top: 0; }

.pal-grid { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 15px; margin-bottom: 15px; justify-content: center; } 
.pal-c { width: 36px; height: 36px; border-radius: 50%; cursor: pointer; border: 2px solid transparent; transition: transform 0.2s; box-shadow: 0 4px 12px rgba(0,0,0,0.5); } 
.pal-c:active { transform: scale(0.8); }
</style>
</head>
<body class="breathing">
<audio id="bg-audio" preload="auto"></audio>

<div id="time-tracker">Temps total: 0h 0m</div>
<div id="purg-cost"></div>

<div id="stability-hud">
    <div style="position:relative;">
        <div class="stab-lbl" id="stab-lbl-text">STABILITÉ CORE</div>
        <div class="stab-val" id="stab-val-text">100%</div>
    </div>
    <div class="stab-bar-bg"><div class="stab-bar-fill" id="stab-fill"></div></div>
</div>

<div id="quick-fx-btn" onclick="toggleQuickFX()">🪄 FX</div>
<div id="quick-fx-hud">
    <div class="fx-sec">
        <div class="fx-lbl">MASQUE (CENSURE)</div>
        <div class="fx-row">
            <select style="width:100%;" onchange="C.maskStyle=this.value; applyMaskConfig();">
                <option value="pixel">Pixels</option>
                <option value="invert_light">Lumière Inversée</option>
                <option value="eye_bar">Eye-Bar (Auto Face)</option>
                <option value="slenderman">Slenderman (Effacement)</option>
                <option value="crypto">Bruit Crypto</option>
                <option value="leurre">Leurre (PiP)</option>
                <option value="freeze">Gel Temporel</option>
                <option value="desync">Désync (-1s)</option>
                <option value="motion_blur">Flou Mouvement</option>
            </select>
        </div>
        <div class="fx-row">
            <button id="btn-draw-mask" class="fx-btn" onclick="toggleDrawMask()">✏️ Tracer</button>
            <button class="fx-btn" style="background:rgba(255,48,48,0.2);color:#ff3030;" onclick="clearMasks()">🗑️ Effacer</button>
        </div>
    </div>
    <div style="height:1px; background:var(--border); margin:4px 0;"></div>
    
    <div class="fx-sec">
        <div class="fx-lbl">DISTORSIONS (EFFETS VISUELS)</div>
        <div class="fx-row">
            <select style="width:100%;" onchange="C.fxStyle=this.value; resetFX();">
                <option value="none">Aucun</option>
                <option value="mosh">Datamoshing</option>
                <option value="motion">Motion Mosh</option>
                <option value="radial">Écho Radial</option>
                <option value="entropy">Entropie (Inversion)</option>
                <option value="stegano">Stéganographie (Bruit)</option>
                <option value="databend">Databending (Glitch RGB)</option>
                <option value="deadpixels">Pixels Morts</option>
                <option value="crypto">Bruit Crypto</option>
                <option value="motionblur">Flou de Mouvement</option>
            </select>
        </div>
        <div class="fx-row">
            <span style="font-size:16px;">⚡</span>
            <input type="range" min="0" max="100" value="0" oninput="C.fxIntensity=+this.value; resetFX();" style="flex:1;">
        </div>
    </div>

    <div style="height:1px; background:var(--border); margin:4px 0;"></div>
    <div class="fx-sec">
        <div class="fx-lbl">ÉCRAN FURTIF</div>
        <div class="fx-row">
            <select style="width:100%;" onchange="C.stealthMode=this.value; applyStealthCanvas();">
                <option value="none">Désactivé</option>
                <option value="polar">Polarisant (Auto-close)</option>
                <option value="scratch">Grattage (Scratch-off)</option>
                <option value="fog">Brouillard (Fog)</option>
            </select>
        </div>
        <div class="fx-row">
            <span style="font-size:16px;">🧹</span>
            <input type="range" min="10" max="150" value="60" oninput="C.stealthIntensity=+this.value;">
        </div>
    </div>
</div>

<div id="unlock-pad" style="display:none; position:fixed; inset:0; z-index:90001; background:rgba(0,0,0,0.95); flex-direction:column; align-items:center; justify-content:center; touch-action:auto;">
    <div style="color:var(--a); margin-bottom:20px; font-weight:800; letter-spacing:2px; font-size:18px;" id="unlock-title">DÉVERROUILLAGE</div>
    <div style="font-size:11px; color:rgba(255,255,255,0.4); margin: 15px 0 5px;">Entrez votre code PIN :</div>
    
    <div id="upin-disp" style="font-size:32px; letter-spacing:18px; color:#fff; height:42px; margin-bottom:20px; text-shadow:0 0 10px var(--a);">••••</div>
    <div id="unlock-keys" style="display:grid; grid-template-columns:repeat(3, 72px); gap:14px;"></div>
    <button onclick="hideUnlockPad()" style="margin-top:30px; background:none; border:none; color:rgba(255,255,255,0.5); font-size:16px; cursor:pointer;">Annuler</button>
</div>

<div id="antidote-overlay">
    <div id="antidote-timer">15.0</div>
    <div id="antidote-board-wrap" style="display:flex;">
        <div id="antidote-board"></div>
    </div>
</div>

<div id="mode-overlay">
  <h1 style="color:var(--a); letter-spacing:2px; text-align:center; margin-bottom:25px;">SÉLECTION DU MODE</h1>
  <div style="display:flex; flex-direction:column; gap:15px; width:85%; max-width:400px; max-height:80vh; overflow-y:auto;">
    <button onclick="selectMode('gallery')" style="background:rgba(76,175,80,0.15); border:1px solid #4caf50; color:#4caf50; padding:18px; border-radius:16px; font-size:16px; font-weight:bold; cursor:pointer;">🖼️ Galerie Simple</button>
    <div style="color:rgba(255,255,255,0.35); font-size:12px; text-align:center; margin:-8px 0 4px; line-height:1.5;">Médias aléatoires · aucune dégradation · aucune infection</div>
    <button onclick="selectMode('zen')" style="background:rgba(0,207,255,0.15); border:1px solid #00cfff; color:#00cfff; padding:18px; border-radius:16px; font-size:16px; font-weight:bold; cursor:pointer;">🕊️ Mode Zen</button>
    <button onclick="selectMode('infected')" style="background:rgba(156,39,176,0.15); border:1px solid #9c27b0; color:#9c27b0; padding:18px; border-radius:16px; font-size:16px; font-weight:bold; cursor:pointer;">☢️ Mode Infection</button>
  </div>
</div>

<div id="lock-overlay"></div>

<div id="lockdown-screen" style="display:none; position:fixed; inset:0; z-index:99999999; background:#000; flex-direction:column; align-items:center; justify-content:center; gap:20px; touch-action:auto;">
    <div style="font-size:70px;">🔒</div>
    <div style="color:#ff3030; font-size:22px; font-weight:900; letter-spacing:4px; text-align:center; text-shadow:0 0 20px rgba(255,48,48,0.6);">GALERIE VERROUILLÉE</div>
    <div style="color:rgba(255,255,255,0.5); font-size:14px; text-align:center; line-height:2.2;">Quota quotidien atteint.<br>Retour automatique à minuit.</div>
    <div id="lockdown-countdown" style="color:#ff5050; font-size:36px; font-weight:900; letter-spacing:4px; margin-top:10px; text-shadow:0 0 20px rgba(255,48,48,0.5); font-variant-numeric:tabular-nums;">--:--:--</div>
    <button onclick="enterBurnMode()" style="margin-top:18px; background:rgba(255,48,48,0.12); border:1px solid rgba(255,48,48,0.5); color:#ff5050; font-size:15px; font-weight:800; letter-spacing:2px; padding:14px 32px; border-radius:14px; cursor:pointer; -webkit-tap-highlight-color:transparent;">👁 VOIR QUAND MÊME</button>
    <div style="color:rgba(255,255,255,0.15); font-size:11px; letter-spacing:2px; margin-top:20px;">SONIC SHIELD — SYSTÈME INVIOLABLE</div>
</div>

<div id="burn-badge" onclick="exitBurnMode()">🔥 BURN MODE — QUITTER</div>
<div id="mode-badge" onclick="toggleSlideshow()" title="Mode actif (cliquer pour diaporama)">🖼️ GALERIE</div>
<div id="slideshow-badge" onclick="toggleSlideshow()">▶️ DIAPORAMA</div>
<div id="session-counter" title="Médias vus dans cette session">👁 0</div>
<div id="info-overlay" onclick="this.style.display='none'"></div>
<div id="burn-strobe-a" class="burn-strobe-layer"></div>
<div id="burn-strobe-b" class="burn-strobe-layer"></div>
<div id="burn-strobe-c" class="burn-strobe-layer"></div>
<div id="burn-strobe-d" class="burn-strobe-layer"></div>
<div id="burn-strobe-js"></div>

<div id="login"> 
    <div style="font-size:12px;font-weight:600;letter-spacing:6px;color:rgba(255,255,255,0.4);margin-bottom:10px">SONIC SHIELD</div> 
    <div style="font-size:11px; color:rgba(255,255,255,0.4); margin: 5px 0;">Entrez votre code PIN</div>
    <div id="pin-display">••••</div> 
    <div id="pin-err" style="font-size:12px; color:#ff3030; height:18px; text-align:center;">&nbsp;</div> 
    <div id="keypad"></div> 
</div>

<div id="prog"></div> 
<div id="ssbadge">▶ SLIDESHOW</div>
<div id="hud-name" onclick="openPanel('info')">CHARGEMENT...</div>

<div id="stars"> 
    <span class="star" data-v="1" onclick="rate(1)">★</span> 
    <span class="star" data-v="2" onclick="rate(2)">★</span> 
    <span class="star" data-v="3" onclick="rate(3)">★</span> 
    <span class="star" data-v="4" onclick="rate(4)">★</span> 
    <span class="star" data-v="5" onclick="rate(5)">★</span> 
</div>

<div id="stage"> 
    <div class="slot" id="sa"></div> 
    <div class="slot" id="sb"></div> 
</div>

<div id="toast"></div>
<div id="empty-gallery-msg" style="display:none; position:fixed; inset:0; z-index:900000; background:var(--bg); flex-direction:column; align-items:center; justify-content:center; color:var(--a);">
    <h1 style="letter-spacing:4px; margin-bottom:10px;">GALERIE VIDE</h1>
    <p style="color:rgba(255,255,255,0.5);">Plus aucun média disponible.</p>
</div>

<div id="nav-handle" onclick="toggleNav()"></div>
<div id="nav-bar">
  <div class="nav-grid">
    <button class="nb" onclick="openPanel('filter')"><span>🔍</span> Galerie</button>
    <button class="nb mu" id="nb-music" onclick="toggleBgMusic()"><span>🎵</span> Musique</button>
    <button class="nb" id="nb-grid" onclick="openGridFromNav()"><span>⊞</span> Explorateur</button>
    <button class="nb ss" id="nb-ss" onclick="toggleSS()"><span>▶</span> Slideshow</button>
    <button class="nb lk" id="nb-ss-lock" onclick="toggleLockSS()"><span>🔒</span> Kiosque</button>
    <button class="nb" onclick="openPanel('cfg')"><span>⚙️</span> Système</button>
    <button class="nb" onclick="toggleFS()"><span>⛶</span> Plein Écran</button>
    <button class="nb" onclick="logout()"><span>🚪</span> Verrouiller</button>
  </div>
</div>

<div class="panel" id="panel-filter"> 
    <div class="pbox"> 
        <button class="px" onclick="closePanel('panel-filter')">✕</button> 
        <div class="ptitle">Galerie & Filtres</div> 
        <div class="slbl">TYPE DE MÉDIAS</div> 
        <div class="row"> 
            <div class="rl">Afficher</div> 
            <select id="sel-cat" onchange="changeCat(this.value)"> 
                <option value="all">Tout</option> 
                <option value="narcisse">👁️ Narcisse (Visages)</option> 
                <option value="video">🎬 Vidéos</option> 
                <option value="image">🖼 Images</option> 
                <option value="fav">❤️ Favoris</option> 
                <option value="hist">🕐 Récent</option> 
            </select> 
        </div> 
        
        <div class="row"> 
            <div class="rl">Démographie (Face API)</div> 
            <select onchange="C.demoFilter=this.value; refillAndNext();"> 
                <option value="all">Tous / Non Détecté</option> 
                <option value="male">Hommes</option> 
                <option value="female">Femmes</option> 
            </select> 
        </div>

        <div class="slbl">FILTRE PAR COULEUR</div> 
        <div class="row" style="margin-bottom:10px;"> 
            <div class="rl">Couleur active : <span id="color-filter-label" style="font-weight:bold;color:var(--a)">Aucune</span></div> 
            <button class="abn" style="padding:8px 14px;font-size:12px;" onclick="clearColorFilter()">Effacer</button> 
        </div> 
        <div class="row"> 
            <div class="rl">Sélectionner</div> 
            <input type="color" id="color-picker" value="#ff0000" onchange="searchByPicker(this.value)"> 
        </div> 
        <div class="pal-grid"> 
            <div class="pal-c" style="background:#FF0000" onclick="searchByColor('255,0,0', 'Rouge')"></div> 
            <div class="pal-c" style="background:#FFA500" onclick="searchByColor('255,165,0', 'Orange')"></div> 
            <div class="pal-c" style="background:#FFFF00" onclick="searchByColor('255,255,0', 'Jaune')"></div> 
            <div class="pal-c" style="background:#008000" onclick="searchByColor('0,128,0', 'Vert')"></div> 
            <div class="pal-c" style="background:#00FFFF" onclick="searchByColor('0,255,255', 'Cyan')"></div> 
            <div class="pal-c" style="background:#0000FF" onclick="searchByColor('0,0,255', 'Bleu')"></div> 
            <div class="pal-c" style="background:#800080" onclick="searchByColor('128,0,128', 'Violet')"></div> 
            <div class="pal-c" style="background:#FFC0CB" onclick="searchByColor('255,192,203', 'Rose')"></div> 
            <div class="pal-c" style="background:#A52A2A" onclick="searchByColor('165,42,42', 'Marron')"></div> 
            <div class="pal-c" style="background:#FFFFFF; border:1px solid #555" onclick="searchByColor('255,255,255', 'Blanc')"></div> 
            <div class="pal-c" style="background:#808080" onclick="searchByColor('128,128,128', 'Gris')"></div> 
            <div class="pal-c" style="background:#000000; border:1px solid #555" onclick="searchByColor('0,0,0', 'Noir')"></div> 
        </div>
        <div class="slbl">ORGANISATION</div> 
        <div class="row"> 
            <div class="rl">Trier par</div> 
            <select id="sel-sort" onchange="C.sort=this.value; refillAndNext();"> 
                <option value="unseen">Moins vus</option> 
                <option value="viewed">Populaires</option> 
                <option value="random">Aléatoire</option> 
                <option value="date">Création (Plus récents)</option> 
                <option value="date_asc">Création (Plus anciens)</option> 
                <option value="size">Taille (Plus lourds)</option> 
                <option value="size_asc">Taille (Plus légers)</option> 
                <option value="name">Nom (A-Z)</option> 
                <option value="namedesc">Nom (Z-A)</option> 
                <option value="rate">Note (Meilleure)</option> 
            </select> 
        </div> 
        <div class="row"> 
            <div class="rl">Note Minimum</div> 
            <div class="rr">
                <input type="range" min="0" max="5" step="1" value="0" oninput="C.minRat=+this.value;this.nextElementSibling.textContent=this.value||'—';">
                <span class="rv">—</span>
            </div> 
        </div> 
        <button class="abn" style="width:100%;margin-top:25px" onclick="refillAndNext(); closePanel('panel-filter')">Appliquer & Rafraîchir</button> 
    </div> 
</div>

<div class="panel" id="panel-grid"> 
    <div class="pbox" style="height:85vh; display:flex; flex-direction:column;"> 
        <button class="px" onclick="closePanel('panel-grid')">✕</button> 
        <div class="ptitle">Explorateur</div> 
        <div class="grid" id="grid-wrap" style="flex:1; overflow-y:auto; padding-bottom:20px; align-content:start;"></div> 
    </div> 
</div>

<div class="panel" id="panel-info"> 
    <div class="pbox"> 
        <button class="px" onclick="closePanel('panel-info')">✕</button> 
        <div class="ptitle">Informations</div> 
        <div id="info-fname" style="font-size:12px;color:rgba(255,255,255,.5);margin-bottom:8px;word-break:break-all;line-height:1.6;text-align:center;"></div> 
        <div id="info-meta" style="font-size:11px;color:rgba(255,255,255,.4);margin-bottom:16px;text-align:center; background:rgba(0,0,0,0.2); padding:8px; border-radius:10px;"></div>

        <div class="slbl">ACTIONS MÉDIA</div>
        <button class="abn" style="width:100%; background:rgba(255,165,0,0.2); color:#ffa500; margin-bottom:10px;" onclick="resetViewsCur()">↺ Remettre les vues à 0</button>
        
        <div class="slbl">PERSONNES</div> 
        <div id="name-wrap" style="min-height:30px;margin-bottom:10px"></div> 
        <div class="tag-row"> 
            <input class="tin" id="name-in" list="known-names" placeholder="Ajouter personne..." onkeydown="if(event.key==='Enter')addName()"> 
            <button class="abn" style="padding:12px 18px; background:#00cfff;" onclick="addName()">+</button> 
        </div> 
        <datalist id="known-names"></datalist>
        
        <div class="slbl">TAGS</div> 
        <div id="tag-wrap" style="min-height:30px;margin-bottom:10px"></div> 
        <div class="tag-row"> 
            <input class="tin" id="tag-in" placeholder="Ajouter tag..." onkeydown="if(event.key==='Enter')addTag()"> 
            <button class="abn" style="padding:12px 18px;" onclick="addTag()">+</button> 
        </div> 
        
        <div class="slbl">NOTE PERSONNELLE</div> 
        <textarea id="note-ta" placeholder="Écrire une note..."></textarea> 
        <button class="abn" style="width:100%;margin-top:16px" onclick="saveNote()">Enregistrer</button> 
    </div> 
</div>

<div class="panel" id="panel-cfg"> 
    <div class="pbox"> 
        <button class="px" onclick="closePanel('panel-cfg')">✕</button> 
        <div class="ptitle">Réglages Système</div> 
        
        <div class="slbl">STABILITÉ CORE (USURE)</div>
        <div class="row">
            <div class="rl">Vitesse de dégradation</div>
            <div class="rr">
                <input type="range" id="cfg-wear-mult" min="0" max="50" value="10" oninput="C.wearMultiplier=this.value/10; localStorage.setItem('wear_mult', C.wearMultiplier); this.nextElementSibling.textContent=C.wearMultiplier+'x'; updateStability();">
                <span class="rv">1x</span>
            </div>
        </div>
        <div style="font-size:10px; color:rgba(255,255,255,0.4); margin-bottom:15px; line-height:1.4;">
            INFO : Un fichier se dégrade à chaque lecture. Un Favori restaure <b>+20%</b>. Une note de 5★ soigne <b>+25%</b>. Une note de 1★ mutile le fichier de <b>-20%</b>.
        </div>

        <div class="slbl">SYSTÈME AVANCÉ</div> 
        <div class="row"> 
            <div class="rl">Égaliser vues vidéos</div> 
            <button class="abn" style="background:rgba(0,255,128,0.2);color:#00ff80" onclick="fetch('/api/equalize_views', {method:'POST'}); toast('Tâche lancée...');">Lancer</button> 
        </div>
        <div class="row"> 
            <div class="rl">Réindexer médias</div> 
            <button class="abn" onclick="fetch('/api/reindex', {method:'POST'}); toast('🔄 Scan lancé...');">↺ Scan</button> 
        </div> 
        <div class="row"> 
            <div class="rl" style="color:#ff3030;font-weight:bold;">⚠️ Purger BDD</div> 
            <button class="abn" style="background:rgba(255,48,48,0.2);color:#ff3030" onclick="if(confirm('Effacer stats ?')) post('/api/purge_db',{}).then(()=>location.reload())">Purger</button> 
        </div>
        
        <div class="slbl">RÉGLAGES PURGATOIRE</div>
        <div class="row">
            <div class="rl">Pénalité de base (jours)</div>
            <input type="number" id="cfg-purg-base" style="width:60px;text-align:center" value="0" onchange="saveConfig()">
        </div>
        <div class="row">
            <div class="rl">Multiplicateur (Vues x Mult)</div>
            <input type="number" step="0.1" id="cfg-purg-mult" style="width:60px;text-align:center" value="1.0" onchange="saveConfig()">
        </div>
        <button class="abn" id="btn-amnesty" style="width:100%; background:rgba(0,255,128,0.15); color:#00ff80; margin-top:10px; display:none;" onclick="purgatoryAmnesty()">🕊️ Amnistie Générale (Vider le Purgatoire)</button>

        <div class="slbl">EXPÉRIENCE</div> 
        <div class="row"> 
            <div class="rl">Diaporama (sec)</div> 
            <select id="sel-slideshow" onchange="setSlideshowDelay(parseInt(this.value))"> 
                <option value="3">3 s</option> 
                <option value="5" selected>5 s</option> 
                <option value="8">8 s</option> 
                <option value="12">12 s</option> 
                <option value="20">20 s</option> 
            </select> 
        </div> 
        <div class="row"> 
            <div class="rl">Mode défaut</div> 
            <select id="sel-mode" onchange="selectMode(this.value)"> 
                <option value="zen">Zen</option> 
                <option value="gallery">Galerie Simple</option> 
                <option value="infected">Infection</option> 
            </select> 
        </div> 
        <div class="row"> 
            <div class="rl">Infection (%)</div> 
            <div class="rr">
                <input type="range" min="0" max="100" value="5" oninput="C.virusRate=this.value/100; dynamicVirusRate=C.virusRate; this.nextElementSibling.textContent=this.value+'%'">
                <span class="rv">5%</span>
            </div> 
        </div>
        
        <div class="slbl">AFFICHAGE GLOBALE</div> 
        <div class="row"> 
            <div class="rl">Activer le Masque Auto (Visages)</div>
            <button class="tog" id="tog-mask" onclick="togC('faceMaskEnabled',this); applyMaskConfig();"></button>
        </div>
        <div class="row"> 
            <div class="rl">Mode Schizophrénie (Flash 16ms)</div>
            <button class="tog" onclick="togC('schizoMode',this);"></button>
        </div>
        <div class="row"> 
            <div class="rl">Effet Time-Smear (Vidéos)</div>
            <button class="tog on" onclick="togC('timeSmear',this); if(C.timeSmear && cur && cur.video) loopSmear();"></button>
        </div>
        <div class="row">
            <div class="rl">Time-Smear Exclusif (Dans le masque)</div>
            <button class="tog" onclick="togC('exclusiveSmear',this)"></button>
        </div>
        <div class="row"> 
            <div class="rl">Filtre Écran</div> 
            <select onchange="document.getElementById('stage').className = this.value !== 'none' ? 'ov-' + this.value : '';">
                <option value="none">Normal</option>
                <option value="invert">Inversion de lumière</option>
            </select> 
        </div> 
        <div class="row"> 
            <div class="rl">Thème UI</div> 
            <select onchange="setTheme(this.value)">
                <option value="dark">Dark</option>
                <option value="neon">Neon</option>
                <option value="ice">Ice</option>
                <option value="gold">Gold</option>
                <option value="mono">Mono</option>
            </select> 
        </div> 
        <div class="row"> 
            <div class="rl">Notes ★ visibles</div> 
            <button class="tog on" onclick="togC('showStars',this); document.getElementById('stars').style.display=C.showStars?'flex':'none';"></button> 
        </div> 
        <div class="row"> 
            <div class="rl">Musique de fond</div> 
            <select id="sel-music" onchange="setBgMusic(this.value)"> 
                <option value="">Aucune</option> 
            </select> 
        </div> 
        
        <div id="stats-wrap" style="margin-top:15px"></div> 

        <div class="slbl">PURGATOIRE (MÉDIAS CONDAMNÉS)</div>
        <div id="purgatory-list" style="display:flex; flex-direction:column; gap:8px; margin-top:10px; margin-bottom:20px;"></div>
    </div> 
</div>

<script>
if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js').catch(()=>{}); }

document.querySelectorAll('.panel').forEach(p => { 
    p.addEventListener('click', e => { if(e.target === p) closePanel(p.id); }); 
});

const C = { 
    hardcore: true, mode: 'all', trans: 'fade', sort: 'unseen', 
    ssDur: 5, bgMusic: '', showStars: true, showProg: true, 
    autoVid: true, vidLoop: true, minRat: 0,
    faceMaskEnabled: false, maskStyle: 'pixel', maskPixelSize: 15,
    exclusiveSmear: false, stealthMode: 'none', stealthIntensity: 60,
    timeSmear: true, fxStyle: 'none', fxIntensity: 0,
    demoFilter: 'all', schizoMode: false,
    virusRate: 0.05, // FIX: taux d'infection par défaut (manquait dans l'objet C)
    wearMultiplier: 1.0 // Multiplicateur d'usure
};

// === CODES PIN (modifiables ici) ===
const ACCESS_PIN = '1002';   // PIN galerie normale
const VAULT_PIN  = '6666';   // PIN coffre-fort

// Charge le multiplicateur depuis le localStorage
document.addEventListener("DOMContentLoaded", () => {
    let wm = localStorage.getItem('wear_mult');
    if (wm !== null) {
        C.wearMultiplier = parseFloat(wm);
        let el = document.getElementById('cfg-wear-mult');
        if (el) {
            el.value = C.wearMultiplier * 10;
            el.nextElementSibling.textContent = C.wearMultiplier + 'x';
        }
    }
});

// --- AUDIO ROT & WEAR (WEB AUDIO API AVANCÉE) ---
let wearCtx = null, crackleGain = null, crackleSource = null;
let droneOsc = null, droneGain = null;

function initWearAudio() {
    if (wearCtx) return;
    try {
        wearCtx = new (window.AudioContext || window.webkitAudioContext)();
        
        // 1. Vinyle et Bruit blanc
        let bufSize = wearCtx.sampleRate * 2; 
        let buf = wearCtx.createBuffer(1, bufSize, wearCtx.sampleRate);
        let data = buf.getChannelData(0);
        for (let i = 0; i < bufSize; i++) { data[i] = (Math.random() * 2 - 1) * (Math.random() < 0.03 ? 0.9 : 0.02); }
        crackleSource = wearCtx.createBufferSource();
        crackleSource.buffer = buf;
        crackleSource.loop = true;

        let filter = wearCtx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 2500; 

        crackleGain = wearCtx.createGain();
        crackleGain.gain.value = 0; 
        crackleSource.connect(filter).connect(crackleGain).connect(wearCtx.destination);
        crackleSource.start();

        // 2. Drone Sub-Basse Horrifique (Simule un ordinateur en fusion)
        droneOsc = wearCtx.createOscillator();
        droneOsc.type = 'sawtooth';
        droneOsc.frequency.value = 40; 
        droneGain = wearCtx.createGain();
        droneGain.gain.value = 0;
        droneOsc.connect(droneGain).connect(wearCtx.destination);
        droneOsc.start();

    } catch(e) {}
}

document.addEventListener('click', initWearAudio, {once:true});
document.addEventListener('touchstart', initWearAudio, {once:true});

// --- GENERATEUR DE ZALGO TEXT ---
const zalgoChars = ['̍','̎','̄','̅','̿','̑','̆','̐','͒','͗','͑','̇','̈','̊','͂','̓','̈','͊','͋','͌','̃','̂','̌','͐','̀','́','̋','̏','̒','̓','̔','̽','̉','ͣ','ͤ','ͥ','ͦ','ͧ','ͨ','ͩ','ͪ','ͫ','ͬ','ͭ','ͮ','ͯ','̾','͛','͆','̚','̕','̛','͜','͝','͞','͟','͠','͢','̸','̷','͜','͝','͞','͟'];
function glitchText(text, intensity) {
    if(intensity < 0.1) return text;
    let res = '';
    for(let i=0; i<text.length; i++) {
        res += text[i];
        if(Math.random() < intensity) {
            let count = Math.floor(Math.random() * (intensity * 10));
            for(let j=0; j<count; j++) res += zalgoChars[Math.floor(Math.random()*zalgoChars.length)];
        }
    }
    return res;
}

// --- CALCUL DE LA STABILITÉ EN CONTINU ---
function updateStability() {
    if (!cur) return;
    if (galleryMode) {
        // Galerie : média toujours intact, pas de filtre, pas d'usure, vidéo en lecture nette
        cur.wearFilter = 'none'; cur.wearMosh = 0;
        if (cur.el) { cur.el.style.filter = 'none'; cur.el.style.animation = 'none'; }
        return;
    }
    let hud = document.getElementById('stability-hud');
    
    let ageHours = Math.max(1, (Date.now()/1000 - (cur.ctime || Date.now()/1000)) / 3600);
    let consumptionRate = (cur.views || 0) / ageHours;
    
    // Base wear modifiée par le multiplicateur
    let wearMultiplier = C.wearMultiplier !== undefined ? C.wearMultiplier : 1.0;
    let baseWear = (consumptionRate * 15) + ((cur.views || 0) * 0.8);
    let stability = 100 - (baseWear * wearMultiplier);
    
    // Influence directe des actions de l'utilisateur
    if (cur.liked) stability += 20; // Favoris = Soin instantané
    if (cur.rating) {
        if (cur.rating === 5) stability += 25;       // Restauration divine
        else if (cur.rating === 4) stability += 10;  // Soin mineur
        else if (cur.rating === 3) stability += 0;   // Neutre
        else if (cur.rating === 2) stability -= 10;  // Dommage
        else if (cur.rating === 1) stability -= 20;  // Coup critique / Glitch immédiat
    }

    // Punitions fatales
    // Dette de temps désactivée -> plus de pénalité de stabilité pour les médias "sacrifiés".
    if (cur.infected && C.hardcore) stability -= 25; 
    
    stability = Math.max(0, Math.min(100, stability));
    
    // Mise à jour de l'UI
    let fill = document.getElementById('stab-fill');
    let txt = document.getElementById('stab-val-text');
    let lbl = document.getElementById('stab-lbl-text');
    let stage = document.getElementById('stage');

    fill.style.width = stability + '%';
    
    // Glissement progressif : Vert (120) vers Rouge (0)
    let hue = Math.max(0, stability * 1.2); 
    fill.style.background = `hsl(${hue}, 100%, 50%)`;
    fill.style.boxShadow = `0 0 15px hsla(${hue}, 100%, 50%, 0.8)`;

    let wearRatio = (100 - stability) / 100; // 0.0 (Neuf) -> 1.0 (Détruit)
    cur.wearRatio = wearRatio;                // mémorisé : pilote la dégradation binaire à la sortie

    // HUD Text Glitches
    if (stability > 15) {
        lbl.textContent = glitchText("STABILITÉ CORE", wearRatio);
        lbl.style.color = `rgba(255,255,255,0.8)`;
        txt.textContent = Math.round(stability) + '%';
    } else {
        lbl.textContent = glitchText("ÉCHEC SYSTÈME", 0.9);
        lbl.style.color = `#ff3030`;
        txt.textContent = (Math.random() > 0.5 ? Math.round(Math.random() * 15) : Math.round(stability)) + '%';
    }

    // Effet sang / Surchauffe sur les bords de l'écran (images uniquement)
    if (stability < 15 && !cur.video) { stage.classList.add('screen-fatal'); } 
    else { stage.classList.remove('screen-fatal'); }

    if (cur.video) {
        // --- VIDÉO : DATAMOSHING PIXEL TEMPS RÉEL ---
        // Plus de filtre lumière/contraste/sépia, plus de ralenti, plus de tremblement.
        // Seul le datamosh canvas (loopFX -> renderVideoDatamosh) s'applique, piloté par l'usure.
        cur.wearFilter = 'none';
        cur.wearMosh = wearRatio;            // intensité du datamosh temps réel
        cur.el.classList.remove('wear-severe', 'wear-fatal');
        cur.el.style.animation = 'none';
        cur.el.style.mixBlendMode = 'normal';
        cur.el.style.filter = 'none';
        if (cur.el.playbackRate !== 1.0) { cur.el.preservesPitch = true; cur.el.playbackRate = 1.0; }
    } else {
        // --- IMAGE : pas de filtre CSS, le fichier sur disque porte la dégradation ---
        cur.wearFilter = 'none';
        cur.el.style.filter = 'none';
        cur.el.style.animation = 'none';
        cur.el.classList.remove('wear-severe', 'wear-fatal');
        // La dégradation binaire est inscrite à la sortie du média (voir triggerWearDamage).
    }
    
    // Audio Horrifique (Web Audio) — désactivé sur les vidéos (audio propre)
    if (wearCtx) {
        if (wearCtx.state === 'suspended') wearCtx.resume();
        let audWear = cur.video ? 0 : wearRatio;
        if (crackleGain) crackleGain.gain.setTargetAtTime(audWear * 0.6, wearCtx.currentTime, 0.2); 
        if (droneGain) droneGain.gain.setTargetAtTime(audWear > 0.4 ? (audWear - 0.4) * 1.5 : 0, wearCtx.currentTime, 0.5);
    }
}

let hasBooted = false, appMode = 'zen', galleryMode = false;
let dynamicVirusRate = C.virusRate, lastShowTime = 0;
let bufs = {all:[], fav:[], image:[], video:[], hist:[], suggest:[]};
let cur = null, activeSlot = 'a', ssOn = false, ssTimer = null;
let navH = [], navI = -1, navOpen = false, pin = '', loginDone = false, badPinCount = 0;
let isLocked = false, lockTaps = 0, lockTimer = null, bgMusicPlaying = false;
let allKnownNames = [], isRefilling = false, viewInterval = null, wakeLock = null, upin = '';
let pendingSacrifices = 0, inVaultMode = false;
let savedInfectionCount = 0; 
let isTransitioning = false; 
let smearRAF = null, stealthRAF = null, fxRAF = null, schizoTimer = null;

let isDrawingMask = false, maskDragStart = null, currentDragBox = null, globalCustomBoxes = [];
let quickFxOpen = false, antidoteActive = false, antidoteTimer = null, puzzleVideoPieces = [];
let audioPlaylist = [], currentAudioIdx = 0;

let pingFailCount = 0;
let lockdownCountdownInterval = null;
let burnMode = false;
let burnStrobeRAF = null, burnStrobeFrame = 0;

function formatBytes(bytes, decimals = 2) {
    if (!+bytes) return '0 Octets';
    const k = 1024, dm = decimals < 0 ? 0 : decimals, sizes = ['Octets', 'Ko', 'Mo', 'Go', 'To'];
    let i = Math.floor(Math.log(bytes) / Math.log(k)); i = Math.min(Math.max(i, 0), sizes.length - 1);
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function formatDate(ts) {
    if(!ts) return 'Inconnue';
    return new Date(ts * 1000).toLocaleString('fr-FR');
}

function loadConfig() {
    fetch('/api/config_get').then(r=>r.json()).then(d => {
        document.getElementById('cfg-purg-base').value = d.purgatory_base || 0;
        document.getElementById('cfg-purg-mult').value = d.purgatory_mult || 1.0;
    }).catch(()=>{});
}

function saveConfig() {
    const b = document.getElementById('cfg-purg-base').value;
    const m = document.getElementById('cfg-purg-mult').value;
    post('/api/config_set', {purgatory_base: b, purgatory_mult: m}).then(()=>toast('Réglages sauvegardés'));
}

function resetViewsCur() {
    if(!cur) return;
    post('/api/reset_views', {file: cur.file}).then(() => {
        cur.views = 0;
        updateHUD();
        updateStability();
        toast('Vues réinitialisées à 0', 2000);
    });
}

function burnStrobeLoop() {
    burnStrobeFrame++;
    const el = document.getElementById('burn-strobe-js');
    if (el) {
        if (burnStrobeFrame % 2 === 0) { el.style.background = '#ffffff'; el.style.opacity = '0.32'; } 
        else { el.style.background = '#000000'; el.style.opacity = '0.28'; }
    }
    if (burnMode) burnStrobeRAF = requestAnimationFrame(burnStrobeLoop);
}

function enterBurnMode() {
    burnMode = true;
    document.getElementById('lockdown-screen').style.display = 'none';
    document.body.classList.add('burn-mode');
    document.getElementById('time-tracker').style.visibility = 'hidden';
    document.getElementById('hud-name').style.visibility = 'hidden';
    document.getElementById('stars').style.visibility = 'hidden';
    document.getElementById('stability-hud').style.visibility = 'hidden';
    
    post('/api/burn_enter', {}).then(() => {
        burnStrobeFrame = 0;
        burnStrobeRAF = requestAnimationFrame(burnStrobeLoop);
        bufs[C.mode] = [];
        refill(C.mode).then(() => {
            isRefilling = false;
            if ((bufs[C.mode] || []).length > 0) {
                document.getElementById('empty-gallery-msg').style.display = 'none';
                isTransitioning = false;
                next();
                if (!ssOn) toggleSS();
            }
        });
    }).catch(() => {});
}

function exitBurnMode() {
    burnMode = false;
    if (burnStrobeRAF) { cancelAnimationFrame(burnStrobeRAF); burnStrobeRAF = null; }
    const jsEl = document.getElementById('burn-strobe-js');
    if (jsEl) { jsEl.style.opacity = '0'; }
    document.body.classList.remove('burn-mode');
    document.getElementById('time-tracker').style.visibility = '';
    document.getElementById('hud-name').style.visibility = '';
    document.getElementById('stars').style.visibility = '';
    document.getElementById('stability-hud').style.visibility = '';
    if (ssOn) toggleSS();
    if (cur && cur.video && cur.el) { cur.el.pause(); }
    post('/api/burn_exit', {}).catch(()=>{});
    showLockdownScreen();
}

function showLockdownScreen() {
    document.getElementById('lockdown-screen').style.display = 'flex';
    updateLockdownCountdown();
    if (!lockdownCountdownInterval) {
        lockdownCountdownInterval = setInterval(updateLockdownCountdown, 1000);
    }
}

function updateLockdownCountdown() {
    const el = document.getElementById('lockdown-countdown');
    if (!el) return;
    const now = new Date();
    const midnight = new Date();
    midnight.setHours(24, 0, 0, 0);
    const diff = Math.max(0, Math.floor((midnight - now) / 1000));
    const h = Math.floor(diff / 3600);
    const m = Math.floor((diff % 3600) / 60);
    const s = diff % 60;
    el.textContent = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    if (diff === 0) {
        clearInterval(lockdownCountdownInterval);
        lockdownCountdownInterval = null;
        setTimeout(() => location.reload(), 2000);
    }
}

function updateDailyTimer(remaining, quota) {
    const effectiveQuota = quota || 2700;
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    const color = remaining < 300 ? '#ff3030' : remaining < 600 ? '#ff9100' : 'rgba(255,255,255,0.6)';
    const el = document.getElementById('time-tracker');
    el.style.color = color;
    const isNight = (new Date().getHours() === 23 || new Date().getHours() < 6);
    el.textContent = isNight ? `🌙 ${m}m ${String(s).padStart(2,'0')}s restants` : `⏱ ${m}m ${String(s).padStart(2,'0')}s restants`;
}

setInterval(() => {
    if(loginDone && !burnMode) {
        post('/api/ping_time', {ping_seconds:10}).then(d => {
            pingFailCount = 0;
            if (d.locked) showLockdownScreen();
            else if (d.remaining !== undefined) updateDailyTimer(d.remaining, d.quota);
        }).catch(() => {
            if (loginDone) { pingFailCount++; if (pingFailCount >= 2) showLockdownScreen(); }
        });
    }
}, 10000);

function formatTime(seconds) {
    let h = Math.floor(seconds / 3600);
    let m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
}

function updatePurgCost() {
    // Dette de temps désactivée : on masque toujours l'indicateur.
    const el = document.getElementById('purg-cost');
    if (el) el.style.display = 'none';
}

setInterval(updatePurgCost, 1000);

function scheduleSchizoFlash() {
    if(schizoTimer) clearTimeout(schizoTimer);
    schizoTimer = setTimeout(() => {
        if(loginDone && C.schizoMode && document.body.classList.contains('ui-hidden') && bufs.all.length > 0) {
            let r_media = bufs.all[Math.floor(Math.random() * bufs.all.length)].file;
            let flash = document.createElement('div');
            flash.style.cssText = `position:fixed;inset:0;z-index:9999999;background:url('${r_media}') center/cover;pointer-events:none;`;
            document.body.appendChild(flash);
            setTimeout(() => flash.remove(), 16); 
        }
        scheduleSchizoFlash();
    }, Math.random() * 15000 + 8000);
}
scheduleSchizoFlash();

function toggleQuickFX() {
    quickFxOpen = !quickFxOpen;
    document.getElementById('quick-fx-hud').classList.toggle('on', quickFxOpen);
    document.getElementById('quick-fx-btn').classList.toggle('active', quickFxOpen);
    resetUI();
}

function toggleDrawMask() {
    isDrawingMask = !isDrawingMask;
    document.getElementById('btn-draw-mask').classList.toggle('active', isDrawingMask);
    if (!isDrawingMask) { maskDragStart = null; currentDragBox = null; applyMaskConfig(); }
}

function clearMasks() {
    globalCustomBoxes = [];
    if(cur) {
        cur.customBoxes = []; maskDragStart = null; currentDragBox = null; applyMaskConfig();
        toast("🗑️ Tracés effacés", 1000);
    }
}

function resetFX() {
    if(cur) {
        cur.radialBuffer=[]; cur.lastFxData=null; cur._fxKey=null; cur._fxDone=false;
        if (cur.el) { cur.el.style.opacity='1'; cur.el.style.filter=''; }
    }
}

function loopFX() {
    if (!cur) return;
    fxRAF = requestAnimationFrame(loopFX);
    
    // Si aucun effet FX manuel n'est activé : datamosh d'usure (vidéo) ou affichage brut
    if (C.fxStyle === 'none' || C.fxIntensity === 0) {
        if (cur.video && !galleryMode && (cur.wearMosh || 0) > 0.02) {
            renderVideoDatamosh();   // datamosh pixel temps réel
            return;
        }
        if (cur.el) {
            cur.el.style.filter = cur.video ? 'none' : (cur.wearFilter || 'none');
            cur.el.style.opacity = '1';
        }
        if (cur.fxCanvas) {
            const ctx = cur.fxCanvas.getContext('2d');
            ctx.clearRect(0, 0, cur.fxCanvas.width, cur.fxCanvas.height);
        }
        return;
    }
    
    if (cur.video && (cur.el.paused || cur.el.readyState < 2)) return;

    const w = cur.video ? cur.el.videoWidth : cur.el.naturalWidth;
    const h = cur.video ? cur.el.videoHeight : cur.el.naturalHeight;
    if (w === 0 || h === 0) return;

    cur.el.style.opacity = '0';
    cur.el.style.filter = '';

    const cvs = cur.fxCanvas;
    const sw = Math.min(w, 640);
    const sh = Math.floor(h * (sw/w));
    if (cvs.width !== sw) cvs.width = sw;
    if (cvs.height !== sh) cvs.height = sh;
    const ctx = cvs.getContext('2d', {willReadFrequently: true});

    let weight = C.fxIntensity / 100;
    let fx = C.fxStyle;

    // FIX perf : pour une image fixe, ne pas retraiter le même FX 60x/s
    if (!cur.video) {
        const _k = fx + '|' + C.fxIntensity;
        if (cur._fxKey === _k && cur._fxDone) return;
        cur._fxKey = _k; cur._fxDone = false;
    }

    ctx.clearRect(0,0,sw,sh);
    ctx.drawImage(cur.el, 0, 0, sw, sh);

    if (weight <= 0.01) return;

    if (fx === 'radial') {
        if (!cur.radialBuffer) cur.radialBuffer = [];
        let tempC = document.createElement('canvas'); tempC.width=sw; tempC.height=sh;
        tempC.getContext('2d').drawImage(cur.el, 0, 0, sw, sh);
        cur.radialBuffer.push(tempC);
        if(cur.radialBuffer.length > 60) cur.radialBuffer.shift();

        let maxRings = Math.max(2, Math.floor(weight * 20)); 
        let centerX = sw/2, centerY = sh/2;
        let maxRadius = Math.hypot(centerX, centerY);

        ctx.clearRect(0,0,sw,sh);
        for(let r=maxRings; r>=0; r--) {
            let frameIdx = Math.max(0, cur.radialBuffer.length - 1 - (r * 4));
            let frame = cur.radialBuffer[frameIdx];
            if(!frame) continue;
            ctx.save();
            ctx.beginPath();
            let radius = maxRadius * ((r+1)/maxRings);
            ctx.arc(centerX, centerY, radius, 0, Math.PI*2);
            ctx.clip();
            ctx.drawImage(frame, 0, 0);
            ctx.restore();
        }
    }
    else if (fx === 'motionblur') {
        let steps = Math.max(2, Math.floor(weight * 15));
        ctx.globalAlpha = 1 / steps;
        for(let i=1; i<steps; i++) { ctx.drawImage(cur.el, i * (weight * 10), i * (weight * 5), sw, sh); }
        ctx.globalAlpha = 1.0;
    }
    else if (fx === 'stegano') {
        let diffSlider = weight * 10; 
        if(diffSlider > 0) {
            ctx.globalAlpha = Math.min(1, diffSlider / 10);
            if(!window.noisePat) {
                let nc = document.createElement('canvas'); nc.width=256; nc.height=256;
                let nctx = nc.getContext('2d');
                let id = nctx.createImageData(256,256);
                for(let i=0;i<id.data.length;i+=4) {
                    let v = Math.random()*255;
                    id.data[i]=v; id.data[i+1]=v; id.data[i+2]=v; id.data[i+3]=255;
                }
                nctx.putImageData(id,0,0);
                window.noisePat = nc;
            }
            ctx.fillStyle = ctx.createPattern(window.noisePat, 'repeat');
            ctx.fillRect(0,0,sw,sh);
            ctx.globalAlpha = 1;
        }
    }

    let currentData = ctx.getImageData(0,0,sw,sh);
    let data = currentData.data;

    if (fx === 'databend') {
        let thresh = weight * 0.15; 
        for(let i=0; i<data.length; i+=4) {
            if(Math.random() < thresh) { let temp = data[i]; data[i] = data[i+2]; data[i+2] = temp; }
        }
    }
    else if (fx === 'deadpixels') {
        let num = Math.floor((sw * sh) * (weight * 0.05)); 
        for(let k=0; k<num; k++) {
            let idx = Math.floor(Math.random() * (sw*sh)) * 4;
            if(Math.random() > 0.5) { data[idx]=255; data[idx+1]=0; data[idx+2]=255; } 
            else { data[idx]=0; data[idx+1]=255; data[idx+2]=0; }
        }
    }
    else if (fx === 'crypto') {
        let strength = weight * 255;
        for(let i=0; i<data.length; i+=4) {
            let px = (i/4) % sw; let py = Math.floor((i/4) / sw);
            if ((px + py) % 2 === 0) {
                data[i] = Math.max(0, data[i] - strength);
                data[i+1] = Math.max(0, data[i+1] - strength);
                data[i+2] = Math.max(0, data[i+2] - strength);
            }
        }
    }
    else if (fx === 'entropy') {
        for(let i=0; i<data.length; i+=4) {
            data[i] = data[i]*(1-weight) + (255-data[i])*weight;
            data[i+1] = data[i+1]*(1-weight) + (255-data[i+1])*weight;
            data[i+2] = data[i+2]*(1-weight) + (255-data[i+2])*weight;
        }
    }
    else if (fx === 'mosh' || fx === 'motion') {
        if(!cur.lastFxData) { cur.lastFxData = new Uint8ClampedArray(data); } 
        else {
            let lastData = cur.lastFxData; let threshLimit = (1 - weight) * 150; 
            for(let i=0; i<data.length; i+=4) {
                let diff = Math.abs(data[i]-lastData[i]) + Math.abs(data[i+1]-lastData[i+1]) + Math.abs(data[i+2]-lastData[i+2]);
                if(fx === 'mosh' && diff < threshLimit) { data[i] = lastData[i]; data[i+1] = lastData[i+1]; data[i+2] = lastData[i+2]; } 
                else if(fx === 'motion' && diff < threshLimit) { data[i]=0; data[i+1]=0; data[i+2]=0; }
            }
        }
    }

    ctx.putImageData(currentData, 0, 0);

    if (fx === 'mosh') { cur.lastFxData = new Uint8ClampedArray(currentData.data); } 
    else if (fx === 'motion') {
         let tctx = document.createElement('canvas').getContext('2d');
         tctx.canvas.width = sw; tctx.canvas.height = sh;
         tctx.drawImage(cur.el, 0, 0, sw, sh);
         cur.lastFxData = tctx.getImageData(0,0,sw,sh).data;
    }
    if (!cur.video) cur._fxDone = true;
}

// --- VRAI DATAMOSHING PIXEL TEMPS RÉEL (VIDÉO) ---
// Effet « bloom/smear » de datamosh : on garde les pixels précédents là où le
// mouvement est faible (suppression de P-frames), + glissement de blocs à forte usure.
function renderVideoDatamosh() {
    const item = cur;
    if (!item || !item.video || !item.el || !item.fxCanvas) return;
    if (item.el.paused || item.el.readyState < 2) return;
    const vw = item.el.videoWidth, vh = item.el.videoHeight;
    if (!vw || !vh) return;

    const cvs = item.fxCanvas;
    const sw = Math.min(vw, 640);
    const sh = Math.floor(vh * (sw / vw));
    if (cvs.width !== sw)  { cvs.width = sw;  item.moshPrev = null; }
    if (cvs.height !== sh) { cvs.height = sh; item.moshPrev = null; }
    const ctx = cvs.getContext('2d', { willReadFrequently: true });

    const wear = Math.min(item.wearMosh || 0, 1);
    // Seuil de « gel » des pixels : plus l'usure est forte, plus on fige -> smear datamosh
    const keepThreshold = 8 + wear * 90;

    ctx.drawImage(item.el, 0, 0, sw, sh);
    const frame = ctx.getImageData(0, 0, sw, sh);
    const data = frame.data;

    if (item.moshPrev && item.moshPrev.length === data.length) {
        const prev = item.moshPrev;
        for (let i = 0; i < data.length; i += 4) {
            const diff = Math.abs(data[i] - prev[i]) + Math.abs(data[i+1] - prev[i+1]) + Math.abs(data[i+2] - prev[i+2]);
            if (diff < keepThreshold) { data[i] = prev[i]; data[i+1] = prev[i+1]; data[i+2] = prev[i+2]; }
        }
    }
    ctx.putImageData(frame, 0, 0);

    // On mémorise la sortie pour l'accumulation du smear
    item.moshPrev = new Uint8ClampedArray(data);

    // Glissement de blocs (glitch type P-frame) à forte usure
    if (wear > 0.4) {
        const blocks = Math.floor(wear * 5);
        for (let b = 0; b < blocks; b++) {
            const bw = 16 + Math.floor(Math.random() * 56);
            const bh = 8 + Math.floor(Math.random() * 28);
            const bx = Math.floor(Math.random() * Math.max(1, sw - bw));
            const by = Math.floor(Math.random() * Math.max(1, sh - bh));
            const dx = Math.floor((Math.random() - 0.5) * wear * 36);
            const dy = Math.floor((Math.random() - 0.5) * wear * 14);
            try { ctx.drawImage(cvs, bx, by, bw, bh, bx + dx, by + dy, bw, bh); } catch(e){}
        }
    }

    item.el.style.opacity = '0';
}

function loopSmear() {
    if (!cur || !cur.video || !cur.smearCanvas || !C.timeSmear || C.fxStyle !== 'none') return;
    smearRAF = requestAnimationFrame(loopSmear);
    if (cur.el.paused || cur.el.readyState < 2) return;
    
    const cvs = cur.smearCanvas, ctx = cvs.getContext('2d');
    const vw = cur.el.videoWidth, vh = cur.el.videoHeight;
    
    if (cvs.width !== vw) cvs.width = vw;
    if (cvs.height !== vh) { cvs.height = vh; ctx.fillStyle = '#000'; ctx.fillRect(0,0,vw,vh); }
    
    if (vw > 0 && vh > 0) {
        ctx.save();
        if (C.exclusiveSmear && (globalCustomBoxes.length > 0 || (cur.lastFaces?.length > 0 && C.faceMaskEnabled))) {
            ctx.beginPath();
            if (globalCustomBoxes.length > 0) { globalCustomBoxes.forEach(b => ctx.rect(b.x * vw, b.y * vh, b.w * vw, b.h * vh)); } 
            else { cur.lastFaces.forEach(b => ctx.rect(b.x, b.y, b.width, b.height)); }
            ctx.clip();
        }

        ctx.globalCompositeOperation = 'source-over';
        ctx.fillStyle = 'rgba(0, 0, 0, 0.001)';
        ctx.fillRect(0, 0, vw, vh);
        
        ctx.globalAlpha = 0.05;
        ctx.drawImage(cur.el, 0, 0, vw, vh);
        ctx.restore();
    }
}

let faceApiLoaded = false;
async function loadFaceApi() {
    if (faceApiLoaded) return;
    try {
        const MODEL_URL = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model/';
        await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL);
        await faceapi.nets.faceLandmark68TinyNet.loadFromUri(MODEL_URL);
        await faceapi.nets.ageGenderNet.loadFromUri(MODEL_URL);
        faceApiLoaded = true;
        console.log("✅ Face API Loaded.");
        processFaceMask();
    } catch(e) { console.error("Erreur Face API:", e); }
}

function drawPixelatedBox(ctx, media, x, y, width, height, pixelSize) {
    let smallW = Math.max(1, Math.floor(width / pixelSize)), smallH = Math.max(1, Math.floor(height / pixelSize));
    let offCanvas = document.createElement('canvas'); offCanvas.width = smallW; offCanvas.height = smallH;
    let octx = offCanvas.getContext('2d');
    try { octx.drawImage(media, x, y, width, height, 0, 0, smallW, smallH); } catch(e){}
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(offCanvas, 0, 0, smallW, smallH, x, y, width, height);
}

function drawInvertedLightnessBox(ctx, media, x, y, width, height) {
    let smallW = Math.max(1, Math.floor(width / 2)), smallH = Math.max(1, Math.floor(height / 2));
    let offCanvas = document.createElement('canvas'); offCanvas.width = smallW; offCanvas.height = smallH;
    let octx = offCanvas.getContext('2d', { willReadFrequently: true });
    try { octx.drawImage(media, x, y, width, height, 0, 0, smallW, smallH); } catch(e){}
    
    let imgData = octx.getImageData(0, 0, smallW, smallH), data = imgData.data;
    for (let i = 0; i < data.length; i += 4) { data[i] = 255 - data[i]; data[i+1] = 255 - data[i+1]; data[i+2] = 255 - data[i+2]; }
    octx.putImageData(imgData, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(offCanvas, 0, 0, smallW, smallH, x, y, width, height);
}

function drawSlendermanBox(ctx, media, x, y, width, height) {
    ctx.save(); ctx.filter = 'blur(15px) contrast(0.8) brightness(1.1)';
    try { ctx.drawImage(media, x, y, width, height, x - 5, y - 5, width + 10, height + 10); } catch(e){}
    ctx.restore();
}

function drawCryptoNoise(ctx, x, y, width, height) {
    if(!window.cryptoNoise) {
        const c = document.createElement('canvas'); c.width = 200; c.height = 200;
        const xCtx = c.getContext('2d', {willReadFrequently:true}), id = xCtx.createImageData(200,200);
        for(let i=0; i<id.data.length; i+=4){ let v = Math.random()>0.5 ? 255 : 0; id.data[i]=v; id.data[i+1]=v===255?0:255; id.data[i+2]=255; id.data[i+3]=255; }
        xCtx.putImageData(id,0,0); window.cryptoNoise = c;
    }
    ctx.drawImage(window.cryptoNoise, Math.random()*100, Math.random()*100, 100, 100, x, y, width, height);
}

function drawDecoy(ctx, item, x, y, width, height) {
    if(bufs.image.length > 0) {
        if(!item.decoyImg) { item.decoyImg = new Image(); item.decoyImg.src = bufs.image[Math.floor(Math.random()*bufs.image.length)].file; }
        if(item.decoyImg.complete) ctx.drawImage(item.decoyImg, x, y, width, height);
    } else { ctx.fillStyle = '#111'; ctx.fillRect(x,y,width,height); }
}

function drawFreeze(ctx, item, x, y, width, height) {
    if(!item.freezeCanvas) {
        item.freezeCanvas = document.createElement('canvas');
        item.freezeCanvas.width = item.el.videoWidth || item.el.naturalWidth; item.freezeCanvas.height = item.el.videoHeight || item.el.naturalHeight;
        item.freezeCanvas.getContext('2d').drawImage(item.el, 0, 0, item.freezeCanvas.width, item.freezeCanvas.height);
    }
    ctx.drawImage(item.freezeCanvas, x, y, width, height, x, y, width, height);
}

function drawDesync(ctx, item, x, y, width, height) {
    if(item.video) {
        if(!item.desyncEl) { item.desyncEl = item.el.cloneNode(); item.desyncEl.muted = true; item.desyncEl.play().catch(()=>{}); }
        if(Math.abs((item.el.currentTime - 1) - item.desyncEl.currentTime) > 0.5) { item.desyncEl.currentTime = Math.max(0, item.el.currentTime - 1); }
        if(item.desyncEl.readyState >= 2) ctx.drawImage(item.desyncEl, x, y, width, height, x, y, width, height);
    } else { ctx.fillStyle='#000'; ctx.fillRect(x,y,width,height); }
}

function drawMotionBlur(ctx, item, x, y, width, height) {
    ctx.globalAlpha = 0.2;
    for(let i=0; i<5; i++) { ctx.drawImage(item.el, x + (i*10), y - (i*5), width, height, x, y, width, height); }
    ctx.globalAlpha = 1.0;
}

function renderMaskEffect(ctx, item, box) {
    let x = box.x, y = box.y, w = box.width || box.w, h = box.height || box.h;
    switch(C.maskStyle) {
        case 'pixel': drawPixelatedBox(ctx, item.el, x, y, w, h, C.maskPixelSize || 15); break;
        case 'invert_light': drawInvertedLightnessBox(ctx, item.el, x, y, w, h); break;
        case 'slenderman': drawSlendermanBox(ctx, item.el, x, y, w, h); break;
        case 'crypto': drawCryptoNoise(ctx, x, y, w, h); break;
        case 'leurre': drawDecoy(ctx, item, x, y, w, h); break;
        case 'freeze': drawFreeze(ctx, item, x, y, w, h); break;
        case 'desync': drawDesync(ctx, item, x, y, w, h); break;
        case 'motion_blur': drawMotionBlur(ctx, item, x, y, w, h); break;
        case 'eye_bar': ctx.fillStyle = '#050508'; ctx.fillRect(x, y, w, h); break;
        default: drawPixelatedBox(ctx, item.el, x, y, w, h, 15);
    }
}

let isDetectingFace = false;
async function processFaceMask() {
    if (!cur || isDetectingFace) { requestAnimationFrame(processFaceMask); return; }

    let isAutoMask = (C.faceMaskEnabled || (inVaultMode && cur.applyVaultMask));
    let hasCustomBoxes = (globalCustomBoxes.length > 0) || currentDragBox;

    if ((!isAutoMask && !hasCustomBoxes) || !cur.maskCanvas) { requestAnimationFrame(processFaceMask); return; }

    let item = cur;
    if (item.video && (item.el.paused || item.el.readyState < 2)) { requestAnimationFrame(processFaceMask); return; }

    const w = item.video ? item.el.videoWidth : item.el.naturalWidth;
    const h = item.video ? item.el.videoHeight : item.el.naturalHeight;
    if (w === 0 || h === 0) { requestAnimationFrame(processFaceMask); return; }

    const canvas = item.maskCanvas;
    if (canvas.width !== w) canvas.width = w;
    if (canvas.height !== h) canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);

    if (hasCustomBoxes) {
        ctx.save(); ctx.beginPath();
        if (globalCustomBoxes.length > 0) { globalCustomBoxes.forEach(b => ctx.rect(b.x * w, b.y * h, b.w * w, b.h * h)); }
        if (currentDragBox) { ctx.rect(currentDragBox.x * w, currentDragBox.y * h, currentDragBox.w * w, currentDragBox.h * h); }
        ctx.clip();
        renderMaskEffect(ctx, item, {x:0, y:0, width:w, height:h});
        ctx.restore();

        if (currentDragBox) {
            ctx.strokeStyle = 'red'; ctx.lineWidth = 4; ctx.setLineDash([10, 10]);
            ctx.strokeRect(currentDragBox.x * w, currentDragBox.y * h, currentDragBox.w * w, currentDragBox.h * h);
            ctx.setLineDash([]);
        }
    }

    if (isAutoMask) {
        isDetectingFace = true;
        try {
            if (!item.video && item.faces_data && item.faces_data !== '[]' && item.faces_data !== '') {
                try { item.lastFaces = typeof item.faces_data === 'string' ? JSON.parse(item.faces_data) : item.faces_data; } catch(e){}
            } else if (!item._lastDetectTs || performance.now() - item._lastDetectTs > 250) {
                item._lastDetectTs = performance.now();
                const options = new faceapi.TinyFaceDetectorOptions({ inputSize: 160, scoreThreshold: 0.2 });
                let detections = await faceapi.detectAllFaces(item.el, options).withFaceLandmarks(true).withAgeAndGender();
                
                if (cur === item && detections.length > 0) {
                    item.lastFaces = faceapi.resizeResults(detections, { width: w, height: h });
                    
                    if (!item.facesSavedToDB && (!item.faces_data || item.faces_data === '')) {
                        let m=0, f=0;
                        detections.forEach(d => { if(d.gender==='male') m++; else f++; });
                        let main_demo = m > f ? 'male' : 'female';
                        item.demographics = main_demo;
                        
                        let clean_faces = item.lastFaces.map(d => { let b = d.box || d.detection.box; return {x: b.x, y: b.y, width: b.width, height: b.height}; });
                        item.faces_data = JSON.stringify(clean_faces); item.facesSavedToDB = true; 
                        
                        post('/api/save_faces', {file: item.file, faces: clean_faces, demographics: main_demo}).catch(()=>{});
                    }
                }
            }
            
            if (item.lastFaces) {
                item.lastFaces.forEach(d => {
                    // Résolution robuste de la box : objets faceapi (live) OU boîtes simples (cache DB)
                    const box = (d.detection && d.detection.box) || d.box || d;
                    const landmarks = d.landmarks || (d.detection && d.detection.landmarks);
                    if (C.maskStyle === 'eye_bar' && landmarks) {
                        const left = landmarks.getLeftEye(), right = landmarks.getRightEye();
                        let lx=0, ly=0, rx=0, ry=0;
                        left.forEach(p=>{lx+=p.x; ly+=p.y;}); lx/=left.length; ly/=left.length;
                        right.forEach(p=>{rx+=p.x; ry+=p.y;}); rx/=right.length; ry/=right.length;
                        const angle = Math.atan2(ry - ly, rx - lx), dist = Math.hypot(rx - lx, ry - ly);
                        ctx.save(); ctx.translate((lx+rx)/2, (ly+ry)/2); ctx.rotate(angle);
                        ctx.fillStyle = '#050508'; ctx.fillRect(-dist*1.2, -dist*0.5, dist*2.4, dist); ctx.restore();
                    } else { renderMaskEffect(ctx, item, box); }
                });
            }
        } catch(e) {}
        isDetectingFace = false;
    }
    requestAnimationFrame(processFaceMask);
}

function applyMaskConfig() {
    if (cur && cur.maskCanvas) {
        const ctx = cur.maskCanvas.getContext('2d'); ctx.clearRect(0, 0, cur.maskCanvas.width, cur.maskCanvas.height);
        if(cur.freezeCanvas) cur.freezeCanvas = null;
    }
}

function applyStealthCanvas() {
    if(!cur) return;
    if(C.stealthMode !== 'none') {
        if(!cur.stealthCanvas) { cur.stealthCanvas = document.createElement('canvas'); cur.stealthCanvas.className = 'stealth-canvas'; document.getElementById('s'+activeSlot).appendChild(cur.stealthCanvas); }
        fillStealth(cur.stealthCanvas);
        cancelAnimationFrame(stealthRAF); stealthRAF = null;
        if(C.stealthMode === 'polar' || C.stealthMode === 'fog') loopStealth();
    } else {
        if(cur.stealthCanvas) { cur.stealthCanvas.remove(); cur.stealthCanvas = null; }
        cancelAnimationFrame(stealthRAF); stealthRAF = null;
    }
}

function fillStealth(cvs) {
    const ctx = cvs.getContext('2d'); cvs.width = window.innerWidth; cvs.height = window.innerHeight;
    ctx.fillStyle = C.stealthMode === 'fog' ? '#ffffff' : '#050508'; ctx.fillRect(0,0,cvs.width, cvs.height);
}

function loopStealth() {
    if(!cur || !cur.stealthCanvas || C.stealthMode === 'none' || C.stealthMode === 'scratch') return;
    stealthRAF = requestAnimationFrame(loopStealth);
    const ctx = cur.stealthCanvas.getContext('2d'); ctx.globalCompositeOperation = 'source-over';
    if (C.stealthMode === 'polar') { ctx.fillStyle = 'rgba(5,5,8,0.08)'; ctx.fillRect(0,0,cur.stealthCanvas.width, cur.stealthCanvas.height); } 
    else if (C.stealthMode === 'fog') { let speed = C.stealthIntensity / 1000; ctx.fillStyle = `rgba(255,255,255,${speed})`; ctx.fillRect(0,0,cur.stealthCanvas.width, cur.stealthCanvas.height); }
}

function showVisualFlash(emoji, color) {
    let flash = document.createElement('div');
    flash.style.cssText = `position:fixed;inset:0;background:${color};z-index:999999;display:flex;align-items:center;justify-content:center;font-size:120px;pointer-events:none;transition:opacity 0.4s ease-out;opacity:1;text-shadow:0 0 30px rgba(0,0,0,0.8);`;
    flash.innerHTML = emoji; document.body.appendChild(flash); flash.offsetHeight;
    setTimeout(() => { flash.style.opacity = '0'; setTimeout(() => flash.remove(), 400); }, 300);
}

let hideUITimer = null;
function resetUI() { 
    document.body.classList.remove('ui-hidden'); 
    clearTimeout(hideUITimer); 
    hideUITimer = setTimeout(() => { 
        if (!navOpen && !anyPanel() && !isLocked && !quickFxOpen) { document.body.classList.add('ui-hidden'); }
    }, 3000); 
}
window.addEventListener('mousemove', resetUI); window.addEventListener('touchstart', resetUI); window.addEventListener('keydown', resetUI); 
resetUI();

let pScale = 1, pInitDist = 0;

(function() {
    const kp = document.getElementById('keypad');
    if (!kp) return;
    [1,2,3,4,5,6,7,8,9,'⌫',0,'↵'].forEach(k => {
        const b = document.createElement('div'); b.className = 'k'; b.textContent = k;
        b.onclick = (e) => {
            e.preventDefault();
            if (loginDone) return;
            if (k === '↵') {
                if (pin === ACCESS_PIN || pin === VAULT_PIN) { 
                    loginDone = true; inVaultMode = (pin === VAULT_PIN); badPinCount = 0;
                    document.getElementById('login').style.display = 'none'; checkModeAndBoot(); 
                } else { 
                    pin = ''; const errEl = document.getElementById('pin-err'); errEl.textContent = 'Code incorrect'; 
                    badPinCount++; if(badPinCount >= 3) { post('/api/alert_intrusion', {}).catch(()=>{}); badPinCount = 0; }
                    setTimeout(() => { if(errEl) errEl.innerHTML = '&nbsp;'; }, 1300); 
                }
            } else if (k === '⌫') { pin = pin.slice(0, -1); } 
            else if (pin.length < 4) { pin += k; }
            const disp = document.getElementById('pin-display');
            if(disp) disp.textContent = '•'.repeat(pin.length) || '••••';
        }; 
        kp.appendChild(b);
    });
})();

function searchByPicker(hex) { 
    let r = parseInt(hex.substring(1,3), 16), g = parseInt(hex.substring(3,5), 16), b = parseInt(hex.substring(5,7), 16);
    searchByColor(`${r},${g},${b}`, hex); 
}

function searchByColor(rgbStr, label) { C.colorFilter = rgbStr; document.getElementById('color-filter-label').textContent = label; toast("🎨 Filtre : " + label); closePanel('panel-filter'); refillAndNext(); }
function clearColorFilter() { C.colorFilter = ''; document.getElementById('color-filter-label').textContent = 'Aucune'; toast("Filtre retiré"); refillAndNext(); }
function changeCat(val) { C.mode = val; refillAndNext(); }

function selectMode(m, isBoot=false) {
    appMode = m; sessionStorage.setItem('app_mode', m); 
    document.getElementById('mode-overlay').style.display = 'none'; 
    C.hardcore = (m === 'infected'); dynamicVirusRate = C.virusRate; 
    galleryMode = (m === 'gallery');   // galerie pure : pas d'usure, pas d'infection, aléatoire

    if (galleryMode) {
        C.sort = 'random';
        let ss = document.getElementById('sel-sort'); if (ss) ss.value = 'random';
        // Masque le HUD de stabilité : inutile en galerie
        let sh = document.getElementById('stability-hud'); if (sh) sh.style.display = 'none';
    } else {
        let sh = document.getElementById('stability-hud'); if (sh) sh.style.display = '';
    }
    document.body.classList.toggle('gallery-mode', galleryMode);
    updateModeBadge();

    document.getElementById('sel-mode').value = m; ssOn = false; 
    if (C.showStars) document.getElementById('stars').classList.add('on'); 
    document.getElementById('nb-ss').classList.toggle('on', ssOn); document.getElementById('ssbadge').classList.toggle('on', ssOn);
    if (!isBoot) { document.getElementById('stage').style.opacity = '1'; boot(); }
}

function updateModeBadge() {
    let b = document.getElementById('mode-badge');
    if (!b) return;
    if (galleryMode) { b.textContent = '🖼️ GALERIE'; b.style.display = 'block'; }
    else { b.style.display = 'none'; }
}

function checkModeAndBoot() { 
    let saved = sessionStorage.getItem('app_mode'); 
    if (!saved) { document.getElementById('mode-overlay').style.display = 'flex'; } else { selectMode(saved, false); }
}

function boot() { 
    if(inVaultMode) toast("🔐 COFFRE-FORT ACTIF", 3000);
    post('/api/ping_time', {ping_seconds:0}).then(d => {
        if (d.locked) showLockdownScreen();
        else {
            const h = new Date().getHours(), isNight = h === 23 || h < 6;
            if (isNight && d.quota !== undefined && d.quota < 2700) toast(`🌙 QUOTA NOCTURNE : ${Math.round(d.quota/60)} min disponibles (23h–6h)`, 5000);
        }
    }).catch(() => {});
    
    if (!hasBooted) { 
        fetch('/api/stats').then(r=>r.json()).then(showStats).catch(()=>{}); 
        fetch('/api/audio').then(r=>r.json()).then(loadAudioList).catch(()=>{}); 
        fetchNames(); setupTouch(); setupUnlockPad(); loadFaceApi(); loadConfig();
        document.addEventListener('keydown', handleKey); 
        setInterval(() => { if (!isRefilling && (bufs[C.mode]||[]).length < 40) refill(C.mode); }, 15000); 
        history.pushState(null, null, location.href); history.pushState(null, null, location.href); 
        window.addEventListener('popstate', function(e) { history.pushState(null, null, location.href); if (!isLocked) { toast('⚠️ KIOSQUE ACTIVÉ', 2000); toggleLockSS(); } else { toast('🔒 KIOSQUE', 1000); } }); 
        hasBooted = true; 
    }
    
    refillAndNext(); 
    if (localStorage.getItem('sonic_kiosk') === 'true') { setTimeout(() => { if (!isLocked) toggleLockSS(); }, 800); }
}

function logout() { 
    post('/api/secure_backup', {}).catch(()=>{});
    closeAllPanels(); closeNav(); loginDone = false; inVaultMode = false; pin = ''; badPinCount = 0; savedInfectionCount = 0; quickFxOpen = false;
    document.getElementById('quick-fx-hud').classList.remove('on'); document.getElementById('quick-fx-btn').classList.remove('active');
    document.getElementById('pin-display').textContent = '••••'; document.getElementById('login').style.display = 'flex'; 
    if (smearRAF) { cancelAnimationFrame(smearRAF); smearRAF = null; } if (stealthRAF) { cancelAnimationFrame(stealthRAF); stealthRAF = null; } if (fxRAF) { cancelAnimationFrame(fxRAF); fxRAF = null; }
    if (cur && cur.video && cur.el) cur.el.pause(); 
    const sa = document.getElementById('sa'), sb = document.getElementById('sb'); sa.innerHTML = ''; sa.className = 'slot'; sb.innerHTML = ''; sb.className = 'slot'; 
    cur = null; activeSlot = 'a'; navH = []; navI = -1; bufs = {all:[], fav:[], image:[], video:[], hist:[], suggest:[]}; 
    stopProg(); clearTimeout(ssTimer);
}

async function toggleLockSS() { 
    closeNav(); 
    if (!isLocked) { 
        isLocked = true; lockTaps = 0; localStorage.setItem('sonic_kiosk', 'true'); 
        document.getElementById('lock-overlay').classList.add('on'); document.getElementById('nb-ss-lock').classList.add('on'); document.body.classList.add('immersive'); 
        if (cur && cur.video && cur.el) cur.el.controls = false; 
        toast('🔒 KIOSQUE ACTIF. 7 taps pour déverrouiller.', 4000); 
        if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(()=>{}); 
        try { wakeLock = await navigator.wakeLock.request('screen'); } catch(e) {} 
        if (cur && cur.video) cur.el.play().catch(()=>{}); 
        if (!ssOn) toggleSS(); 
    } 
}

function setupUnlockPad() {
    const p = document.getElementById('unlock-keys');
    [1,2,3,4,5,6,7,8,9,'⌫',0,'↵'].forEach(k => {
        let b = document.createElement('div'); b.className = 'k'; b.textContent = k;
        b.onclick = () => {
            if(k === '⌫') { upin = upin.slice(0,-1); } 
            else if(k === '↵') {
                if(upin === ACCESS_PIN || upin === VAULT_PIN) { 
                    let isV = (upin === VAULT_PIN); badPinCount = 0; hideUnlockPad(); unlockSS(); 
                    if(inVaultMode !== isV) { inVaultMode = isV; toast(inVaultMode ? "🔐 COFFRE-FORT ACTIF" : "🔓 GALERIE NORMALE", 2000); bufs[C.mode] = []; refillAndNext(); } 
                } else { 
                    upin = ''; toast("❌ PIN INCORRECT"); badPinCount++; 
                    if(badPinCount >= 3) { post('/api/alert_intrusion', {}).catch(()=>{}); badPinCount=0; } 
                }
            } else if(upin.length < 4) { upin += k; }
            document.getElementById('upin-disp').textContent = '•'.repeat(upin.length) || '••••';
        }; 
        p.appendChild(b);
    });
}

function showUnlockPad(title="DÉVERROUILLAGE") { upin = ''; document.getElementById('upin-disp').textContent = '••••'; document.getElementById('unlock-title').textContent = title; document.getElementById('unlock-pad').style.display = 'flex'; }
function hideUnlockPad() { document.getElementById('unlock-pad').style.display = 'none'; }
function unlockSS() { 
    isLocked = false; lockTaps = 0; localStorage.setItem('sonic_kiosk', 'false'); 
    document.getElementById('lock-overlay').classList.remove('on'); document.getElementById('nb-ss-lock').classList.remove('on'); document.body.classList.remove('immersive'); 
    if (cur && cur.video && cur.el) cur.el.controls = true; toast('🔓 DÉVERROUILLÉ'); 
    if (wakeLock) wakeLock.release().then(() => { wakeLock=null; }); 
    if (ssOn) toggleSS(); 
}

function makeEl(item) {
    if (!item || item.el) return;
    item.error = false; 
    const onErr = () => { console.error("Erreur de décodage:", item.file); item.error = true; };
    if (item.video) { 
        const v = document.createElement('video'); v.src = item.file; v.muted = true; v.preload = 'metadata'; v.setAttribute('playsinline', ''); v.setAttribute('webkit-playsinline', ''); v.onerror = onErr; item.el = v; 
    } else { 
        const img = document.createElement('img'); img.src = item.file; img.decoding = 'async'; img.onerror = onErr; img.className = 'kb'; item.el = img; 
    }
}

function toggleImmersive() { document.body.classList.toggle('immersive'); if(cur && cur.video && cur.el && !isLocked) { cur.el.controls = !document.body.classList.contains('immersive'); } }

async function refill(mode) { 
    if ((bufs[mode]||[]).length > 999999) return; 
    try { 
        let url = `/api/batch?mode=${mode}&sort=${C.sort}&minr=${C.minRat}&vault=${inVaultMode}&demo=${C.demoFilter}`; 
        if (C.colorFilter) url += `&color=${encodeURIComponent(C.colorFilter)}`; 
        const r = await fetch(url); const d = await r.json(); 
        d.forEach(it => { if (!galleryMode && C.hardcore) { if (!it.infected) it.infected = (Math.random() < dynamicVirusRate); } it.saved = false; }); 
        bufs[mode] = [...(bufs[mode]||[]), ...d]; 
    } catch(e) {} 
}

function refillAndNext() { 
    bufs[C.mode] = []; isRefilling = true; 
    refill(C.mode).then(() => { 
        isRefilling = false; 
        if((bufs[C.mode]||[]).length > 0) { document.getElementById('empty-gallery-msg').style.display = 'none'; isTransitioning = false; next(); } 
        else { 
            document.getElementById('empty-gallery-msg').style.display = 'flex'; document.getElementById('hud-name').textContent = "⚠️ AUCUN FICHIER"; 
            if (C.colorFilter !== '') { toast(`❌ Aucun filtre. Retiré.`); clearColorFilter(); } 
            else { toast(inVaultMode ? "❌ Coffre-Fort vide." : "❌ Rien trouvé."); if (C.mode !== 'all') { C.mode = 'all'; document.getElementById('sel-cat').value = 'all'; refillAndNext(); } } 
        } 
    }); 
}

function incrementView(item, amount) { 
    post('/api/view', {file:item.file, add:amount}).then(d => { 
        if(d.views !== undefined) { 
            item.views = d.views; 
            if(cur === item) {
                updateHUD(); 
                updateStability();
            }
        } 
    }).catch(()=>{}); 
}

function show(item) {
    if (item.applyVaultMask === undefined) { item.applyVaultMask = Math.random() < 0.2; }
    pScale = 1; 
    if (smearRAF) { cancelAnimationFrame(smearRAF); smearRAF = null; } if (stealthRAF) { cancelAnimationFrame(stealthRAF); stealthRAF = null; } if (fxRAF) { cancelAnimationFrame(fxRAF); fxRAF = null; }
    // Dette de temps DÉSACTIVÉE : plus de marquage automatique des médias.
    
    clearTimeout(ssTimer); ssTimer = null; 
    if (viewInterval) { clearInterval(viewInterval); viewInterval = null; }
    
    if (!burnMode) { post('/api/hist', {file:item.file}).catch(()=>{}); }
    
    if (item.error) { isTransitioning = false; setTimeout(next, 50); return; }
  
    const ns = activeSlot === 'a' ? 'b' : 'a';
    const cEl = document.getElementById('s' + activeSlot), nEl = document.getElementById('s' + ns);
    nEl.innerHTML = ''; nEl.className = 'slot'; 
    const transClass = C.trans === 'rnd' ? 't-' + TRANS[Math.floor(Math.random()*TRANS.length)] : (C.trans === 'fade' ? null : 't-'+C.trans);
    if (transClass) nEl.classList.add(transClass);
    item.el.style.transform = 'scale(1)'; 
    
    nEl.appendChild(item.el); 

    // Vidéo : pas de time-smear ni de filtre. Le datamosh temps réel (loopFX) gère tout.
    item.el.style.opacity = '1';
    item.moshPrev = null; if (item.wearMosh === undefined) item.wearMosh = 0;

    // Canvas time-smear (z-index 2, derrière la vidéo) : trace fantôme pour les vidéos
    if (item.video) {
        item.smearCanvas = document.createElement('canvas');
        item.smearCanvas.className = 'smear-canvas';
        nEl.appendChild(item.smearCanvas);
    } else {
        item.smearCanvas = null;
    }
    item.fxCanvas = document.createElement('canvas'); item.fxCanvas.className = 'fx-canvas'; nEl.appendChild(item.fxCanvas);
    let canvas = document.createElement('canvas'); canvas.className = 'mask-canvas'; nEl.appendChild(canvas); item.maskCanvas = canvas;
    item.lastFaces = []; item.customBoxes = item.customBoxes || [];

    nEl.classList.add('on'); cEl.classList.remove('on'); 
    setTimeout(() => { 
        const old = cEl.querySelector('video'); 
        // On garde le src (pause seulement) pour permettre le RETOUR ARRIÈRE et ré-agresser le média
        if (old) { old.onended = null; old.pause(); } 
        cEl.innerHTML = ''; cEl.className = 'slot'; 
    }, 280); 
    
    activeSlot = ns; cur = item; lastShowTime = Date.now(); 
    item._viewStartTime = Date.now();  // pour mesurer la durée de visite (-> agression sur sortie)
    bumpSessionCount();
    if (document.body.classList.contains('slideshow-on')) scheduleSlide();
    let io = document.getElementById('info-overlay'); if (io) io.style.display = 'none';
    
    applyStealthCanvas(); loopFX();
    // Time-smear : trace fantôme temps réel sur les vidéos (si activé et aucun FX manuel)
    if (item.video && C.timeSmear) loopSmear();

    if (!burnMode) { incrementView(item, 1); viewInterval = setInterval(() => incrementView(item, 1), 1000); }

    const bgAud = document.getElementById('bg-audio');
    if (item.video) {
        if(bgMusicPlaying) bgAud.muted = true; 
        item.el.muted = false; item.el.controls = (!document.body.classList.contains('immersive') && !isLocked); 
        item.el.loop = false; item.el.playbackRate = 1.0; 
        item.el.onended = () => { 
            if (ssOn) next(); 
            else if (C.vidLoop) { 
                item.el.currentTime = 0; 
                item.el.play().then(() => { item.el.playbackRate = Math.max(0.1, item.el.playbackRate * 0.9); }).catch(()=>{}); 
            } 
        };
        let playPromise = item.el.play(); 
        if (playPromise !== undefined) { playPromise.catch(e => { item.el.muted = true; item.el.play().catch(()=>{}); }); }
    } else {
        if(bgMusicPlaying) bgAud.muted = false; 
    }
  
    updateHUD();
    updateStability();
    document.getElementById('stage').style.opacity = '1'; 
    if (ssOn) { 
        if (item.video) { 
            if (item.el.readyState >= 1) { if (C.showProg) startProg(item.el.duration); } 
            else { item.el.addEventListener('loadedmetadata', () => { if (ssOn && cur===item && C.showProg) startProg(item.el.duration); }, {once:true}); } 
        } else { ssTimer = setTimeout(next, C.ssDur * 1000); if (C.showProg) startProg(C.ssDur); } 
    } else if (!ssOn) { stopProg(); } 
}

// ============================================================
// === FONCTIONNALITÉS BONUS ===
// ============================================================

// --- 1) DIAPORAMA AUTO (lecture mains-libres) ---
let slideshowTimer = null;
let slideshowDelay = 5000; // ms entre deux médias (images). Vidéos : on attend la fin.
function toggleSlideshow() {
    if (slideshowTimer) { stopSlideshow(); }
    else { startSlideshow(); }
}
function startSlideshow() {
    stopSlideshow();
    document.body.classList.add('slideshow-on');
    toast('▶️ Diaporama lancé', 1500);
    scheduleSlide();
}
function stopSlideshow() {
    if (slideshowTimer) { clearTimeout(slideshowTimer); slideshowTimer = null; }
    document.body.classList.remove('slideshow-on');
}
function scheduleSlide() {
    if (slideshowTimer) clearTimeout(slideshowTimer);
    if (!document.body.classList.contains('slideshow-on')) return;
    // Vidéo : avance à la fin de la lecture (géré par l'event 'ended' dans makeEl si présent),
    // sinon on programme un délai standard.
    if (cur && cur.video && cur.el && !cur.el.ended && cur.el.duration) {
        let remaining = Math.max(1000, (cur.el.duration - cur.el.currentTime) * 1000 + 300);
        slideshowTimer = setTimeout(() => { next(); }, remaining);
    } else {
        slideshowTimer = setTimeout(() => { next(); }, slideshowDelay);
    }
}
function setSlideshowDelay(sec) {
    slideshowDelay = Math.max(1000, sec * 1000);
    toast(`⏱️ Diaporama : ${sec}s`, 1200);
    if (slideshowTimer) scheduleSlide();
}

// --- 2) PLEIN ÉCRAN ---
function toggleFullscreen() {
    if (!document.fullscreenElement) {
        (document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen || (()=>{})).call(document.documentElement);
        toast('⛶ Plein écran', 1000);
    } else {
        (document.exitFullscreen || document.webkitExitFullscreen || (()=>{})).call(document);
    }
}

// --- 3) RACCOURCIS CLAVIER ---
document.addEventListener('keydown', (e) => {
    if (!loginDone) return;
    let tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    switch (e.key) {
        case 'ArrowRight': case ' ': e.preventDefault(); next(); break;
        case 'ArrowLeft': prev(); break;
        case 'f': case 'F': toggleFullscreen(); break;
        case 's': case 'S': toggleSlideshow(); break;
        case 'l': case 'L': if (typeof toggleLike === 'function' && cur) toggleLike(); break;
        case 'i': case 'I': toggleInfoOverlay(); break;
        case 'Escape': stopSlideshow(); break;
        default:
            if (e.key >= '1' && e.key <= '5' && typeof rate === 'function') rate(parseInt(e.key));
    }
});

// --- 4) COMPTEUR DE SESSION (médias vus) ---
let sessionCount = 0;
function bumpSessionCount() {
    sessionCount++;
    let el = document.getElementById('session-counter');
    if (el) el.textContent = '👁 ' + sessionCount;
}

// --- 5) PANNEAU INFO MÉDIA (overlay rapide) ---
function toggleInfoOverlay() {
    let ov = document.getElementById('info-overlay');
    if (!ov || !cur) return;
    if (ov.style.display === 'flex') { ov.style.display = 'none'; return; }
    let parts = [];
    parts.push(`<b>${(cur.file||'').split('/').pop()}</b>`);
    parts.push(`Type : ${cur.video ? 'Vidéo' : 'Image'}`);
    if (cur.views !== undefined) parts.push(`Vues : ${cur.views}`);
    if (cur.rating) parts.push(`Note : ${'★'.repeat(cur.rating)}`);
    if (cur.liked) parts.push(`❤️ Favori`);
    if (cur.tags && cur.tags.length) parts.push(`Tags : ${cur.tags.join(', ')}`);
    ov.innerHTML = parts.join('<br>');
    ov.style.display = 'flex';
}

// Inscription BINAIRE de la dégradation sur le fichier (déclenchée à la sortie du média)
// Chaque visite > 2 s = une passe minime cumulative sur le disque.
function triggerWearDamage(item) {
    if (galleryMode) return;              // GALERIE : aucune dégradation
    if (!item || !item.file) return;
    if (burnMode) return;                 // mode burn = on ne touche pas le disque
    if (item.liked || item.rating === 5) return;  // favori / 5★ protègent
    if (!item._viewStartTime) return;
    const dur = Date.now() - item._viewStartTime;
    if (dur < 2000) return;               // visite trop courte (swipe rapide) = pas d'agression
    item._viewStartTime = 0;              // évite le double-déclenchement
    // L'intensité suit la stabilité réelle : média instable = dégradation forte ;
    // média sain (favori/bonne note) = wearRatio bas -> le serveur restaure depuis la sauvegarde.
    let wr = (typeof item.wearRatio === 'number') ? item.wearRatio : 0.5;
    post('/api/degrade_live', { file: item.file, wear_ratio: wr }).then(res => {
        // Pour les images, on recharge la <img> pour visualiser la generation loss
        if (res && res.ok && !item.video && item.el) {
            const refreshed = item.file + '?rnd=' + Date.now();
            // On remplace src même si l'item n'est plus à l'écran : la prochaine vue verra l'état dégradé
            try {
                item.el.src = refreshed;
                item._fxDone = false;
            } catch(e) {}
        }
    }).catch(()=>{});
}

function next() { 
    if (isTransitioning) return;
    isTransitioning = true;
    setTimeout(() => { isTransitioning = false; }, 300);

    // AGRESSION du média qu'on quitte (image OU vidéo) : passe binaire cumulative
    if (cur) triggerWearDamage(cur);

    if (lastShowTime > 0) { 
        let dt = Date.now() - lastShowTime; 
        if (dt < 2000) dynamicVirusRate += 0.01; 
        else if (dt > 8000) dynamicVirusRate = Math.max(C.virusRate, dynamicVirusRate - 0.01); 
    }

    // NOTE: plus de suppression/condamnation automatique au passage (dette de temps désactivée).
    // Le média reste accessible -> on peut revenir en arrière pour le ré-agresser.
    if (appMode === 'infected' && C.hardcore && cur && cur.infected && !cur.disinfected) { 
        cur.disinfected = true; let count = Math.random() < 0.15 ? 10 : 3; pendingSacrifices += count; 
        toast(`☢️ Infection ! ${count} médias marqués.`, 3000); 
    } 

    // 1) Avancer dans l'historique s'il y a déjà un média « devant »
    if (navI < navH.length - 1) {
        navI++;
        let item = navH[navI];
        makeEl(item);
        if (navI + 1 < navH.length) makeEl(navH[navI + 1]);
        show(item);
        return;
    }

    // 2) Sinon, tirer un nouveau média du buffer
    const buf = bufs[C.mode] || []; 
    if (!buf.length) { 
        if(isRefilling) { isTransitioning = false; return; }
        isRefilling = true; 
        refill(C.mode).then(() => { 
            isRefilling = false; isTransitioning = false; 
            if ((bufs[C.mode] || []).length > 0) { document.getElementById('empty-gallery-msg').style.display = 'none'; setTimeout(next, 50); }
            else { 
                document.getElementById('empty-gallery-msg').style.display = 'flex';
                if (C.colorFilter) { toast("Fin. Filtre retiré."); clearColorFilter(); } 
                else if (C.mode !== 'all') { toast("Fin. Retour Tout."); C.mode = 'all'; document.getElementById('sel-cat').value = 'all'; refillAndNext(); } 
            } 
        }); 
        return; 
    } else { document.getElementById('empty-gallery-msg').style.display = 'none'; }
    
    let item = buf.shift(); makeEl(item); if (buf.length > 0) makeEl(buf[0]); 
    navH.push(item); 
    // Borne mémoire : on libère les très anciens éléments
    if (navH.length > 200) { 
        let old = navH.shift(); 
        if (old && old.el) { try { if (old.video) { old.el.pause(); old.el.removeAttribute('src'); old.el.load(); } } catch(e){} old.el = null; }
        navI = Math.max(0, navI - 1); 
    }
    navI = navH.length - 1; 
    show(item); 
    if (buf.length < 20 && !isRefilling) refill(C.mode); 
}

function prev() {
    if (isTransitioning) return;
    if (navI <= 0) { toast('⏮ Début de la session', 1200); return; }
    isTransitioning = true;
    setTimeout(() => { isTransitioning = false; }, 300);
    if (cur) triggerWearDamage(cur);   // sortie -> passe binaire
    navI--;
    let item = navH[navI];
    makeEl(item);
    show(item);
}

function updateHUD() { 
    if (!cur) { document.getElementById('hud-name').textContent = "⚠️ RECHERCHE..."; return; } 
    let text = `👁 ${cur.views || 0}`; 
    if (cur.markedForDeath) text += ` | 💀 SACRIFIÉ APRÈS LECTURE`; 
    else if (C.hardcore && cur.infected && !cur.disinfected) text += ` | ☢️ INFECTÉ (Appui: Antidote)`; 
    document.getElementById('hud-name').textContent = text + `  ·  ${cur.file.split('/').pop().slice(0,35)}`; 
    renderStars(cur.rating || 0); document.getElementById('stars').classList.toggle('on', C.showStars); 
    
    // MAJ Panel Info
    document.getElementById('info-fname').textContent = cur.file.split('/').pop();
    document.getElementById('info-meta').innerHTML = `Taille: <b>${formatBytes(cur.size)}</b><br>Créé le: <b>${formatDate(cur.ctime)}</b>`;
}

function drawPuzzleVideo() {
    if (!antidoteActive || !cur || !cur.video || !cur.el) return;
    puzzleVideoPieces.forEach(p => { if(p.v_el && p.v_el.readyState >= 2) { p.ctx.drawImage(p.v_el, p.sx, p.sy, p.sw, p.sh, 0, 0, p.sw, p.sh); } });
    if(antidoteActive) requestAnimationFrame(drawPuzzleVideo);
}

function initPuzzle(item, isAntidote=false) {
    if(!isAntidote) return;
    puzzleVideoPieces = [];
    const wrap = document.getElementById('antidote-board'); wrap.innerHTML = ''; let selPiece = null;
    const c = 5, r = 5; wrap.style.gridTemplateColumns = `repeat(${c}, 1fr)`; wrap.style.gridTemplateRows = `repeat(${r}, 1fr)`;
    let ar = 1; if(item.video && item.el.videoWidth) ar = item.el.videoWidth / item.el.videoHeight; else if(!item.video && item.el.naturalWidth) ar = item.el.naturalWidth / item.el.naturalHeight;
    wrap.style.aspectRatio = ar; if (ar > 1) { wrap.style.width = '100%'; wrap.style.height = 'auto'; } else { wrap.style.height = '100%'; wrap.style.width = 'auto'; }
    
    let pieces = [];
    for(let y=0; y<r; y++){
        for(let x=0; x<c; x++){
            let p = document.createElement('div'); p.className = 'puzzle-piece'; p.dataset.idx = `${x}-${y}`;
            let content;
            if (item.video) {
                let vw = item.el.videoWidth || 640, vh = item.el.videoHeight || 360, pw = vw / c, ph = vh / r;
                content = document.createElement('canvas'); content.width = pw; content.height = ph; content.className = 'puzzle-content'; content.style.width = '100%'; content.style.height = '100%';
                let vClone = item.el.cloneNode(); vClone.muted = true; vClone.loop = true; let pieceIndex = y * c + x;
                vClone.currentTime = Math.max(0, item.el.currentTime - (pieceIndex * 1.0)); vClone.play().catch(()=>{});
                puzzleVideoPieces.push({ ctx: content.getContext('2d'), sx: x * pw, sy: y * ph, sw: pw, sh: ph, v_el: vClone });
            } else {
                content = item.el.cloneNode(true); content.className = 'puzzle-content'; content.style.width = `${c * 100}%`; content.style.height = `${r * 100}%`; content.style.transform = `translate(-${(x/c)*100}%, -${(y/r)*100}%)`;
            }
            p.appendChild(content);
            p.onclick = () => {
                if(!selPiece) { selPiece = p; p.classList.add('selected'); } 
                else if(selPiece === p) { selPiece = null; p.classList.remove('selected'); } 
                else {
                    let sibling = p.nextSibling, parent = p.parentNode, selSibling = selPiece.nextSibling;
                    if(selSibling === p) parent.insertBefore(p, selPiece); 
                    else if(sibling === selPiece) parent.insertBefore(selPiece, p); 
                    else { parent.insertBefore(selPiece, sibling); parent.insertBefore(p, selSibling); }
                    selPiece.classList.remove('selected'); selPiece = null; checkAntidoteWin();
                }
            }; 
            pieces.push(p);
        }
    }
    pieces.sort(() => Math.random() - 0.5); pieces.forEach(p => wrap.appendChild(p)); if(item.video) drawPuzzleVideo();
}

function startAntidotePuzzle(item) {
    if(antidoteActive || !item) return;
    antidoteActive = true; document.getElementById('antidote-overlay').style.display = 'flex'; initPuzzle(item, true);
    let timeRemaining = 15.0; const timerDisplay = document.getElementById('antidote-timer'); timerDisplay.textContent = timeRemaining.toFixed(1);
    antidoteTimer = setInterval(() => {
        timeRemaining -= 0.1; timerDisplay.textContent = timeRemaining.toFixed(1);
        if(timeRemaining <= 0) {
            clearInterval(antidoteTimer); antidoteActive = false; document.getElementById('antidote-overlay').style.display = 'none';
            toast("❌ Échec de l'Antidote ! Condamnation accélérée.", 3000); item.markedForDeath = true; next();
        }
    }, 100);
}

function checkAntidoteWin() {
    const pieces = Array.from(document.getElementById('antidote-board').children); let win = true; 
    for(let i=0; i<pieces.length; i++) { if(pieces[i].dataset.idx !== `${i % 5}-${Math.floor(i / 5)}`) { win = false; break; } } 
    if(win) { 
        clearInterval(antidoteTimer); antidoteActive = false; document.getElementById('antidote-overlay').style.display = 'none';
        toast('💉 ANTIDOTE RÉUSSI ! Le média est sauvé.', 3000); cur.infected = false; cur.disinfected = true; updateHUD(); updateStability();
    }
}

function loadAudioList(a) { 
    audioPlaylist = a || []; const s = document.getElementById('sel-music'); 
    if(audioPlaylist.length){ 
        s.innerHTML = '<option value="">Aucune</option><option value="playlist">Playlist Continue (Toutes)</option>'; 
        audioPlaylist.forEach(x => { const o = document.createElement('option'); o.value = x; o.textContent = x.split('/').pop(); s.appendChild(o); }); 
    } 
}

function setBgMusic(v) {
    if (v === 'playlist') { C.bgMusic = 'playlist'; if(bgMusicPlaying) playNextInPlaylist(); } 
    else { C.bgMusic = v; if(bgMusicPlaying && v) { document.getElementById('bg-audio').src = v; document.getElementById('bg-audio').play().catch(e=>{}); } else if (bgMusicPlaying && !v) { toggleBgMusic(); } }
}

function playNextInPlaylist() {
    if(!audioPlaylist.length) return;
    document.getElementById('bg-audio').src = audioPlaylist[currentAudioIdx]; document.getElementById('bg-audio').play().catch(e=>{});
    currentAudioIdx = (currentAudioIdx + 1) % audioPlaylist.length;
}

document.getElementById('bg-audio').addEventListener('ended', () => { if(C.bgMusic === 'playlist') playNextInPlaylist(); });

function toggleBgMusic() { 
    const aud = document.getElementById('bg-audio'); if(!C.bgMusic) return toast('Sélectionnez une musique ou la Playlist'); 
    bgMusicPlaying = !bgMusicPlaying; document.getElementById('nb-music').classList.toggle('on', bgMusicPlaying); 
    if(bgMusicPlaying){ 
        if(C.bgMusic === 'playlist' && !aud.src) { playNextInPlaylist(); } 
        else if(C.bgMusic !== 'playlist') { aud.src = C.bgMusic; aud.play().catch(e=>{}); } 
        else { aud.play().catch(e=>{}); }
        if (cur && cur.video) { aud.muted = true; cur.el.muted = false; } else { aud.muted = false; }
        toast('🎵 Musique ON'); 
    } else { aud.pause(); if (cur && cur.video) cur.el.muted = false; toast('🎵 Musique OFF'); } 
}

function renderStars(n) { document.querySelectorAll('.star').forEach(s => s.classList.toggle('on', +s.dataset.v <= n)); }

async function rate(n) { 
    if (!cur) return; const v = cur.rating === n ? 0 : n; cur.rating = v; renderStars(v); 
    await post('/api/rate', {file:cur.file, stars:v}); 
    if (appMode === 'infected' && v > 0) { cur.infected = true; pendingSacrifices += v; toast(`💀 ÉTOILES : ${v} sacrifices ajoutés à la dette !`, 2500); } 
    else if (v > 0) { pendingSacrifices += v; toast(`💀 ${v} sacrifices en attente`, 2500); } 
    else { toast('Retirée'); }
    
    // IMPACT IMMÉDIAT SUR L'USURE
    updateStability();
}

function removeFromSession(f) {
    Object.keys(bufs).forEach(k => { bufs[k] = bufs[k].filter(i => i.file !== f); });
    navH = navH.filter(i => i.file !== f);
    navI = navH.length - 1;   // forcer next() à tirer un nouveau média
}

async function swipeUpToVault() { 
    if (!cur) return; showVisualFlash('🔐', 'rgba(255, 215, 0, 0.4)');
    let f = cur.file;
    if (cur.markedForDeath) { cur.markedForDeath = false; pendingSacrifices++; }
    if (appMode === 'infected' && cur.infected) { 
        cur.infected = false; cur.disinfected = true; 
        if (bufs[C.mode] && bufs[C.mode].length > 0) { bufs[C.mode][0].infected = true; toast('☢️ Infection transférée au suivant !', 2000); } 
        else { toast('☢️ Infection neutralisée !', 2000); } 
    } 
    const r = await post('/api/vault', {file: f}); 
    if (r.vaulted) { toast('🔐 TRANSFÉRÉ AU COFFRE', 1500); if (!inVaultMode) { removeFromSession(f); cur = null; next(); } } 
    else { toast('🔓 RETIRÉ DU COFFRE', 1500); if (inVaultMode) { removeFromSession(f); cur = null; next(); } } 
}

async function toggleLike() { 
    if (!cur) return; 
    if (appMode === 'infected' && cur.infected) { if(confirm("☢️ Tenter l'antidote ? Tu as 15s pour résoudre le puzzle 5x5.")) { startAntidotePuzzle(cur); } return; }
    const r = await post('/api/like', {file:cur.file}); cur.liked = r.liked; 
    
    if (r.liked) {
        showVisualFlash('❤️', 'rgba(255, 0, 128, 0.4)');
        if (appMode === 'infected' && (cur.infected || cur.markedForDeath)) { 
            cur.infected = false; cur.markedForDeath = false; cur.disinfected = true; savedInfectionCount++; 
            let toInfect = 2 * savedInfectionCount; let infectedCount = 0;
            if (bufs[C.mode]) { for (let i = 0; i < bufs[C.mode].length && infectedCount < toInfect; i++) { if (!bufs[C.mode][i].infected) { bufs[C.mode][i].infected = true; infectedCount++; } } }
            toast(`☢️ SAUVÉ ! Mais l'infection mute vers ${infectedCount} prochains médias... (Dette: ${savedInfectionCount}x)`, 4000);
        } else if (cur.markedForDeath) { cur.markedForDeath = false; pendingSacrifices++; toast('❤️ Sauvé !', 2000); }
    } else { showVisualFlash('💔', 'rgba(100, 100, 100, 0.4)'); }
    
    updateHUD();
    
    // IMPACT IMMÉDIAT SUR L'USURE
    updateStability();
}

function doDelete() { 
    if (!cur) return; 
    showVisualFlash('🗑️', 'rgba(255, 48, 48, 0.4)'); 
    let f = cur.file, isVid = cur.video || false, isHard = cur.hardDelete || false;
    // Action explicite -> on envoie à la corbeille/purgatoire ici (plus jamais en arrière-plan via next())
    if (!burnMode) { post('/api/delete', {file: f, hard: isHard, is_video: isVid, quick_close: false}).catch(()=>{}); }
    toast(isHard ? '💀 Suppression définitive' : '🗑️ Envoyé à la corbeille');
    removeFromSession(f);
    cur = null;
    next(); 
}

function openPanel(id) { 
    closeAllPanels(); document.getElementById('panel-' + id).classList.add('on'); 
    if (id === 'info') updateHUD(); 
    if (id === 'cfg') { fetch('/api/stats').then(r=>r.json()).then(showStats).catch(()=>{}); loadConfig(); loadPurgatory(); }
    resetUI(); 
}

function showStats(d) { 
    if(!d || d.total_files === undefined) return; 
    document.getElementById('stats-wrap').innerHTML = `
        <div class="slbl">STATISTIQUES EN DIRECT</div>
        <div class="sg">
            <div class="sc"><div class="sn">${d.total_files}</div><div class="sl">Médias</div></div>
            <div class="sc"><div class="sn">${d.images}</div><div class="sl">Images</div></div>
            <div class="sc"><div class="sn">${d.videos}</div><div class="sl">Vidéos</div></div>
            <div class="sc"><div class="sn" style="color:#ffd700">${d.vault}</div><div class="sl">Coffre</div></div>
            <div class="sc"><div class="sn" style="color:#ff3030">${d.liked}</div><div class="sl">Favoris</div></div>
            <div class="sc"><div class="sn">${d.history}</div><div class="sl">Vus</div></div>
        </div>
    `; 
    if(d.total_time !== undefined) { document.getElementById('time-tracker').textContent = `Temps total: ${formatTime(d.total_time)}`; }
}

function loadPurgatory() {
    fetch('/api/purgatory').then(r=>r.json()).then(data => {
        const cont = document.getElementById('purgatory-list'); cont.innerHTML = '';
        const btnAm = document.getElementById('btn-amnesty');
        
        if(!data || data.length === 0) { 
            btnAm.style.display = 'none';
            cont.innerHTML = '<div style="color:rgba(255,255,255,0.4); font-size:12px; text-align:center;">Aucun média dans le purgatoire.</div>'; 
            return; 
        }
        
        btnAm.style.display = 'block';

        data.forEach(it => {
            let d = Math.floor(it.restore_in / 86400), h = Math.floor((it.restore_in % 86400) / 3600), m = Math.floor((it.restore_in % 3600) / 60);
            let timeStr = it.restore_in > 0 ? `${d}j ${h}h ${m}m` : 'Résurrection imminente...';

            let row = document.createElement('div'); row.style.cssText = 'display:flex; align-items:center; gap:12px; background:rgba(255,48,48,0.1); padding:10px; border-radius:12px; border:1px solid rgba(255,48,48,0.3);';

            let img = document.createElement('img'); img.src = '/t/' + it.fid; img.style.cssText = 'width:50px; height:50px; object-fit:cover; border-radius:8px; filter:saturate(4) contrast(1.4) hue-rotate(20deg) brightness(1.15); cursor:pointer;'; img.title = '⏳ ' + timeStr;
            img.onclick = () => {
                let ov = document.createElement('div'); ov.style.cssText = 'position:fixed;inset:0;z-index:9999999;background:rgba(0,0,0,0.96);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;';
                ov.onclick = () => ov.remove(); let mediaSrc = '/api/purgatory_media?fid=' + it.fid; let isVid = /\.(mp4|webm|mov|avi|mkv|m4v)\.sv2$/i.test(it.name); let mediaEl;
                if (isVid) { mediaEl = document.createElement('video'); mediaEl.src = mediaSrc; mediaEl.controls = true; mediaEl.style.cssText = 'max-width:90vw;max-height:70vh;border-radius:14px;filter:saturate(4) contrast(1.4) hue-rotate(20deg) brightness(1.15);'; } 
                else { mediaEl = document.createElement('img'); mediaEl.src = mediaSrc; mediaEl.style.cssText = 'max-width:90vw;max-height:70vh;object-fit:contain;border-radius:14px;filter:saturate(4) contrast(1.4) hue-rotate(20deg) brightness(1.15);'; }
                let timeEl = document.createElement('div'); timeEl.textContent = '⏳ ' + timeStr; timeEl.style.cssText = 'color:#ff3030;font-size:20px;font-weight:800;letter-spacing:1px;';
                let nameEl = document.createElement('div'); nameEl.textContent = it.name; nameEl.style.cssText = 'color:rgba(255,255,255,0.5);font-size:12px;';
                ov.appendChild(mediaEl); ov.appendChild(timeEl); ov.appendChild(nameEl); document.body.appendChild(ov);
            };
            img.onerror = function() { this.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><rect width="50" height="50" fill="%23222"/><text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" font-size="20">💀</text></svg>'; };

            let info = document.createElement('div'); info.style.cssText = 'flex:1; display:flex; flex-direction:column; overflow:hidden;';
            let name = document.createElement('div'); name.textContent = it.name; name.style.cssText = 'font-size:12px; font-weight:bold; color:#ff3030; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;';
            let timer = document.createElement('div'); timer.textContent = '⏳ ' + timeStr; timer.style.cssText = 'font-size:11px; font-weight:600; color:rgba(255,255,255,0.7); margin-top:4px;';
            info.appendChild(name); info.appendChild(timer); row.appendChild(img); row.appendChild(info);

            // Bouton Ressusciter
            let btnRes = document.createElement('button');
            btnRes.textContent = "👼"; btnRes.title = "Ressusciter maintenant";
            btnRes.style.cssText = 'background:none; border:none; font-size:20px; cursor:pointer; margin-left:5px; transition:transform 0.2s;';
            btnRes.onmousedown = () => btnRes.style.transform = "scale(0.8)";
            btnRes.onclick = () => {
                if(confirm('Ressusciter ce média immédiatement ?')) {
                    post('/api/purgatory_force_restore', {fid: it.fid}).then(res => {
                        if(res.ok) { toast('👼 Résurrection accomplie !'); loadPurgatory(); refillAndNext(); }
                        else toast('Erreur: ' + res.err);
                    });
                }
            };
            row.appendChild(btnRes);

            // Bouton Exécuter (Hard Delete)
            let btnExec = document.createElement('button');
            btnExec.textContent = "💀"; btnExec.title = "Exécuter (Supprimer définitivement)";
            btnExec.style.cssText = 'background:rgba(255,0,0,0.2); border:1px solid red; border-radius:8px; font-size:16px; cursor:pointer; padding:4px 8px; margin-left:10px; transition:background 0.2s;';
            btnExec.onmousedown = () => btnExec.style.background = "rgba(255,0,0,0.5)";
            btnExec.onclick = () => {
                if(confirm('⚠️ ATTENTION ⚠️\nVoulez-vous SUPPRIMER DÉFINITIVEMENT ce média de la machine ? (Irréversible)')) {
                    post('/api/purgatory_execute', {fid: it.fid}).then(res => {
                        if(res.ok) { toast('💀 Exécution terminée.'); loadPurgatory(); }
                        else toast('Erreur: ' + res.err);
                    });
                }
            };
            row.appendChild(btnExec);

            cont.appendChild(row);
        });
    }).catch(e => console.error(e));
}

function purgatoryAmnesty() {
    if(confirm("🕊️ Voulez-vous vraiment gracier TOUS les médias du Purgatoire d'un coup ?")) {
        post('/api/purgatory_amnistie', {}).then(res => {
            if(res.ok) { toast(`🕊️ Amnistie générale ! ${res.count} médias sauvés.`); loadPurgatory(); refillAndNext(); }
        });
    }
}

function toggleNav() { navOpen = !navOpen; document.getElementById('nav-bar').classList.toggle('open', navOpen); document.getElementById('nav-handle').classList.toggle('active', navOpen); resetUI(); }
function closeNav() { navOpen = false; document.getElementById('nav-bar').classList.remove('open'); document.getElementById('nav-handle').classList.remove('active'); }
function openGridFromNav() { closeNav(); renderGrid(); openPanel('grid'); } 
function openCfgFromNav() { closeNav(); openPanel('cfg'); }

function toggleSS() { 
    ssOn = !ssOn; document.getElementById('ssbadge').classList.toggle('on', ssOn); document.getElementById('nb-ss').classList.toggle('on', ssOn); 
    if (ssOn) { if(cur && cur.video && cur.el) { if (C.showProg && cur.el.duration) startProg(cur.el.duration); } else { ssTimer = setTimeout(next, C.ssDur * 1000); if (C.showProg) startProg(C.ssDur); } } 
    else { clearTimeout(ssTimer); ssTimer = null; stopProg(); } 
    closeNav(); 
}

function startProg(d) { if (!C.showProg) return; const b = document.getElementById('prog'); b.style.transition='none'; b.style.width='0%'; requestAnimationFrame(()=>requestAnimationFrame(()=>{ b.style.transition=`width ${d}s linear`; b.style.width='100%'; })); }
function stopProg() { const b = document.getElementById('prog'); b.style.transition='none'; b.style.width='0%'; }

let gridItems = [], gridIndex = 0; 
const gridObserver = new IntersectionObserver(ents => { ents.forEach(ent => { if(ent.isIntersecting) { gridObserver.unobserve(ent.target); loadMoreGrid(); } }); });

function renderGrid() { gridItems = (bufs[C.mode]||[]).length ? bufs[C.mode] : bufs.all; gridIndex = 0; document.getElementById('grid-wrap').innerHTML = ''; loadMoreGrid(); }
function loadMoreGrid() { 
    const frag = document.createDocumentFragment(), chunk = gridItems.slice(gridIndex, gridIndex + 30); if(!chunk.length) return; 
    chunk.forEach(it => { 
        if(it.error) return; 
        const d = document.createElement('div'); d.className='gt'; 
        const t = document.createElement('img'); t.src = it.file.replace('/f/', '/t/'); t.loading = 'lazy'; 
        t.onerror = function() { this.onerror = null; this.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" font-size="40">⏳</text></svg>'; }; 
        d.appendChild(t); 
        const ov = document.createElement('div'); ov.className='gt-ov'; d.appendChild(ov); 
        if(it.liked) { const f=document.createElement('span'); f.className='gt-fav'; f.textContent='❤'; d.appendChild(f); } 
        if(it.video) { const v=document.createElement('span'); v.className='gt-vid'; v.textContent='🎬'; d.appendChild(v); } 
        if(it.rating) { const r=document.createElement('span'); r.className='gt-rat'; r.textContent='★'.repeat(it.rating); d.appendChild(r); } 
        d.onclick = () => { if (!it.el) makeEl(it); show(it); closePanel('panel-grid'); }; 
        frag.appendChild(d); 
    }); 
    const w = document.getElementById('grid-wrap'); w.appendChild(frag); gridIndex += 30; if(w.lastElementChild) gridObserver.observe(w.lastElementChild); 
}

function togC(key, btn) { C[key] = !C[key]; btn.classList.toggle('on', C[key]); } 
function setTheme(t) { document.documentElement.removeAttribute('data-theme'); if (t !== 'dark') document.documentElement.setAttribute('data-theme', t); }

async function fetchNames() { try { const r = await fetch('/api/all_names'); allKnownNames = await r.json(); updateNameDatalist(); } catch(e) {} }
function updateNameDatalist() { const dl = document.getElementById('known-names'); dl.innerHTML = ''; allKnownNames.forEach(n => { const opt = document.createElement('option'); opt.value = n; dl.appendChild(opt); }); }

function toggleFS() { if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(()=>{}); else document.exitFullscreen().catch(()=>{}); }

const PANELS = ['panel-grid','panel-info','panel-cfg','panel-filter'];
function closePanel(id) { document.getElementById(id).classList.remove('on'); resetUI(); } 
function closeAllPanels() { PANELS.forEach(closePanel); } 
function anyPanel() { return PANELS.some(id => document.getElementById(id).classList.contains('on')); }

function setupTouch() { 
    let sx=0, sy=0, lastTap=0; const stage = document.getElementById('stage'), ov = document.getElementById('lock-overlay');
    ov.addEventListener('touchstart', e => { 
        e.preventDefault(); if (!isLocked) return; 
        let now = Date.now(); if (now - lockTimer > 1000) lockTaps = 0; lockTimer = now; lockTaps++; 
        if (lockTaps >= 7) { lockTaps = 0; showUnlockPad(); } 
    }, { passive: false }); 
    
    stage.addEventListener('touchmove', e => { 
        if(e.touches.length === 2 && cur && cur.el) { 
            e.preventDefault(); let dist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); 
            if(pInitDist > 0) { pScale = Math.min(Math.max(1, pScale * (dist/pInitDist)), 5); cur.el.style.transform = `scale(${pScale})`; } pInitDist = dist; 
        }
        let cx = e.touches[0].clientX, cy = e.touches[0].clientY;
        if (isDrawingMask && maskDragStart && currentDragBox && cur) {
            e.preventDefault(); const rect = cur.el.getBoundingClientRect();
            let pX = (cx - rect.left) / rect.width, pY = (cy - rect.top) / rect.height;
            pX = Math.max(0, Math.min(1, pX)); pY = Math.max(0, Math.min(1, pY));
            currentDragBox.x = Math.min(maskDragStart.x, pX); currentDragBox.y = Math.min(maskDragStart.y, pY);
            currentDragBox.w = Math.abs(pX - maskDragStart.x); currentDragBox.h = Math.abs(pY - maskDragStart.y);
            return;
        }
        if(cur && cur.stealthCanvas && C.stealthMode !== 'none') {
            e.preventDefault(); const sX = cur.stealthCanvas.width / window.innerWidth, sY = cur.stealthCanvas.height / window.innerHeight;
            let radius = C.stealthMode === 'fog' ? C.stealthIntensity * 2 : C.stealthIntensity;
            const ctx = cur.stealthCanvas.getContext('2d'); ctx.globalCompositeOperation = 'destination-out'; ctx.beginPath();
            if (cur.lastTx !== undefined) { ctx.moveTo(cur.lastTx, cur.lastTy); ctx.lineTo(cx * sX, cy * sY); ctx.lineWidth = radius * 2; ctx.lineCap = 'round'; ctx.stroke(); }
            ctx.arc(cx * sX, cy * sY, radius, 0, Math.PI*2); ctx.fill();
            cur.lastTx = cx * sX; cur.lastTy = cy * sY; return; 
        }
    }, {passive:false});
    
    stage.addEventListener('touchstart', e => { 
        if(e.touches.length === 2) { pInitDist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); return; } 
        if (e.target.closest('#nav-bar, #nav-handle, #hud-name, .panel, #unlock-pad, #stars, #quick-fx-btn, #quick-fx-hud, #antidote-overlay, #stability-hud')) return; 
        if ((isDrawingMask && cur) || (cur && cur.stealthCanvas && C.stealthMode !== 'none')) { e.preventDefault(); }
        let cx = e.touches ? e.touches[0].clientX : e.clientX, cy = e.touches ? e.touches[0].clientY : e.clientY;
        if (isDrawingMask && cur) {
            const rect = cur.el.getBoundingClientRect();
            let pX = (cx - rect.left) / rect.width, pY = (cy - rect.top) / rect.height;
            maskDragStart = {x: Math.max(0, pX), y: Math.max(0, pY)}; currentDragBox = {x: maskDragStart.x, y: maskDragStart.y, w: 0, h: 0}; return;
        }
        sx = cx; sy = cy; 
    }, {passive:false}); 
    
    stage.addEventListener('touchend', e => { 
        if(e.touches && e.touches.length < 2) pInitDist = 0; if(pScale > 1.1) return;
        if(cur) { cur.lastTx = undefined; cur.lastTy = undefined; }
        if (e.target.closest('#nav-bar, #nav-handle, #hud-name, .panel, #unlock-pad, #stars, #quick-fx-btn, #quick-fx-hud, #antidote-overlay, #stability-hud')) { return; }
        
        if (isDrawingMask) {
            if (maskDragStart && currentDragBox && cur) { if (currentDragBox.w > 0.02 && currentDragBox.h > 0.02) { globalCustomBoxes.push({...currentDragBox}); } maskDragStart = null; currentDragBox = null; }
            return; 
        }

        let cx = e.changedTouches ? e.changedTouches[0].clientX : e.clientX, cy = e.changedTouches ? e.changedTouches[0].clientY : e.clientY; 
        const dx=cx-sx, dy=cy-sy, adx=Math.abs(dx), ady=Math.abs(dy); 
        let now = Date.now(); 
        
        if (now - lastTap < 300 && now - lastTap > 0 && adx < 20 && ady < 20) { 
            let w = window.innerWidth;
            if (cur && cur.video && cur.el) {
                if (cx < w * 0.3) {
                    cur.el.currentTime = Math.max(0, cur.el.currentTime - 5);
                    showVisualFlash('⏪', 'rgba(255,255,255,0.2)');
                } else if (cx > w * 0.7) {
                    cur.el.currentTime = Math.min(cur.el.duration, cur.el.currentTime + 5);
                    showVisualFlash('⏩', 'rgba(255,255,255,0.2)');
                } else {
                    toggleLike();
                }
            } else {
                toggleLike();
            }
            e.preventDefault(); lastTap = 0; return; 
        } 
        lastTap = now;
        
        if (adx<15 && ady<15) { 
            if (navOpen) { closeNav(); return; } if (quickFxOpen) { toggleQuickFX(); return; } if (anyPanel()) { closeAllPanels(); return; } 
            if (cx < window.innerWidth * 0.3) { prev(); } else if (cx > window.innerWidth * 0.7) { next(); } else toggleImmersive(); return; 
        } 
        
        if (ady > 70 && ady > adx * 1.5) { 
            if (C.stealthMode !== 'none') return; 
            dy < 0 ? swipeUpToVault() : doDelete(); 
        } else if (adx > 55 && adx > ady * 1.5) { 
            if (C.stealthMode !== 'none') return; 
            dx < 0 ? next() : prev(); 
        }

    }, {passive:false}); 
}

function handleKey(e) { 
    if (['INPUT','TEXTAREA'].includes(e.target.tagName)) return; 
    resetUI(); const k = e.key; 
    if (k==='ArrowRight'||k===' ') { e.preventDefault(); next(); } 
    else if (k==='ArrowLeft') { prev(); } 
    else if (k==='ArrowUp') swipeUpToVault(); 
    else if (k==='ArrowDown') toggleLike(); 
    else if (k==='Delete') { doDelete(); } 
    else if (k==='f'||k==='F') toggleFS(); 
    else if (k==='g'||k==='G') openGridFromNav(); 
    else if (k==='m'||k==='M') toggleNav(); 
    else if (k==='s'||k==='S') toggleSS(); 
    else if (k==='i'||k==='I') openPanel('info'); 
    else if (k>='1'&&k<='5') rate(+k); 
    else if (k==='Escape') { closeAllPanels(); closeNav(); if(quickFxOpen) toggleQuickFX(); } 
}

async function post(url, body) { 
    const r = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) }); 
    return r.json(); 
}

function toast(msg, ms=1600) { 
    const t = document.getElementById('toast'); t.textContent = msg; t.classList.add('on'); 
    clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove('on'), ms); 
}
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════
# §4 — JEU "LES TREIZE VOILES"  (données + moteur + WITCH_UI_HTML)
# ═══════════════════════════════════════════════════════════════════
# ============================================================
# === JEU "LES TREIZE VOILES" (RPG femdom à embranchements) ===
# ============================================================
# === DONNÉES DU JEU "LES TREIZE VOILES" ===
# 20 sorcières, chacune avec un RÔLE mécanique unique + un niveau de puissance.
# Réparties par palier pour empêcher de tout vaincre d'emblée.


# Chaque sorcière :
#  id, nom, niveau (palier de puissance), zone, rôle (mécanique unique),
#  tactique gagnante (le bon "contre"), volonté de combat, désc., répliques.
WITCHES = [
    # --- PALIER 1 : INITIATRICES (niv 1-3) ---
    {"id":"liane","nom":"Liane la Patiente","niveau":1,"zone":"vestibule","role":"drain",
     "counter":"resist","wcombat":3,
     "desc":"La première Voile. Elle ne presse rien. Elle attend que tu cèdes de toi-même, un fil de volonté après l'autre.",
     "intro":"« Inutile de courir. Tout le monme finit assis à mes pieds. Toi aussi, tôt ou tard. »",
     "win":"« Déjà ? ... Tu as de la nerf. Garde-la. Tu en auras besoin plus bas. »",
     "lose":"« Là. Tu vois comme c'est simple de ne plus rien décider. »"},
    {"id":"orne","nom":"Orne aux Lèvres Closes","niveau":2,"zone":"vestibule","role":"silence",
     "counter":"observe","wcombat":4,
     "desc":"Elle ne parle pas. Elle t'impose le silence et observe si tu sais lire ce qu'on ne dit pas.",
     "intro":"« ... » (Son regard te cloue sur place.)",
     "win":"Elle incline la tête, presque admirative, et s'écarte.",
     "lose":"Tes mots meurent dans ta gorge. Tu t'agenouilles sans qu'on te l'ait demandé."},
    {"id":"sere","nom":"Séré la Souriante","niveau":2,"zone":"vestibule","role":"mirror",
     "counter":"defy","wcombat":4,
     "desc":"Elle renvoie chacun de tes gestes. Te soumettre devant elle, c'est te soumettre à ton propre reflet.",
     "intro":"« Regarde-toi bien. C'est toi qui décides de plier — moi je ne fais que tenir le miroir. »",
     "win":"Le reflet se brise. Pour une fois, tu n'y ressembles pas.",
     "lose":"Tu obéis à ton reflet, et ton reflet obéit à elle."},
    {"id":"vael","nom":"Vael Pieds-Nus","niveau":3,"zone":"vestibule","role":"haste",
     "counter":"patient","wcombat":5,
     "desc":"Elle punit l'hésitation. Chaque seconde de doute renforce son emprise.",
     "intro":"« Vite. Décide. Tu hésites ? Trop tard, c'est déjà à moi. »",
     "win":"« Hmf. Réflexes corrects. On se reverra quand tu seras plus lent. »",
     "lose":"Tu as trop tardé. Le sol t'attire vers elle."},

    # --- PALIER 2 : LES VOILÉES (niv 4-8) ---
    {"id":"morgaine","nom":"Morgaine la Marchande","niveau":4,"zone":"galerie","role":"bargain",
     "counter":"refuse","wcombat":6,
     "desc":"Elle t'offre du pouvoir. Chaque don creuse ta dette d'Emprise. Refuser demande une volonté de fer.",
     "intro":"« Tu veux descendre plus bas ? Je te donne la clé. Tu ne paieras... que plus tard. »",
     "win":"« Tu refuses un cadeau ? Rare. Tu m'intéresses, mortel. »",
     "lose":"Tu prends. Tu prends toujours. Et la dette se referme sur toi."},
    {"id":"isolde","nom":"Isolde aux Chaînes Douces","niveau":4,"zone":"galerie","role":"chain",
     "counter":"break","wcombat":6,
     "desc":"Elle t'enchaîne : au prochain tour, tes choix sont réduits. Il faut briser le lien avant qu'il ne se resserre.",
     "intro":"« Ne lutte pas tout de suite. Laisse-moi d'abord t'apprendre le poids du métal. »",
     "win":"Les chaînes tombent. Elle te regarde les enjamber, lèvres pincées.",
     "lose":"Un maillon. Puis deux. Bientôt tu ne te souviens plus comment on tient debout seul."},
    {"id":"nyx","nom":"Nyx la Brouilleuse","niveau":5,"zone":"galerie","role":"fog",
     "counter":"trust","wcombat":7,
     "desc":"Elle cache les conséquences de tes choix. Tu avances à l'aveugle, en te fiant à ton instinct.",
     "intro":"« Choisis. Non, je ne te dirai pas ce que ça fait. Là est tout le plaisir. »",
     "win":"Le brouillard se dissipe. Tu avais vu juste, sans rien voir.",
     "lose":"Tu as choisi dans le noir. Le noir a choisi pour toi."},
    {"id":"calla","nom":"Calla Deux-Voix","niveau":5,"zone":"galerie","role":"twin",
     "counter":"split","wcombat":7,
     "desc":"Elle se dédouble. Tu affrontes deux Calla qui se contredisent ; il faut deviner laquelle est réelle.",
     "intro":"« Laquelle de nous deux ment ? Choisis mal et nous te garderons toutes les deux. »",
     "win":"L'illusion s'efface. La vraie Calla applaudit, lente.",
     "lose":"Tu obéis à la fausse. La vraie sourit. Maintenant tu leur appartiens."},
    {"id":"hespe","nom":"Hespé la Tisseuse","niveau":6,"zone":"galerie","role":"web",
     "counter":"cut","wcombat":8,
     "desc":"Elle tisse autour de toi une toile de promesses. Plus tu te débats, plus tu t'y prends.",
     "intro":"« Bouge encore. Chaque sursaut est un fil de plus autour de tes poignets. »",
     "win":"Tu tranches net plutôt que de te débattre. La toile s'effondre.",
     "lose":"Pris. Suspendu. Offert à sa patience."},
    {"id":"riven","nom":"Riven la Glaçante","niveau":6,"zone":"biblio","role":"freeze",
     "counter":"warm","wcombat":8,
     "desc":"Son regard fige. Tu dois trouver en toi une chaleur — colère ou désir — pour bouger encore.",
     "intro":"« Reste. Immobile. C'est tout ce que je demande. Tout ce que tu sauras bientôt faire. »",
     "win":"Quelque chose brûle en toi assez fort pour briser le givre.",
     "lose":"Tu gèles à ses pieds, statue parmi ses statues."},
    {"id":"sable","nom":"Sable l'Effaceuse","niveau":7,"zone":"biblio","role":"erase",
     "counter":"remember","wcombat":9,
     "desc":"Elle efface tes souvenirs de combat. Sans mémoire de la veille, tu répètes tes erreurs — sauf si tu t'ancres.",
     "intro":"« Qui es-tu déjà ? Bientôt même cette question disparaîtra. »",
     "win":"Tu te rappelles ton nom, et le sien. Elle recule, contrariée.",
     "lose":"Page blanche. Tu ne sais plus pourquoi tu résistais."},
    {"id":"vesper","nom":"Vesper la Dévorante","niveau":7,"zone":"biblio","role":"feast",
     "counter":"starve","wcombat":9,
     "desc":"Elle se nourrit de ta volonté dépensée. Plus tu agis fort, plus tu la rassasies.",
     "intro":"« Donne-moi tout. Frappe fort. Je n'aime rien tant qu'un repas qui se débat. »",
     "win":"Tu agis avec une économie froide. Elle reste affamée.",
     "lose":"Repue de ta rage, elle te garde pour le prochain festin."},
    {"id":"lune","nom":"Lune la Tendre","niveau":8,"zone":"biblio","role":"comfort",
     "counter":"distance","wcombat":10,
     "desc":"Elle ne menace pas. Elle réconforte, materne, et c'est ainsi qu'elle te garde. La douceur est son piège.",
     "intro":"« Tu as l'air si fatigué. Viens. Pose ta tête. Plus besoin de te battre, jamais. »",
     "win":"Tu prends tes distances avant que la chaleur ne t'endorme.",
     "lose":"Tu poses la tête. Tu ne la relèves plus."},
    {"id":"abra","nom":"Abra la Pactiseuse","niveau":8,"zone":"biblio","role":"oath",
     "counter":"halftruth","wcombat":10,
     "desc":"Elle t'arrache des serments. Chaque mot donné devient une chaîne. Il faut promettre sans se lier.",
     "intro":"« Jure. Un seul mot. Que peut bien coûter un mot ? »",
     "win":"Tu promets une chose qui ne t'engage à rien. Elle plisse les yeux.",
     "lose":"Tu as juré. Le serment te possède désormais."},

    # --- PALIER 3 : GARDIENNES (niv 9-12) ---
    {"id":"thorne","nom":"Thorne la Geôlière","niveau":9,"zone":"crypte","role":"prison",
     "counter":"key","wcombat":12,
     "desc":"Gardienne de la Crypte. Elle t'emmure dans une cellule mentale ; il te faut une clé — réelle ou volée.",
     "intro":"« Personne ne descend plus bas sans ma permission. Et je ne la donne jamais. »",
     "win":"La clé tourne. La grille s'ouvre. Elle s'incline, vaincue par sa propre serrure.",
     "lose":"Clac. La cellule se referme. Le temps n'existe plus ici."},
    {"id":"vora","nom":"Vora la Reine-Sangsue","niveau":10,"zone":"crypte","role":"drain2",
     "counter":"sever","wcombat":13,
     "desc":"Drain massif et continu. Chaque tour te coûte. Il faut couper le lien vite ou s'effondrer.",
     "intro":"« Je sens déjà ton pouls dans le mien. Donne. Donne. Donne. »",
     "win":"Tu sectionnes le lien d'un coup sec. Elle hurle, à sec.",
     "lose":"Vidé. Sec. Tu deviens une veine de plus dans son trône."},
    {"id":"morrigane","nom":"Morrigane Triple","niveau":11,"zone":"crypte","role":"phases",
     "counter":"adapt","wcombat":14,
     "desc":"Trois visages : la Jeune, la Mère, la Vieille. Le bon contre change à chaque phase. Lire et s'adapter.",
     "intro":"« Tu n'affrontes pas une sorcière. Tu en affrontes trois, dans une seule peau. »",
     "win":"Tu suis ses mues une à une. Les trois visages se figent, battus ensemble.",
     "lose":"Tu n'en lis qu'une. Les deux autres te prennent par-derrière."},
    {"id":"selka","nom":"Selka l'Inverseuse","niveau":12,"zone":"crypte","role":"invert",
     "counter":"reverse","wcombat":15,
     "desc":"Tout est inversé chez elle : résister la nourrit, céder l'affaiblit. Le contre logique est piégé.",
     "intro":"« Bats-toi. Je t'en prie, bats-toi. C'est exactement ce que je veux. »",
     "win":"Tu fais l'inverse de l'instinct. Le sol se dérobe sous ELLE.",
     "lose":"Tu as résisté, comme un bon petit. Tu l'as nourrie."},

    # --- PALIER 4 : LES TRÔNES (niv 13+) ---
    {"id":"ombre","nom":"L'Ombre sans Nom","niveau":14,"zone":"sanctum","role":"void",
     "counter":"name","wcombat":18,
     "desc":"Elle n'a pas de visage. Pour la vaincre, il faut lui donner un nom — donc avoir trouvé son secret.",
     "intro":"« Je suis ce que tu deviens quand on t'a tout pris. Bientôt, je serai toi. »",
     "win":"Tu prononces le nom oublié. L'Ombre se fendille comme un masque.",
     "lose":"Tu n'as pas de nom à lui donner. Alors elle prend le tien."},
    {"id":"reine","nom":"La Treizième Voile","niveau":16,"zone":"sanctum","role":"throne",
     "counter":"all","wcombat":22,
     "desc":"La maîtresse du Domaine. Elle combine tous les rôles. On ne la bat qu'en ayant compris toutes les autres.",
     "intro":"« Tu es venu jusqu'à mon trône. Charmant. Désormais, tu n'en repartiras qu'à genoux — ou pas. »",
     "win":"Le Domaine tremble. La Treizième Voile se déchire. Tu es libre, ou plus que libre.",
     "lose":"Le trône t'accueille — à sa base. Pour toujours."},
]

# RÔLES → libellé du bon contre (utilisé pour l'aide tactique progressive)
ROLE_COUNTER_HINT = {
    "drain":"Résister fermement coupe son flux.",
    "silence":"Observe au lieu de parler.",
    "mirror":"Défie ton reflet plutôt que de l'imiter.",
    "haste":"Garde ton calme, agis avec lenteur maîtrisée.",
    "bargain":"Refuse le marché, quel qu'en soit le prix.",
    "chain":"Brise le lien avant qu'il se referme.",
    "fog":"Fie-toi à ton instinct dans le brouillard.",
    "twin":"Sépare le vrai du faux.",
    "web":"Tranche net au lieu de te débattre.",
    "freeze":"Trouve une chaleur intérieure (colère/désir).",
    "erase":"Ancre-toi dans un souvenir précis.",
    "feast":"Agis avec économie, ne la nourris pas.",
    "comfort":"Garde tes distances malgré la douceur.",
    "oath":"Promets une demi-vérité qui ne t'engage pas.",
    "prison":"Il te faut une clé pour ouvrir sa cellule.",
    "drain2":"Sectionne le lien d'un coup, vite.",
    "phases":"Lis chaque visage et adapte-toi.",
    "invert":"Fais l'inverse de ton instinct.",
    "void":"Donne-lui le nom que tu as découvert.",
    "throne":"Mobilise tout ce que les autres t'ont appris.",
}

# Choix tactiques proposés en combat (id -> libellé visible)
TACTICS = {
    "resist":"Résister de toutes tes forces",
    "observe":"Observer en silence",
    "defy":"Défier du regard",
    "patient":"Agir avec lenteur maîtrisée",
    "refuse":"Refuser net",
    "break":"Briser le lien",
    "trust":"Suivre ton instinct",
    "split":"Démêler le vrai du faux",
    "cut":"Trancher d'un geste",
    "warm":"Puiser une chaleur intérieure",
    "remember":"T'ancrer dans un souvenir",
    "starve":"Économiser tes forces",
    "distance":"Garder tes distances",
    "halftruth":"Offrir une demi-vérité",
    "key":"Utiliser une clé",
    "sever":"Sectionner le lien",
    "adapt":"T'adapter à sa mue",
    "reverse":"Faire l'inverse de l'instinct",
    "name":"Prononcer son nom",
    "all":"Tout mobiliser",
    # leurres communs
    "submit":"Céder un peu",
    "flee":"Tenter de fuir",
    "plead":"Implorer",
    "charge":"Attaquer frontalement",
}

# ITEMS du jeu
ITEMS = {
    "key_crypt":   {"nom":"Clé de la Crypte","type":"key","desc":"Ouvre la grille de Thorne et la descente vers la Crypte."},
    "key_sanctum": {"nom":"Sceau de la Treizième","type":"key","desc":"Brise le dernier Voile, donne accès au Sanctum."},
    "eye":         {"nom":"Œil de Verre","type":"key","desc":"Révèle les chemins cachés dans chaque zone."},
    "name_shard":  {"nom":"Éclat de Nom","type":"key","desc":"Fragment du vrai nom de l'Ombre. Indispensable contre elle."},
    "philtre":     {"nom":"Philtre de Volonté","type":"potion","desc":"Restaure une partie de ta Volonté.","effect":{"will":40}},
    "ember":       {"nom":"Braise Ancienne","type":"potion","desc":"Garantit la victoire au prochain combat (usage unique).","effect":{"autowin":True}},
    "ward":        {"nom":"Talisman d'Ancrage","type":"potion","desc":"Réduit l'Emprise gagnée et protège la mémoire.","effect":{"grip":-25}},
    "tome":        {"nom":"Tome des Voiles","type":"lore","desc":"Révèle le rôle et le bon contre des sorcières que tu rencontres."},
}

# CARTE : zones -> salles. Chaque salle : connexions, sorcière éventuelle (cachée ou non),
# item éventuel à fouiller, niveau requis pour entrer dans la zone.
# 30+ salles. "hidden": sortie révélée par item/niveau. "gate": condition de passage.
MAP = {
    "vestibule": {"nom":"Le Vestibule des Voiles","minlvl":1,"color":"#3a2a4a","rooms":{
        "v_entree":  {"nom":"Le Seuil","desc":"Une porte sans serrure se referme derrière toi. Pas de retour.","exits":{"v_hall":None},"search":None},
        "v_hall":    {"nom":"Le Grand Hall","desc":"Treize voiles noirs pendent du plafond. L'un d'eux frémit.","exits":{"v_entree":None,"v_aile_o":None,"v_aile_e":None,"galerie:g_entree":{"gate":"witch:liane"}},"witch":"liane"},
        "v_aile_o":  {"nom":"L'Aile Ouest","desc":"Des portraits dont les yeux suivent. Une silhouette se tait.","exits":{"v_hall":None,"v_alcove":{"hidden":"item:eye"}},"witch":"orne"},
        "v_aile_e":  {"nom":"L'Aile Est","desc":"Un miroir haut comme deux hommes. Quelqu'un sourit dedans.","exits":{"v_hall":None},"witch":"sere","search":"philtre"},
        "v_alcove":  {"nom":"L'Alcôve Cachée","desc":"Derrière les portraits, une niche oubliée.","exits":{"v_aile_o":None,"v_oubli":None},"search":"eye","witch":"vael"},
        "v_oubli":   {"nom":"Le Réduit Poussiéreux","desc":"Un débarras oublié des Voiles. Rien ne bouge ici.","exits":{"v_alcove":None},"search":"philtre"},
    }},
    "galerie": {"nom":"La Galerie des Marchés","minlvl":3,"color":"#4a2a35","rooms":{
        "g_entree":  {"nom":"L'Entrée Marchande","desc":"Des étals de promesses. Tout a un prix d'Emprise.","exits":{"vestibule:v_hall":None,"g_nef":None,"g_loge":None},"witch":"morgaine"},
        "g_nef":     {"nom":"La Nef Suspendue","desc":"Des chaînes de soie descendent du vide.","exits":{"g_entree":None,"g_atelier":None,"g_voute":{"gate":"witch:isolde"}},"witch":"isolde"},
        "g_loge":    {"nom":"La Loge Obscure","desc":"On n'y voit pas le bout de ses propres mains.","exits":{"g_entree":None},"witch":"nyx","search":"tome"},
        "g_atelier": {"nom":"L'Atelier des Reflets","desc":"Deux femmes identiques tissent face à face.","exits":{"g_nef":None,"g_serre":{"hidden":"item:eye"}},"witch":"calla"},
        "g_voute":   {"nom":"La Voûte Tissée","desc":"Une toile immense barre le passage vers le bas.","exits":{"g_nef":None,"biblio:b_entree":{"gate":"witch:hespe"}},"witch":"hespe","search":"philtre"},
        "g_serre":   {"nom":"La Serre Gelée","desc":"Des fleurs de givre. L'air ne bouge plus.","exits":{"g_atelier":None,"g_jardin":None},"search":"ward"},
        "g_jardin":  {"nom":"Le Jardin Mort","desc":"Des ronces noires étranglent d'anciennes statues de visiteurs.","exits":{"g_serre":None,"g_puits_o":{"hidden":"item:eye"}},"search":None},
        "g_puits_o": {"nom":"Le Puits aux Offrandes","desc":"Un puits tapissé de bagues, de mèches, de promesses jetées.","exits":{"g_jardin":None},"search":"philtre"},
    }},
    "biblio": {"nom":"La Bibliothèque Noyée","minlvl":6,"color":"#1f3a44","rooms":{
        "b_entree":  {"nom":"Le Vestibule Noyé","desc":"L'eau monte aux chevilles. Les livres flottent, gonflés.","exits":{"galerie:g_voute":None,"b_rayons":None,"b_scriptorium":None},"witch":"riven"},
        "b_rayons":  {"nom":"Les Rayons Sombres","desc":"Des étagères sans fin. On oublie ce qu'on cherchait.","exits":{"b_entree":None,"b_puits":None},"witch":"sable","search":"tome"},
        "b_scriptorium":{"nom":"Le Scriptorium","desc":"Des plumes écrivent seules des serments à ta place.","exits":{"b_entree":None,"b_chaire":{"hidden":"lvl:7"}},"witch":"abra"},
        "b_puits":   {"nom":"Le Puits de Mémoire","desc":"Un trou d'eau noire. Ton reflet y a faim.","exits":{"b_rayons":None,"b_archives":None},"witch":"vesper","search":"ember"},
        "b_archives":{"nom":"Les Archives Englouties","desc":"Des registres de tous ceux qui ont cédé. Ton nom n'y est pas. Pas encore.","exits":{"b_puits":None,"b_crypte_l":{"hidden":"lvl:8"}},"search":"tome"},
        "b_crypte_l":{"nom":"La Crypte aux Lettres","desc":"Des lettres jamais envoyées, scellées de cire noire.","exits":{"b_archives":None},"search":"ward"},
        "b_chaire":  {"nom":"La Chaire Tendre","desc":"Un fauteuil trop accueillant. On voudrait ne plus se lever.","exits":{"b_scriptorium":None,"crypte:c_grille":{"gate":"witch:lune"}},"witch":"lune","search":"key_crypt"},
    }},
    "crypte": {"nom":"La Crypte des Trônes","minlvl":9,"color":"#2a2030","rooms":{
        "c_grille":  {"nom":"La Grille Scellée","desc":"Une geôlière garde l'unique descente. Sans clé, nul ne passe.","exits":{"biblio:b_chaire":None,"c_cellules":{"gate":"item:key_crypt"}},"witch":"thorne"},
        "c_cellules":{"nom":"Les Cellules Vides","desc":"Des cellules où d'anciens visiteurs murmurent encore.","exits":{"c_grille":None,"c_trone_s":None,"c_oubliette":{"hidden":"item:eye"}},"witch":"vora"},
        "c_trone_s": {"nom":"Le Trône Triple","desc":"Trois visages d'une même reine te toisent.","exits":{"c_cellules":None,"c_seuil":{"gate":"witch:morrigane"}},"witch":"morrigane","search":"philtre"},
        "c_oubliette":{"nom":"L'Oubliette","desc":"Tout y est à l'envers. Le haut est en bas.","exits":{"c_cellules":None,"c_ossuaire":None},"witch":"selka","search":"ward"},
        "c_ossuaire":{"nom":"L'Ossuaire des Volontés","desc":"Des volontés brisées, empilées comme des os blanchis.","exits":{"c_oubliette":None,"c_reliquaire":{"hidden":"item:eye"}},"search":"philtre"},
        "c_reliquaire":{"nom":"Le Reliquaire Scellé","desc":"Une châsse contient un éclat qui murmure un nom.","exits":{"c_ossuaire":None},"search":"name_shard"},
        "c_seuil":   {"nom":"Le Seuil du Sanctum","desc":"Une porte de nacre. Il manque un sceau pour l'ouvrir.","exits":{"c_trone_s":None,"sanctum:s_voile":{"gate":"item:key_sanctum"}},"search":"key_sanctum"},
    }},
    "sanctum": {"nom":"Le Sanctum de la Treizième","minlvl":13,"color":"#120c1a","rooms":{
        "s_voile":   {"nom":"Le Dernier Voile","desc":"Une présence sans visage attend dans le noir absolu.","exits":{"crypte:c_seuil":None,"s_trone":{"gate":"witch:ombre"}},"witch":"ombre"},
        "s_trone":   {"nom":"Le Trône des Treize Voiles","desc":"Elle t'attend, couronnée d'ombre. La fin de tout.","exits":{"s_voile":None},"witch":"reine"},
    }},
}

START_ROOM = "vestibule:v_entree"

# === MOTEUR DE JEU "LES TREIZE VOILES" (côté serveur) ===
# Combat = mix tactique + hasard, modulé par l'écart de niveau.
# État sauvegardé côté serveur (fichier JSON par profil).



_WBYID = {w["id"]: w for w in WITCHES}
SAVE_LOCK = threading.Lock()

def witch_seed(wid):
    """Seed déterministe pour qu'une sorcière garde le même visage entre parties."""
    return int(hashlib.md5(wid.encode()).hexdigest()[:8], 16)

def new_game(origin="intrus"):
    """origin: 'intrus' (résiste) ou 'soumis' (volontaire)."""
    will_max = 100
    state = {
        "origin": origin,
        "level": 1,
        "xp": 0,
        "xp_next": 20,
        "will": will_max if origin == "intrus" else 70,
        "will_max": will_max,
        "grip": 0 if origin == "intrus" else 20,   # Emprise
        "room": START_ROOM,
        "visited": [START_ROOM],
        "inventory": [],
        "defeated": [],       # sorcières vaincues
        "marks": [],          # marques laissées par défaites (debuffs persistants)
        "knowledge": [],      # ids de sorcières dont on connaît le rôle (via Tome / rencontre)
        "flags": {},
        "log": [],
        "ending": None,
    }
    return state

def player_power(state):
    """Puissance effective du joueur = niveau + bonus items - malus marques."""
    p = state["level"]
    if "ember" in state["inventory"]:
        pass  # l'ember est un autowin ponctuel, pas un bonus passif
    p -= len(state.get("marks", []))  # chaque marque non levée affaiblit
    return max(1, p)

def can_enter_zone(state, zone):
    z = MAP.get(zone)
    if not z: return False
    return state["level"] >= z.get("minlvl", 1)

def has_knowledge(state, wid):
    return wid in state.get("knowledge", []) or "tome" in state["inventory"]

def resolve_combat(state, wid, tactic):
    """
    Résolution mix tactique + hasard + niveau.
    Retourne dict {result: win/lose, will_delta, grip_delta, xp, text, ...}.
    """
    w = _WBYID[wid]
    correct = (tactic == w["counter"])

    # Écart de niveau : sous-niveau => très dur, sur-niveau => facile
    gap = state["level"] - w["niveau"]   # >0 = joueur plus fort

    # Probabilité de base de réussite
    if correct:
        base = 0.78
    elif tactic in ("submit", "flee", "plead", "charge"):
        base = 0.12   # leurres : presque toujours mauvais
    else:
        base = 0.30   # mauvaise tactique mais pas un leurre total

    # Modulation par le niveau (chaque point d'écart vaut ~7%)
    prob = base + gap * 0.07
    # Bonus de connaissance : si on connaît le rôle, petit coup de pouce de lecture
    if has_knowledge(state, wid) and correct:
        prob += 0.08
    prob = max(0.03, min(0.97, prob))

    # Ember = victoire garantie (consommée)
    autowin = False
    if "ember" in state["inventory"]:
        # on ne consomme l'ember que si le joueur en a besoin (échec probable) — simplifié : on l'utilise si tactique != bonne
        pass

    roll = random.random()
    win = roll < prob

    out = {"witch": wid, "tactic": tactic, "correct": correct, "prob": round(prob, 2),
           "gap": gap, "roll": round(roll, 2)}

    if win:
        # Récompense XP : proportionnelle au niveau de la sorcière
        xp = 8 + w["niveau"] * 4
        # surcoût si on était sous-niveau (exploit) : bonus
        if gap < 0: xp = int(xp * 1.5)
        out.update({
            "result": "win",
            "will_delta": -max(0, (w["wcombat"] - state["level"])) if not correct else 0,
            "grip_delta": 3 if not correct else 0,
            "xp": xp,
            "text": w["win"],
        })
    else:
        # Défaite : perte de Volonté modérée (le jeu n'est pas un game-over), gain d'Emprise
        wl = -(w["wcombat"] + random.randint(0, 5))
        gd = 8 + w["niveau"]
        out.update({
            "result": "lose",
            "will_delta": wl,
            "grip_delta": gd,
            "xp": 1,  # XP de consolation minime (perdre n'est pas une stratégie de farm)
            "text": w["lose"],
        })
    return out

def apply_combat(state, wid, outcome):
    """Applique l'issue au state. Gère montée de niveau, marques, fins."""
    w = _WBYID[wid]
    # connaissance acquise après une rencontre
    if wid not in state["knowledge"]:
        state["knowledge"].append(wid)

    state["will"] = max(0, min(state["will_max"], state["will"] + outcome["will_delta"]))
    state["grip"] = max(0, min(100, state["grip"] + outcome["grip_delta"]))
    add_xp(state, outcome["xp"])

    if outcome["result"] == "win":
        if wid not in state["defeated"]:
            state["defeated"].append(wid)
        # lever une marque correspondante si présente (revanche)
        state["marks"] = [m for m in state["marks"] if m != wid]
        # boss final
        if wid == "reine":
            state["ending"] = ending_for(state, wid, victory=True)
    else:
        # marque persistante (debuff) si pas déjà présente
        if wid not in state["marks"] and wid not in state["defeated"]:
            state["marks"].append(wid)
        # Volonté à zéro => fin de soumission spécifique à la sorcière
        if state["will"] <= 0:
            state["ending"] = ending_for(state, wid, victory=False)
    return state

def add_xp(state, amount):
    state["xp"] += amount
    while state["xp"] >= state["xp_next"]:
        state["xp"] -= state["xp_next"]
        state["level"] += 1
        state["xp_next"] = int(state["xp_next"] * 1.4) + 10
        state["will_max"] += 10
        state["will"] = state["will_max"]   # plein soin de Volonté au level up

def rest(state):
    """Se reposer dans une salle sûre (sans sorcière) : régénère un peu de Volonté."""
    gain = 15 + state["level"] * 2
    state["will"] = min(state["will_max"], state["will"] + gain)
    return gain

def ending_for(state, wid, victory):
    w = _WBYID[wid]
    if victory and wid == "reine":
        if state["grip"] >= 70:
            return {"type":"throne_grip","titre":"Le Consort d'Ombre",
                    "texte":"Tu as vaincu la Treizième Voile — mais le Domaine t'a trop marqué. Tu prends sa place sur le trône, et c'est toi, désormais, qu'on viendra défier."}
        if state["origin"] == "soumis":
            return {"type":"throne_devoted","titre":"L'Égal Choisi",
                    "texte":"Tu es venu te soumettre, et tu repars souverain. La Treizième s'agenouille — par choix. Vous régnerez à deux."}
        return {"type":"throne_free","titre":"Le Briseur de Voiles",
                "texte":"Les treize voiles tombent un à un. Le Domaine s'effondre derrière toi tandis que tu remontes vers une porte qui, cette fois, s'ouvre."}
    # défaites par soumission
    return {"type":"submit","titre":f"Soumis à {w['nom']}",
            "texte":w["lose"] + " Ta volonté s'est tue. Tu lui appartiens, jusqu'à ce qu'on vienne — peut-être — te délivrer."}

# --- DÉPLACEMENT / EXPLORATION ---
def room_obj(room_key):
    if ":" in room_key:
        zone, rid = room_key.split(":", 1)
    else:
        # salle dans la zone courante : il faut le contexte ; on cherche partout
        for zname, z in MAP.items():
            if room_key in z["rooms"]:
                return zname, room_key, z["rooms"][room_key]
        return None, None, None
    z = MAP.get(zone)
    if not z or rid not in z["rooms"]:
        return None, None, None
    return zone, rid, z["rooms"][rid]

def resolve_exit_key(current_zone, exit_key):
    """Une sortie peut être 'rid' (même zone) ou 'zone:rid'."""
    if ":" in exit_key:
        return exit_key
    return f"{current_zone}:{exit_key}"

def gate_ok(state, cond):
    """Vérifie une condition de passage/secret. cond ex: 'item:eye', 'lvl:7', 'witch:liane'."""
    if not cond:
        return True
    kind, val = cond.split(":", 1)
    if kind == "item":
        return val in state["inventory"]
    if kind == "lvl":
        return state["level"] >= int(val)
    if kind == "witch":
        return val in state["defeated"]
    return True

def visible_exits(state):
    """Retourne les sorties visibles de la salle courante (cachées révélées par 'eye'/niveau)."""
    zone, rid, room = room_obj(state["room"])
    if not room:
        return []
    has_eye = "eye" in state["inventory"]
    out = []
    for ek, meta in room.get("exits", {}).items():
        full = resolve_exit_key(zone, ek)
        tz, trid, troom = room_obj(full)
        entry = {"key": full, "nom": troom["nom"] if troom else ek, "locked": False, "reason": None, "hidden": False}
        if isinstance(meta, dict):
            if "hidden" in meta:
                cond = meta["hidden"]
                kind = cond.split(":")[0]
                # révélé par l'Œil (pour item:eye) ou par niveau
                revealed = gate_ok(state, cond) or has_eye
                if not revealed:
                    continue  # totalement invisible
                entry["hidden"] = True
            if "gate" in meta:
                if not gate_ok(state, meta["gate"]):
                    entry["locked"] = True
                    entry["reason"] = meta["gate"]
        # zone min level
        if tz and not can_enter_zone(state, tz) and tz != zone:
            entry["locked"] = True
            entry["reason"] = f"lvl:{MAP[tz].get('minlvl',1)}"
        out.append(entry)
    return out

# --- SAUVEGARDE SERVEUR ---
def save_path(base_dir, profile):
    safe = hashlib.md5(profile.encode()).hexdigest()[:16]
    return os.path.join(base_dir, f".witch_save_{safe}.json")

def save_game(base_dir, profile, state):
    with SAVE_LOCK:
        try:
            with open(save_path(base_dir, profile), "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
            return True
        except Exception:
            return False

def load_game(base_dir, profile):
    with SAVE_LOCK:
        try:
            p = save_path(base_dir, profile)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    return None

WITCH_UI_HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="theme-color" content="#120c1a">
<link rel="manifest" href="/witch/manifest.json">
<title>Les Treize Voiles</title>
<style>
:root{ --safe-t:env(safe-area-inset-top); --safe-b:env(safe-area-inset-bottom); --acc:#b388ff; --will:#5cd6ff; --grip:#ff4d8d; }
*{box-sizing:border-box; -webkit-tap-highlight-color:transparent;}
html,body{margin:0; padding:0; height:100%; background:#0a0710; color:#e8e0f0; font-family:'Georgia','Times New Roman',serif; overflow:hidden;}
#game{position:fixed; inset:0; display:flex; flex-direction:column;}
#scene{position:relative; flex:1; overflow:hidden;}
#bg{position:absolute; inset:0; background-size:cover; background-position:center; transition:opacity .6s; z-index:1;}
#bg-canvas{position:absolute; inset:0; width:100%; height:100%; z-index:0;}
#vignette{position:absolute; inset:0; z-index:2; pointer-events:none; background:radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.85) 100%);}
#cine{position:absolute; inset:0; z-index:50; background:#000; display:none; align-items:center; justify-content:center;}
#cine video{max-width:100%; max-height:100%;}
#cine-skip{position:absolute; bottom:max(20px,var(--safe-b)); right:20px; background:rgba(0,0,0,0.6); border:1px solid rgba(255,255,255,0.3); color:#fff; padding:10px 20px; border-radius:20px; font-size:13px; cursor:pointer; z-index:51;}

/* HUD */
#hud{position:relative; z-index:10; padding:max(10px,var(--safe-t)) 14px 8px; background:linear-gradient(180deg, rgba(10,7,16,0.95), rgba(10,7,16,0)); display:flex; align-items:center; gap:12px; flex-wrap:wrap;}
.bar-wrap{flex:1; min-width:120px;}
.bar-lbl{font-size:10px; letter-spacing:1px; opacity:.7; text-transform:uppercase; margin-bottom:2px; display:flex; justify-content:space-between;}
.bar{height:8px; border-radius:4px; background:rgba(255,255,255,0.1); overflow:hidden;}
.bar > div{height:100%; transition:width .5s; border-radius:4px;}
.bar.will > div{background:linear-gradient(90deg,#2a8fc0,var(--will));}
.bar.grip > div{background:linear-gradient(90deg,#a02050,var(--grip));}
#lvl-badge{background:rgba(179,136,255,0.2); border:1px solid var(--acc); color:var(--acc); padding:5px 12px; border-radius:16px; font-size:13px; font-weight:bold; white-space:nowrap;}
#xpbar{height:3px; background:rgba(255,255,255,0.08); position:relative; z-index:10;}
#xpbar > div{height:100%; background:var(--acc); transition:width .5s;}

/* Panneau texte/choix */
#panel{position:relative; z-index:10; background:linear-gradient(0deg, rgba(10,7,16,0.97) 70%, rgba(10,7,16,0)); padding:14px 16px max(16px,var(--safe-b)); max-height:55%; overflow-y:auto;}
#room-title{font-size:13px; letter-spacing:2px; text-transform:uppercase; color:var(--acc); opacity:.85; margin-bottom:6px;}
#narration{font-size:16px; line-height:1.6; margin-bottom:14px; min-height:40px;}
#narration .witch-name{color:var(--grip); font-weight:bold;}
#narration em{color:var(--will); font-style:italic;}
#choices{display:flex; flex-direction:column; gap:9px;}
.choice{background:rgba(179,136,255,0.08); border:1px solid rgba(179,136,255,0.3); color:#e8e0f0; padding:13px 16px; border-radius:12px; font-size:15px; font-family:inherit; text-align:left; cursor:pointer; transition:all .15s; display:flex; align-items:center; gap:10px;}
.choice:active{transform:scale(0.98);}
.choice:hover{background:rgba(179,136,255,0.16); border-color:var(--acc);}
.choice.locked{opacity:.4; border-style:dashed; cursor:not-allowed;}
.choice.danger{border-color:rgba(255,77,141,0.4);}
.choice .ico{font-size:18px; flex-shrink:0;}
.choice .sub{font-size:11px; opacity:.6; margin-left:auto;}

/* Boutons système */
#sysbar{position:absolute; top:max(8px,var(--safe-t)); right:10px; z-index:20; display:flex; gap:6px;}
.sysb{width:36px; height:36px; border-radius:50%; background:rgba(0,0,0,0.5); border:1px solid rgba(255,255,255,0.15); color:#cbb; font-size:16px; cursor:pointer; display:flex; align-items:center; justify-content:center;}

/* Overlays */
.overlay{position:fixed; inset:0; z-index:100; background:rgba(8,5,14,0.96); display:none; flex-direction:column; padding:max(40px,var(--safe-t)) 24px max(24px,var(--safe-b)); overflow-y:auto;}
.overlay.show{display:flex;}
.overlay h2{color:var(--acc); letter-spacing:2px; font-size:20px; margin:0 0 16px;}
.inv-item{background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.12); border-radius:10px; padding:12px 14px; margin-bottom:8px;}
.inv-item .it-nom{font-weight:bold; color:var(--acc);}
.inv-item .it-desc{font-size:13px; opacity:.7; margin-top:3px;}
.inv-item .it-use{margin-top:8px; background:rgba(92,214,255,0.15); border:1px solid var(--will); color:var(--will); padding:7px 14px; border-radius:8px; font-size:13px; cursor:pointer;}
.witch-card{display:flex; gap:12px; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:10px; margin-bottom:10px; align-items:center;}
.witch-card img{width:60px; height:60px; border-radius:8px; object-fit:cover; background:#1a1424; flex-shrink:0;}
.witch-card .wc-nom{font-weight:bold; font-size:15px;}
.witch-card .wc-meta{font-size:12px; opacity:.7; margin-top:2px;}
.witch-card .wc-hint{font-size:12px; color:var(--will); margin-top:4px; font-style:italic;}
.witch-card.def{border-color:rgba(92,214,255,0.4);}
.witch-card.mark{border-color:rgba(255,77,141,0.4);}
.ov-close{margin-top:auto; background:rgba(179,136,255,0.15); border:1px solid var(--acc); color:var(--acc); padding:12px; border-radius:10px; font-size:15px; cursor:pointer;}

/* Titre */
#title-screen{position:fixed; inset:0; z-index:200; background:radial-gradient(ellipse at center, #1a0f28, #0a0710); display:flex; flex-direction:column; align-items:center; justify-content:center; padding:24px; text-align:center;}
#title-screen h1{font-size:34px; letter-spacing:4px; color:var(--acc); margin:0 0 8px; text-shadow:0 0 30px rgba(179,136,255,0.5);}
#title-screen .sub{opacity:.6; font-size:14px; letter-spacing:3px; margin-bottom:40px;}
.title-btn{width:100%; max-width:340px; background:rgba(179,136,255,0.1); border:1px solid var(--acc); color:#e8e0f0; padding:16px; border-radius:14px; font-size:16px; font-family:inherit; cursor:pointer; margin-bottom:12px;}
.title-btn:active{transform:scale(0.98);}
.origin-desc{font-size:13px; opacity:.6; max-width:340px; margin:-6px 0 18px; line-height:1.5;}

/* Combat */
#combat-banner{display:none; text-align:center; padding:10px; margin-bottom:12px; border-radius:10px; background:rgba(255,77,141,0.12); border:1px solid rgba(255,77,141,0.4);}
#combat-banner .cb-role{font-size:12px; color:var(--grip); letter-spacing:1px; text-transform:uppercase;}
#combat-banner .cb-lvl{font-size:12px; opacity:.7; margin-top:3px;}

#toast{position:fixed; bottom:max(80px,var(--safe-b)); left:50%; transform:translateX(-50%); z-index:300; background:rgba(0,0,0,0.85); color:#fff; padding:12px 22px; border-radius:24px; font-size:14px; opacity:0; transition:opacity .3s; pointer-events:none; max-width:80%; text-align:center;}
#toast.show{opacity:1;}
.flash{animation:flash .4s;}
@keyframes flash{0%{filter:brightness(2.5);}100%{filter:brightness(1);}}
</style>
</head>
<body>

<div id="title-screen">
  <h1>LES TREIZE VOILES</h1>
  <div class="sub">UN DOMAINE DONT ON NE RESSORT PAS INTACT</div>
  <div id="title-buttons"></div>
</div>

<div id="game" style="display:none;">
  <div id="scene">
    <canvas id="bg-canvas"></canvas>
    <div id="bg"></div>
    <div id="vignette"></div>
    <div id="sysbar">
      <div class="sysb" onclick="openInv()">🎒</div>
      <div class="sysb" onclick="openGrimoire()">📖</div>
      <div class="sysb" onclick="saveNow()">💾</div>
    </div>
    <div id="cine">
      <video id="cine-vid" playsinline></video>
      <div id="cine-skip" onclick="endCine()">Passer ▶</div>
    </div>
  </div>
  <div id="hud">
    <div id="lvl-badge">Niv 1</div>
    <div class="bar-wrap"><div class="bar-lbl"><span>Volonté</span><span id="will-num">100</span></div><div class="bar will"><div id="will-bar" style="width:100%"></div></div></div>
    <div class="bar-wrap"><div class="bar-lbl"><span>Emprise</span><span id="grip-num">0</span></div><div class="bar grip"><div id="grip-bar" style="width:0%"></div></div></div>
  </div>
  <div id="xpbar"><div id="xp-bar" style="width:0%"></div></div>
  <div id="panel">
    <div id="combat-banner"><div class="cb-role" id="cb-role"></div><div class="cb-lvl" id="cb-lvl"></div></div>
    <div id="room-title">—</div>
    <div id="narration">—</div>
    <div id="choices"></div>
  </div>
</div>

<div id="inv-overlay" class="overlay"><h2>🎒 Inventaire</h2><div id="inv-list"></div><div class="ov-close" onclick="closeOv('inv-overlay')">Fermer</div></div>
<div id="grim-overlay" class="overlay"><h2>📖 Grimoire des Voiles</h2><div id="grim-list"></div><div class="ov-close" onclick="closeOv('grim-overlay')">Fermer</div></div>
<div id="end-overlay" class="overlay" style="text-align:center; align-items:center; justify-content:center;"><h2 id="end-title"></h2><div id="end-text" style="font-size:17px; line-height:1.7; max-width:480px; margin-bottom:30px;"></div><div class="ov-close" style="max-width:300px;" onclick="location.reload()">Recommencer</div></div>

<div id="toast"></div>

<script>
// ============ ÉTAT & API ============
const PROFILE = 'default'; // un seul profil pour l'instant
let S = null;              // state serveur
let ASSETS = {images:[], videos:[]};
let META = null;           // witches, map, items, tactics

async function api(path, body){
  const r = await fetch('/witch/api/'+path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body||{})});
  return r.json();
}

// ============ DÉMARRAGE ============
async function boot(){
  META = await api('meta', {});
  ASSETS = META.assets || {images:[], videos:[]};
  const saved = await api('load', {profile:PROFILE});
  const tb = document.getElementById('title-buttons');
  tb.innerHTML = '';
  if(saved && saved.state && !saved.state.ending){
    let b = document.createElement('button'); b.className='title-btn'; b.textContent='▶ Continuer';
    b.onclick = ()=>{ S = saved.state; startGame(); }; tb.appendChild(b);
  }
  let d1 = document.createElement('div'); d1.className='origin-desc'; d1.textContent="Choisis qui tu es en franchissant le seuil :"; tb.appendChild(d1);
  let bi = document.createElement('button'); bi.className='title-btn'; bi.innerHTML='⚔️ L\'Intrus <span style="opacity:.6;font-size:13px">— tu résistes</span>';
  bi.onclick = ()=>newGame('intrus'); tb.appendChild(bi);
  let di = document.createElement('div'); di.className='origin-desc'; di.textContent="Pleine Volonté, nulle Emprise. Tu es venu prendre, pas céder."; tb.appendChild(di);
  let bs = document.createElement('button'); bs.className='title-btn'; bs.innerHTML='🕯️ Le Suppliant <span style="opacity:.6;font-size:13px">— tu te soumets</span>';
  bs.onclick = ()=>newGame('soumis'); tb.appendChild(bs);
  let ds = document.createElement('div'); ds.className='origin-desc'; ds.textContent="Tu commences déjà marqué — mais certaines portes ne s'ouvrent qu'à ceux qui plient. Une fin t'est réservée."; tb.appendChild(ds);
}

async function newGame(origin){
  const r = await api('new', {profile:PROFILE, origin:origin});
  S = r.state; startGame();
}

function startGame(){
  document.getElementById('title-screen').style.display='none';
  document.getElementById('game').style.display='flex';
  renderRoom();
}

// ============ FONDS GÉNÉRÉS ============
function genBackground(zoneColor, seed){
  const cv = document.getElementById('bg-canvas');
  const ctx = cv.getContext('2d');
  const W = cv.width = cv.offsetWidth, H = cv.height = cv.offsetHeight;
  let rnd = mulberry(seed);
  // dégradé de base
  let g = ctx.createLinearGradient(0,0,0,H);
  g.addColorStop(0, shade(zoneColor, 30));
  g.addColorStop(1, shade(zoneColor, -40));
  ctx.fillStyle = g; ctx.fillRect(0,0,W,H);
  // motif occulte : arcs/cercles concentriques
  ctx.strokeStyle = 'rgba(255,255,255,0.06)'; ctx.lineWidth = 1.5;
  let cx = W*(0.3+rnd()*0.4), cy = H*(0.3+rnd()*0.4);
  for(let i=1;i<=7;i++){ ctx.beginPath(); ctx.arc(cx,cy, i*Math.min(W,H)*0.07, 0, Math.PI*2); ctx.stroke(); }
  // rayons
  for(let i=0;i<12;i++){ let a=rnd()*Math.PI*2; ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(cx+Math.cos(a)*W, cy+Math.sin(a)*W); ctx.stroke(); }
  // brume
  for(let i=0;i<40;i++){ ctx.fillStyle='rgba('+(200)+','+(180)+','+(255)+','+(rnd()*0.03)+')'; let r=rnd()*180+40; ctx.beginPath(); ctx.arc(rnd()*W, rnd()*H, r,0,Math.PI*2); ctx.fill(); }
  document.getElementById('bg').style.backgroundImage='none';
  document.getElementById('bg').style.opacity='0';
}
function mulberry(a){ return function(){ a|=0; a=a+0x6D2B79F5|0; let t=Math.imul(a^a>>>15,1|a); t=t+Math.imul(t^t>>>7,61|t)^t; return((t^t>>>14)>>>0)/4294967296; }; }
function shade(hex,p){ let n=parseInt(hex.slice(1),16),r=(n>>16)+p,g=((n>>8)&255)+p,b=(n&255)+p; r=Math.max(0,Math.min(255,r));g=Math.max(0,Math.min(255,g));b=Math.max(0,Math.min(255,b)); return '#'+((1<<24)+(r<<16)+(g<<8)+b).toString(16).slice(1); }

function showWitchImage(seed){
  if(!ASSETS.images.length){ return false; }
  let idx = seed % ASSETS.images.length;
  document.getElementById('bg').style.backgroundImage = 'url(/f/'+ASSETS.images[idx]+')';
  document.getElementById('bg').style.opacity = '1';
  return true;
}

// ============ CINÉMATIQUES VIDÉO ============
let cineCb=null;
function playCine(seed, cb){
  if(!ASSETS.videos.length){ if(cb)cb(); return; }
  cineCb = cb;
  let idx = seed % ASSETS.videos.length;
  let v = document.getElementById('cine-vid');
  v.src = '/f/'+ASSETS.videos[idx];
  document.getElementById('cine').style.display='flex';
  v.onended = endCine; v.play().catch(()=>endCine());
}
function endCine(){
  let v=document.getElementById('cine-vid'); v.pause(); v.removeAttribute('src'); v.load();
  document.getElementById('cine').style.display='none';
  let cb=cineCb; cineCb=null; if(cb)cb();
}

// ============ RENDU SALLE ============
function hashStr(s){ let h=0; for(let i=0;i<s.length;i++){ h=(h*31+s.charCodeAt(i))>>>0; } return h; }

async function renderRoom(){
  updateHUD();
  document.getElementById('combat-banner').style.display='none';
  const r = await api('room', {profile:PROFILE});
  S = r.state;
  if(S.ending){ showEnding(S.ending); return; }
  const room = r.room;
  document.getElementById('room-title').textContent = r.zoneName + ' · ' + room.nom;

  // Fond : sorcière présente (et pas vaincue) -> son image ; sinon fond généré
  if(room.witch && !S.defeated.includes(room.witch)){
    let seed = hashStr(room.witch);
    if(!showWitchImage(seed)) genBackground(r.zoneColor, seed);
  } else {
    genBackground(r.zoneColor, hashStr(S.room));
  }

  let narr = room.desc;
  document.getElementById('narration').innerHTML = narr;

  const choicesEl = document.getElementById('choices');
  choicesEl.innerHTML='';

  // Sorcière non vaincue dans la salle -> rencontre
  if(room.witch && !S.defeated.includes(room.witch)){
    const w = META.witches[room.witch];
    document.getElementById('narration').innerHTML =
      narr + '<br><br><span class="witch-name">'+w.nom+'</span> se dresse devant toi.<br><em>'+w.intro+'</em>';
    addChoice('⚔️','Affronter '+w.nom, ()=>startCombat(room.witch), false, false);
    // fuir possible (revenir)
    addChoice('🚪','Reculer prudemment', ()=>{ toast('Tu te retires. Elle te laisse partir... pour l\'instant.'); renderRoom(); }, false, true);
  } else {
    // Exploration : sorties + fouille + repos
    if(room.search && !S.flags['searched_'+S.room]){
      addChoice('🔍','Fouiller la salle', ()=>doSearch(), false, false);
    }
    if(!room.witch){
      addChoice('🕯️','Te reposer (récupérer de la Volonté)', ()=>doRest(), false, false);
    }
    for(const ex of r.exits){
      let label = ex.hidden ? ('✨ '+ex.nom+' (passage caché)') : ex.nom;
      if(ex.locked){
        addChoice('🔒', label, null, true, false, lockReason(ex.reason));
      } else {
        addChoice('➡️', label, ()=>move(ex.key), false, false);
      }
    }
  }
}

function lockReason(reason){
  if(!reason) return 'Verrouillé';
  let [k,v]=reason.split(':');
  if(k==='lvl') return 'Niveau '+v+' requis';
  if(k==='item') return 'Requiert : '+(META.items[v]?META.items[v].nom:v);
  if(k==='witch') return 'Vaincre '+(META.witches[v]?META.witches[v].nom:v);
  return 'Verrouillé';
}

function addChoice(ico, txt, fn, locked, danger, sub){
  const el = document.createElement('button');
  el.className='choice'+(locked?' locked':'')+(danger?' danger':'');
  el.innerHTML='<span class="ico">'+ico+'</span><span>'+txt+'</span>'+(sub?'<span class="sub">'+sub+'</span>':'');
  if(fn && !locked) el.onclick=fn;
  document.getElementById('choices').appendChild(el);
}

async function move(key){
  const r = await api('move', {profile:PROFILE, to:key});
  if(!r.ok){ toast(r.msg||'Impossible'); return; }
  S = r.state; renderRoom();
}

async function doSearch(){
  const r = await api('search', {profile:PROFILE});
  S = r.state;
  if(r.found){ toast('🔍 Trouvé : '+META.items[r.found].nom); document.getElementById('scene').classList.add('flash'); setTimeout(()=>document.getElementById('scene').classList.remove('flash'),400); }
  else toast('Rien d\'utile ici.');
  renderRoom();
}

async function doRest(){
  const r = await api('rest', {profile:PROFILE});
  S = r.state; toast('🕯️ Tu reprends '+r.gain+' de Volonté.'); renderRoom();
}

// ============ COMBAT ============
let combatWitch=null;
async function startCombat(wid){
  combatWitch = wid;
  const w = META.witches[wid];
  document.getElementById('combat-banner').style.display='block';
  // rôle révélé si on a la connaissance / le tome
  let known = S.knowledge.includes(wid) || S.inventory.includes('tome');
  document.getElementById('cb-role').textContent = known ? ('RÔLE : '+w.roleLabel) : 'RÔLE INCONNU';
  document.getElementById('cb-lvl').textContent = 'Niveau '+w.niveau+' · '+(S.level>=w.niveau?'à ta portée':'au-dessus de toi')+(known?(' — '+w.hint):'');
  document.getElementById('narration').innerHTML='<span class="witch-name">'+w.nom+'</span><br><em>'+w.desc+'</em><br><br>Comment réagis-tu ?';
  const choicesEl=document.getElementById('choices'); choicesEl.innerHTML='';
  // propose la bonne tactique noyée dans des leurres
  let opts = buildTactics(wid, known);
  for(const t of opts){
    addChoice('•', META.tactics[t], ()=>doCombat(wid,t), false, t==='charge'||t==='flee');
  }
  // objet utilisable en combat
  if(S.inventory.includes('ember')){ addChoice('🔥','Utiliser la Braise Ancienne (victoire assurée)', ()=>useEmber(wid), false, false); }
}

function buildTactics(wid, known){
  const w = META.witches[wid];
  let pool = ['resist','observe','defy','patient','refuse','break','trust','split','cut','warm','remember','starve','distance','halftruth','sever','adapt','reverse','submit','flee','charge'];
  // toujours inclure le bon contre
  let chosen = new Set([w.counter]);
  // si on connaît, on présente 3 options dont la bonne ; sinon 5 options
  let n = known ? 3 : 5;
  let others = pool.filter(t=>t!==w.counter);
  shuffle(others);
  for(let t of others){ if(chosen.size>=n) break; chosen.add(t); }
  // contre spéciaux nécessitant items
  let arr=[...chosen];
  shuffle(arr);
  return arr;
}
function shuffle(a){ for(let i=a.length-1;i>0;i--){ let j=Math.floor(Math.random()*(i+1)); [a[i],a[j]]=[a[j],a[i]]; } }

async function doCombat(wid, tactic){
  const r = await api('combat', {profile:PROFILE, witch:wid, tactic:tactic});
  S = r.state;
  const o = r.outcome;
  document.getElementById('scene').classList.add('flash');
  setTimeout(()=>document.getElementById('scene').classList.remove('flash'),400);
  updateHUD();
  // afficher résultat
  document.getElementById('choices').innerHTML='';
  let txt = (o.result==='win'?'<em>Victoire.</em> ':'<em>Tu cèdes du terrain.</em> ') + o.text;
  document.getElementById('narration').innerHTML = txt;
  if(S.ending){ setTimeout(()=>showEnding(S.ending), 1500); return; }
  if(o.result==='win'){
    playCine(hashStr(wid+'win'), ()=>{ addChoice('➡️','Continuer', ()=>renderRoom()); });
    if(o.levelup) toast('⬆️ Niveau '+S.level+' !');
  } else {
    addChoice('↩️','Te replier et te renforcer', ()=>renderRoom());
    if(o.marked) toast('💀 '+META.witches[wid].nom+' t\'a marqué. Reviens plus fort.');
  }
}

async function useEmber(wid){
  const r = await api('combat', {profile:PROFILE, witch:wid, tactic:'__ember__'});
  S=r.state; updateHUD();
  document.getElementById('choices').innerHTML='';
  document.getElementById('narration').innerHTML='<em>La Braise s\'embrase.</em> '+META.witches[wid].win;
  if(S.ending){ setTimeout(()=>showEnding(S.ending),1500); return; }
  playCine(hashStr(wid+'win'), ()=>addChoice('➡️','Continuer', ()=>renderRoom()));
}

// ============ HUD ============
function updateHUD(){
  if(!S) return;
  document.getElementById('lvl-badge').textContent='Niv '+S.level;
  let wp = Math.round(S.will/S.will_max*100);
  document.getElementById('will-bar').style.width=wp+'%';
  document.getElementById('will-num').textContent=S.will+'/'+S.will_max;
  document.getElementById('grip-bar').style.width=S.grip+'%';
  document.getElementById('grip-num').textContent=S.grip;
  document.getElementById('xp-bar').style.width=Math.round(S.xp/S.xp_next*100)+'%';
}

// ============ INVENTAIRE / GRIMOIRE ============
function openInv(){
  const el=document.getElementById('inv-list'); el.innerHTML='';
  if(!S.inventory.length){ el.innerHTML='<div style="opacity:.5">Vide. Fouille les salles.</div>'; }
  for(const id of S.inventory){
    const it=META.items[id];
    let div=document.createElement('div'); div.className='inv-item';
    div.innerHTML='<div class="it-nom">'+it.nom+'</div><div class="it-desc">'+it.desc+'</div>';
    if(it.type==='potion'){ let b=document.createElement('button'); b.className='it-use'; b.textContent='Utiliser'; b.onclick=()=>useItem(id); div.appendChild(b); }
    el.appendChild(div);
  }
  document.getElementById('inv-overlay').classList.add('show');
}
async function useItem(id){
  const r=await api('use_item',{profile:PROFILE, item:id});
  S=r.state; updateHUD(); toast(r.msg||'Utilisé'); closeOv('inv-overlay');
}
function openGrimoire(){
  const el=document.getElementById('grim-list'); el.innerHTML='';
  let order=Object.values(META.witches).sort((a,b)=>a.niveau-b.niveau);
  for(const w of order){
    let known=S.knowledge.includes(w.id)||S.inventory.includes('tome');
    let def=S.defeated.includes(w.id), mark=S.marks.includes(w.id);
    let div=document.createElement('div'); div.className='witch-card'+(def?' def':'')+(mark?' mark':'');
    let imgIdx = ASSETS.images.length ? (hashStr(w.id)%ASSETS.images.length) : -1;
    let imgTag = imgIdx>=0 ? '<img src="/t/'+ASSETS.images[imgIdx]+'" onerror="this.style.opacity=0">' : '<img>';
    if(!known){
      div.innerHTML='<img style="filter:brightness(0.2)"><div><div class="wc-nom" style="opacity:.5">??? '+(def?'(vaincue)':'')+'</div><div class="wc-meta">Niveau '+w.niveau+'</div></div>';
    } else {
      div.innerHTML=imgTag+'<div><div class="wc-nom">'+w.nom+(def?' ✓':'')+(mark?' 💀':'')+'</div><div class="wc-meta">Niveau '+w.niveau+' · '+w.roleLabel+'</div><div class="wc-hint">'+w.hint+'</div></div>';
    }
    el.appendChild(div);
  }
  document.getElementById('grim-overlay').classList.add('show');
}
function closeOv(id){ document.getElementById(id).classList.remove('show'); }

async function saveNow(){ await api('save',{profile:PROFILE, state:S}); toast('💾 Partie sauvegardée'); }

function showEnding(end){
  document.getElementById('end-title').textContent=end.titre;
  document.getElementById('end-text').textContent=end.texte;
  document.getElementById('end-overlay').classList.add('show');
  playCine(hashStr(end.type), ()=>{});
}

// ============ TOAST ============
let toastT=null;
function toast(msg, dur){ const el=document.getElementById('toast'); el.textContent=msg; el.classList.add('show'); if(toastT)clearTimeout(toastT); toastT=setTimeout(()=>el.classList.remove('show'), dur||2200); }

// auto-save périodique
setInterval(()=>{ if(S && !S.ending) api('save',{profile:PROFILE, state:S}); }, 20000);

// Service worker (requis pour l'installation PWA)
if('serviceWorker' in navigator){ navigator.serviceWorker.register('/witch/sw.js').catch(()=>{}); }

boot();
</script>
</body>
</html>
"""

_WITCH_ICON_CACHE = {}
def _witch_icon_png(size=512):
    # Génère (et met en cache) une icône PNG pour l'installation PWA.
    if size in _WITCH_ICON_CACHE:
        return _WITCH_ICON_CACHE[size]
    if not HAS_PILLOW:
        return None
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
        return None
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

def lock_msg(reason):
    if not reason: return "Verrouillé."
    k, v = reason.split(":", 1)
    if k == "lvl": return f"Niveau {v} requis pour cette zone."
    if k == "item": return f"Il te faut : {ITEMS.get(v,{}).get('nom', v)}."
    if k == "witch":
        nm = next((w['nom'] for w in WITCHES if w['id']==v), v)
        return f"Tu dois d'abord vaincre {nm}."
    return "Verrouillé."

def use_item(state, iid):
    if iid not in state["inventory"]:
        return "Tu n'as pas cet objet."
    it = ITEMS.get(iid)
    if not it or it.get("type") != "potion":
        return "Cet objet ne s'utilise pas ainsi."
    eff = it.get("effect", {})
    if "will" in eff:
        state["will"] = min(state["will_max"], state["will"] + eff["will"])
    if "grip" in eff:
        state["grip"] = max(0, state["grip"] + eff["grip"])
    if eff.get("autowin"):
        return "Garde la Braise pour un combat : utilise-la pendant l'affrontement."
    # consommer (sauf ember qui se garde pour le combat)
    if iid != "ember":
        state["inventory"].remove(iid)
    return f"{it['nom']} utilisé."


# ═══════════════════════════════════════════════════════════════════
# §5 — SÉCURITÉ SYSTÈME
# ═══════════════════════════════════════════════════════════════════

def disable_ctrl_c(sig, frame):
    pass

signal.signal(signal.SIGINT, disable_ctrl_c)


def secret_kill_switch():
    fd = None
    old_settings = None
    try:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setraw(fd)
        buffer = ""
        while True:
            char = sys.stdin.read(1)
            if char in ('\x03', '\x1a', '\x1c', '\x04'):
                continue
            buffer += char.lower()
            if KILL_PHRASE in buffer:
                if old_settings is not None:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                print("\n\r✅ [DÉVERROUILLAGE] Mot de passe accepté. Arrêt du système...")
                os._exit(0)
            if len(buffer) > 40:
                buffer = buffer[-len(KILL_PHRASE):]
    except Exception:
        if fd is not None and old_settings is not None:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass
        while True:
            try:
                if input().strip().lower() == KILL_PHRASE:
                    os._exit(0)
            except Exception:
                time.sleep(1)

threading.Thread(target=secret_kill_switch, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# §6 — BASE DE DONNÉES
# ═══════════════════════════════════════════════════════════════════

def xor_chunk(chunk, offset):
    if offset >= SCRAMBLE_SIZE:
        return chunk
    chunk_array = bytearray(chunk)
    key_len = len(XOR_KEY)
    xor_length = min(len(chunk_array), SCRAMBLE_SIZE - offset)
    for i in range(xor_length):
        chunk_array[i] ^= XOR_KEY[(offset + i) % key_len]
    return bytes(chunk_array)


def lock_purgatory_file(filepath):
    try:
        with open(filepath, 'r+b') as f:
            chunk = bytearray(f.read(1024 * 1024))
            if not chunk:
                return
            key_len = len(PURGATORY_KEY)
            for i in range(len(chunk)):
                chunk[i] ^= PURGATORY_KEY[i % key_len]
            chunk.reverse()
            f.seek(0)
            f.write(chunk)
    except Exception:
        pass


def unlock_purgatory_file(filepath):
    try:
        with open(filepath, 'r+b') as f:
            chunk = bytearray(f.read(1024 * 1024))
            if not chunk:
                return
            chunk.reverse()
            key_len = len(PURGATORY_KEY)
            for i in range(len(chunk)):
                chunk[i] ^= PURGATORY_KEY[i % key_len]
            f.seek(0)
            f.write(chunk)
    except Exception:
        pass


def lock_database():
    global FILE_INDEX, FILE_INDEX_R
    midnight = get_midnight_timestamp()
    with open(DB_LOCK_FILE, "w") as f:
        f.write(str(midnight))
    FILE_INDEX   = {}
    FILE_INDEX_R = {}


def unlock_database_file():
    try:
        os.remove(DB_LOCK_FILE)
    except Exception:
        pass


def get_midnight_timestamp():
    now = datetime.datetime.now()
    midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


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
            ("faces_data", "TEXT DEFAULT ''"), ("demographics", "TEXT DEFAULT ''")
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
        return conn


# --- Vérification du lock fichier au démarrage ---
if os.path.exists(DB_LOCK_FILE):
    try:
        with open(DB_LOCK_FILE) as _lf:
            _unlock_ts = float(_lf.read().strip())
        if time.time() < _unlock_ts:
            SESSION_KEY_ACTIVE = False
            LOCKED_UNTIL = _unlock_ts
            print(f"🔒 [QUOTA] Galerie verrouillée jusqu'à minuit.")
        else:
            unlock_database_file()
            print("🔓 [QUOTA] Verrou expiré, déverrouillage automatique.")
    except Exception:
        pass

if is_night_hours():
    print(f"🌙 [QUOTA] Fenêtre 23h–6h détectée : quota réduit.")

db = init_db()


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
            videos = sum(1 for f in MEDIA_FILES if is_obfuscated_video(f))
            images = len(MEDIA_FILES) - videos
            audios = len(AUDIO_FILES)
            total_files = images + videos + audios

        with DB_LOCK:
            c = db.cursor()
            c.execute("SELECT SUM(liked), SUM(vault) FROM media")
            row = c.fetchone()
            liked = row[0] or 0
            vault = row[1] or 0
            c.execute("SELECT COUNT(*) FROM history")
            history = c.fetchone()[0]
            c.execute("SELECT value FROM global_stats WHERE key='total_time'")
            total_time = c.fetchone()[0]

        return {
            'total_files': total_files, 'images': images, 'videos': videos,
            'audios': audios, 'liked': liked, 'vault': vault, 'history': history,
            'total_time': total_time
        }
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════
# §7 — GESTION DES MÉDIAS
# ═══════════════════════════════════════════════════════════════════

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
    global MEDIA_FILES, AUDIO_FILES
    with INDEX_LOCK:
        all_f = [
            (r, f) for r, _, fs in os.walk(MEDIA_DIR)
            if TRASH_DIR not in r and CORRUPT_DIR not in r and THUMB_DIR not in r and PURGATORY_DIR not in r and BACKUP_DIR not in r
            for f in fs
        ]
        MEDIA_FILES = [os.path.abspath(os.path.join(r, f)) for r, f in all_f if is_obfuscated_media(f)]
        AUDIO_FILES = [os.path.abspath(os.path.join(r, f)) for r, f in all_f if is_obfuscated_audio(f)]

    with FILE_INDEX_LOCK:
        FILE_INDEX.clear()
        FILE_INDEX_R.clear()
        FILE_CTIME.clear()
        FILE_SIZE.clear()

        for p in MEDIA_FILES + AUDIO_FILES:
            fid = hashlib.md5(p.encode('utf-8')).hexdigest()[:16]
            FILE_INDEX[fid] = p
            FILE_INDEX_R[p] = fid
            try:
                stat_info = os.stat(p)
                FILE_CTIME[p] = getattr(stat_info, 'st_birthtime', stat_info.st_ctime)
                FILE_SIZE[p] = stat_info.st_size
            except Exception:
                FILE_CTIME[p] = 0
                FILE_SIZE[p] = 0


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


def live_degrade_image(filepath, wear_ratio):
    if not HAS_PILLOW:
        return
    base = filepath[:-EXT_LEN] if filepath.endswith(SVAULT_EXT) else filepath
    ext = os.path.splitext(base)[1].lower()
    if ext not in IMG_EXTS:
        return
    if ext == '.gif':
        return

    if float(wear_ratio) <= 0.05:
        restore_from_backup(filepath)
        return

    backup_original_once(filepath)

    try:
        with open(filepath, 'rb') as f:
            header = f.read(SCRAMBLE_SIZE)
            rest = f.read()
        dec_data = xor_chunk(header, 0) + rest

        with Image.open(io.BytesIO(dec_data)) as img:
            orig_format = (img.format or 'JPEG').upper()
            img = img.convert('RGB')

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

            out_io = io.BytesIO()
            if orig_format == 'PNG':
                img.save(out_io, format='PNG', optimize=False)
            else:
                img.save(out_io, format='JPEG', quality=86)
            new_data = bytearray(out_io.getvalue())

        new_data[:SCRAMBLE_SIZE] = bytearray(xor_chunk(bytes(new_data[:SCRAMBLE_SIZE]), 0))
        with open(filepath, 'wb') as f:
            f.write(new_data)
    except Exception as e:
        print(f"Erreur dégradation image: {e}")


_video_degrade_inflight = set()
_video_degrade_master_lock = threading.Lock()


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

    threading.Thread(target=worker, daemon=True).start()
    return True


def live_degrade_video(filepath, wear_ratio):
    if float(wear_ratio) <= 0.05:
        restore_from_backup(filepath)
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
            images_coffre = [f for f in MEDIA_FILES if not is_obfuscated_video(f)]
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


# ═══════════════════════════════════════════════════════════════════
# §8 — WORKERS EN ARRIÈRE-PLAN
# ═══════════════════════════════════════════════════════════════════

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
                fid = FILE_INDEX_R.get(p)
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
                files = list(MEDIA_FILES)
            rows = db_fetch("SELECT path FROM media WHERE (r != -1 AND phash != '') AND corrupted = 0")
            analyzed_files = set(r[0] for r in rows)

            processed_in_batch = 0
            for f in files:
                fid = FILE_INDEX_R.get(f)
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
    global SESSION_KEY_ACTIVE, LOCKED_UNTIL, LOCKDOWN_TRIGGERED
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
                    SESSION_KEY_ACTIVE  = True
                    LOCKED_UNTIL        = 0.0
                    LOCKDOWN_TRIGGERED  = False
                    threading.Thread(target=reindex_bg, daemon=True).start()
                    print("🔓 [QUOTA] Déverrouillage automatique à minuit.")
            except Exception as e:
                print(f"⚠️  [QUOTA] erreur : {e}")



# ═══════════════════════════════════════════════════════════════════
# §9 — SERVEUR HTTP
# ═══════════════════════════════════════════════════════════════════

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
                if not SESSION_KEY_ACTIVE and not BURN_MODE_SERVER:
                    self.send_json({'files': [], 'locked': True})
                    return
                mode = q.get('mode', ['all'])[0]
                sort = q.get('sort', ['unseen'])[0]
                minr = int(q.get('minr', ['0'])[0])
                limit = int(q.get('limit', ['999999'])[0])
                color_filter = q.get('color', [''])[0]
                vault_req = q.get('vault', ['false'])[0] == 'true'
                demo_filter = q.get('demo', ['all'])[0]

                with INDEX_LOCK: pool = list(MEDIA_FILES)

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
                    if sort == 'date': pool.sort(key=lambda x: FILE_CTIME.get(x, 0), reverse=True)
                    elif sort == 'date_asc': pool.sort(key=lambda x: FILE_CTIME.get(x, 0))
                    elif sort == 'size': pool.sort(key=lambda x: FILE_SIZE.get(x, 0), reverse=True)
                    elif sort == 'size_asc': pool.sort(key=lambda x: FILE_SIZE.get(x, 0))
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
                        'file': f'/f/{FILE_INDEX_R.get(f, "")}',
                        'liked': d['liked'], 'tags': tags_map.get(f, []), 'names': names_map.get(f, []),
                        'rating': d['rating'], 'note': notes_map.get(f, ''), 'views': d['views'], 'video': is_obfuscated_video(f),
                        'faces_data': d['faces_data'], 'demographics': d['demographics'],
                        'size': FILE_SIZE.get(f, 0),
                        'ctime': FILE_CTIME.get(f, 0)
                    })
                self.send_json(res)
                return

            if path == '/api/all_names': return self.send_json(get_all_unique_names())
            if path == '/api/audio': return self.send_json([f'/f/{FILE_INDEX_R.get(p,"")}' for p in list(AUDIO_FILES)])
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
                    fp = FILE_INDEX.get(fid)
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
        global BURN_MODE_SERVER
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
                fp_db = FILE_INDEX.get(d.get('file')[3:])

            # --- ENDPOINT : DÉGRADATION INCRÉMENTALE (image OU vidéo) ---
            if path == '/api/degrade_live':
                wear_ratio = float(d.get('wear_ratio', 0.0))
                if fp_db and os.path.exists(fp_db):
                    base = fp_db[:-EXT_LEN] if fp_db.endswith(SVAULT_EXT) else fp_db
                    ext = os.path.splitext(base)[1].lower()
                    if ext in VID_EXTS:
                        live_degrade_video(fp_db, wear_ratio)
                    else:
                        live_degrade_image(fp_db, wear_ratio)
                self.send_json({'ok': True})

            # === API DU JEU "LES TREIZE VOILES" ===
            elif path.startswith('/witch/api/'):
                action = path[len('/witch/api/'):]
                profile = str(d.get('profile', 'default'))

                if action == 'meta':
                    # Expose witches (avec rôle/hint/niveau), items, tactics, et assets médias
                    with INDEX_LOCK:
                        imgs = [FILE_INDEX_R[f] for f in MEDIA_FILES if not is_obfuscated_video(f) and f in FILE_INDEX_R]
                        vids = [FILE_INDEX_R[f] for f in MEDIA_FILES if is_obfuscated_video(f) and f in FILE_INDEX_R]
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
                BURN_MODE_SERVER = True
                indexer()
                self.send_json({'ok': True})

            elif path == '/api/burn_exit':
                BURN_MODE_SERVER = False
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

                if SESSION_KEY_ACTIVE:
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
                            global SESSION_KEY_ACTIVE, LOCKDOWN_TRIGGERED
                            if LOCKDOWN_TRIGGERED: return
                            LOCKDOWN_TRIGGERED = True
                            SESSION_KEY_ACTIVE = False
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
                            if fp_db in MEDIA_FILES: MEDIA_FILES.remove(fp_db)
                            if fp_db in AUDIO_FILES: AUDIO_FILES.remove(fp_db)
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


# ═══════════════════════════════════════════════════════════════════
# §10 — DÉMARRAGE
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print(f"📁 Dossier server  : {BASE_DIR}")
    print(f"📂 Dossier médias  : {MEDIA_DIR}")

    scan_obfuscate()
    scan_and_move_corrupted()
    indexer()

    threading.Thread(target=reindex_bg,         daemon=True).start()
    threading.Thread(target=bg_worker,           daemon=True).start()
    threading.Thread(target=resurrection_worker, daemon=True).start()
    threading.Thread(target=daily_reset_worker,  daemon=True).start()

    with ThreadedHTTPServer(("", PORT), GalleryHandler) as httpd:
        print(f"💎 SONIC-SHIELD PRO : http://localhost:{PORT}")
        print("🚫 [SÉCURITÉ EXTRÊME] Clavier aveugle.")
        print("🔑 Tapez 'azertyuiop' à l'aveugle pour stopper le système.")
        httpd.serve_forever()
