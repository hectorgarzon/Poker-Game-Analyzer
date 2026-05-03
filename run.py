"""Entry point for the PokerHero Analyzer development server.

Usage:
    python run.py

The database is created at data/pokerhero.db if it does not already exist.
Override the path with the POKERHERO_DB_PATH environment variable.
Set POKERHERO_DEBUG=true to enable the Werkzeug debugger.
"""

import os
import shutil
import json
import xml.etree.ElementTree as ET
from enum import Enum
from pathlib import Path

import diskcache
from dash import DiskcacheManager

from pokerhero.config import DB_PATH, setup_logging
from pokerhero.database.db import init_db, get_connection, get_setting
from pokerhero.ingestion.pipeline import ingest_directory
from pokerhero.frontend.app import create_app

class PlayerLabel(Enum):
    NONE = ""
    GREEN = "1"
    RED = "2"
    BLUE = "3"
    YELLOW = "4"
    ORANGE = "5"
    PURPLE = "6"

LABEL_MAPPING = {
    "1": "",
    "2": "label2",
    "3": "label3",
    "4": "",
    "5": "pez",
    "6": "label6",
    "": ""
}

def load_player_notes():
    # Copy files of player notes from different sources
    ficheros_notas = [
        "/Users/hector/Library/Application Support/com.barbarysoftware.pokercopilot/playerNotes.xml",
        "/Users/hector/Library/Application Support/PokerStarsES/notes.enygma9999.xml"
    ]
    for f in ficheros_notas:
        ruta_src = Path(f)
        if ruta_src.exists():
            print(f"** copiando fichero {ruta_src} - {ruta_src.name}")
            shutil.copy2(ruta_src, ruta_src.name)

    all_notes = []

    # Procesar notas de Poker Copilot
    copilot_file = Path("playerNotes.xml")
    if copilot_file.exists():
        try:
            tree = ET.parse(copilot_file)
            for player in tree.findall(".//player"):
                note_node = player.find("note")
                label_val = player.get("label", "")
                all_notes.append({
                    "name": player.get("name", ""),
                    "note": note_node.text if note_node is not None and note_node.text else "",
                    "label": LABEL_MAPPING.get(label_val, label_val)
                })
        except Exception as e:
            print(f"Error parseando {copilot_file}: {e}")

    # Procesar notas de PokerStars
    ps_file = Path("notes.enygma9999.xml")
    if ps_file.exists():
        try:
            tree = ET.parse(ps_file)
            for note_el in tree.findall(".//note"):
                label_val = note_el.get("label", "")
                all_notes.append({
                    "name": note_el.get("player", ""),
                    "note": note_el.text if note_el.text else "",
                    "label": LABEL_MAPPING.get(label_val, label_val)
                })
        except Exception as e:
            print(f"Error parseando {ps_file}: {e}")

    # Crear el fichero JSON
    with open("player_notes.json", "w", encoding="utf-8") as f:
        json.dump(all_notes, f, indent=4, ensure_ascii=False)
    # Eliminar los ficheros XML procesados
    for xml_file in ["playerNotes.xml", "notes.enygma9999.xml"]:
        p = Path(xml_file)
        if p.exists():
            p.unlink()

if __name__ == "__main__":
    setup_logging()
    init_db(DB_PATH)

    # Carga automática de archivos en la carpeta 'data/hands'
    hand_dir = Path(os.environ.get("POKERHERO_HANDS_PATH", "/Users/hector/Documents/PokerStarsHands/enygma9999"))
    if hand_dir.exists():
        conn = get_connection(DB_PATH)
        hero = get_setting(conn, "hero_username", default="")
        if hero:
            print(f"Cargando nuevas manos automáticamente desde {hand_dir}...")
            ingest_directory(hand_dir, hero, conn)
            load_player_notes()
        else:
            print("No se pudo cargar automáticamente: 'hero_username' no configurado en la base de datos.")
        conn.close()

    cache_dir = str(DB_PATH.parent / "cache")
    cache = diskcache.Cache(cache_dir)
    manager = DiskcacheManager(cache)
    app = create_app(db_path=DB_PATH, background_callback_manager=manager)
    debug = os.environ.get("POKERHERO_DEBUG", "").lower() == "true"
    app.run(debug=debug)
