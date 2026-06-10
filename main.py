#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
# main.py — point d'entrée : python3 main.py [dossier_medias]
# ═══════════════════════════════════════════════════════════════════
import threading

import config
import security
import database
import media
import workers
import server
import witch_game


if __name__ == '__main__':
    print(f"📁 Dossier server  : {config.BASE_DIR}")
    print(f"📂 Dossier médias  : {config.MEDIA_DIR}")

    # Initialisation DB (db = ...) puis vérification du lock fichier.
    database.init_db()
    database.check_startup_lock()

    # Sécurité : SIGINT neutralisé + kill-switch clavier aveugle.
    security.install_killswitch()

    media.scan_obfuscate()
    media.scan_and_move_corrupted()
    media.indexer()

    threading.Thread(target=workers.reindex_bg,         daemon=True).start()
    threading.Thread(target=workers.bg_worker,           daemon=True).start()
    threading.Thread(target=workers.resurrection_worker, daemon=True).start()
    threading.Thread(target=workers.daily_reset_worker,  daemon=True).start()

    with server.ThreadedHTTPServer(("", config.PORT), server.GalleryHandler) as httpd:
        print(f"💎 SONIC-SHIELD PRO : http://localhost:{config.PORT}")
        print("🚫 [SÉCURITÉ EXTRÊME] Clavier aveugle.")
        print("🔑 Tapez 'azertyuiop' à l'aveugle pour stopper le système.")
        httpd.serve_forever()
