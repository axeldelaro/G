# ═══════════════════════════════════════════════════════════════════
# security.py — XOR, verrous purgatoire/db, kill-switch
# ═══════════════════════════════════════════════════════════════════
import os
import sys
import time
import signal
import termios
import tty
import datetime
import threading

import config
from config import SCRAMBLE_SIZE, XOR_KEY, PURGATORY_KEY, DB_LOCK_FILE, KILL_PHRASE


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


def get_midnight_timestamp():
    now = datetime.datetime.now()
    midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


def lock_database():
    midnight = get_midnight_timestamp()
    with open(DB_LOCK_FILE, "w") as f:
        f.write(str(midnight))
    config.FILE_INDEX   = {}
    config.FILE_INDEX_R = {}


def unlock_database_file():
    try:
        os.remove(DB_LOCK_FILE)
    except Exception:
        pass


def disable_ctrl_c(sig, frame):
    pass


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


def install_killswitch():
    signal.signal(signal.SIGINT, disable_ctrl_c)
    threading.Thread(target=secret_kill_switch, daemon=True).start()
