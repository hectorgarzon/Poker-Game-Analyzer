"""Entry point for the PokerHero Analyzer development server.

Usage:
    python run.py

The database is created at data/pokerhero.db if it does not already exist.
Override the path with the POKERHERO_DB_PATH environment variable.
Set POKERHERO_DEBUG=true to enable the Werkzeug debugger.
"""

import os
from pathlib import Path

import diskcache
from dash import DiskcacheManager

from pokerhero.config import DB_PATH, setup_logging
from pokerhero.database.db import init_db, get_connection, get_setting
from pokerhero.ingestion.pipeline import ingest_directory
from pokerhero.frontend.app import create_app

if __name__ == "__main__":
    setup_logging()
    init_db(DB_PATH)

    # Carga automática de archivos en la carpeta 'data/hands'
    hand_dir = Path(os.environ.get("POKERHERO_HANDS_PATH", "/Users/hector/Documents/PokerStarsHands/enygma9999"))
    if hand_dir.exists():
        conn = get_connection(DB_PATH)
        hero = get_setting(conn, "hero_username", default="")
        if hero:
            print(f"Cargando manos automáticamente desde {hand_dir}...")
            ingest_directory(hand_dir, hero, conn)
        else:
            print("No se pudo cargar automáticamente: 'hero_username' no configurado en la base de datos.")
        conn.close()

    cache_dir = str(DB_PATH.parent / "cache")
    cache = diskcache.Cache(cache_dir)
    manager = DiskcacheManager(cache)
    app = create_app(db_path=DB_PATH, background_callback_manager=manager)
    debug = os.environ.get("POKERHERO_DEBUG", "").lower() == "true"
    app.run(debug=debug)
