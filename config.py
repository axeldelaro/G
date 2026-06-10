# ═══════════════════════════════════════════════════════════════════
# config.py — constantes + état runtime mutable + détection Pillow
# ═══════════════════════════════════════════════════════════════════
import os
import sys
import threading
import hashlib

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
