from __future__ import annotations

import dash
import pandas as pd
from dash import html, dash_table, dcc
from pokerhero.database.db import get_connection, get_setting, upsert_player

dash.register_page(__name__, path="/hands", name="Lista de Manos")

_SUIT_SYMBOLS = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}

def _format_cards_text(cards_str: str | None) -> str:
    """Formatea las cartas con símbolos de palos."""
    if not cards_str:
        return "—"
    parts = []
    for card in str(cards_str).split():
        if len(card) >= 2:
            rank = card[:-1]
            suit = _SUIT_SYMBOLS.get(card[-1].lower(), card[-1])
            parts.append(f"{rank}{suit}")
    return " ".join(parts) if parts else "—"

def layout() -> html.Div:
    db_path = dash.get_app().server.config.get("DB_PATH", ":memory:")
    conn = get_connection(db_path)
    try:
        username = get_setting(conn, "hero_username", default="")
        hero_id = upsert_player(conn, username) if username else None

        if hero_id is None:
            return html.Div("Configure el usuario Hero en la página de ajustes primero.")

        # Consulta con JOIN a sessions para obtener la fecha
        df = pd.read_sql("""
            SELECT s.start_time, h.id, h.source_hand_id, hp.hole_cards, h.total_pot, hp.net_result
            FROM hands h
            JOIN hand_players hp ON h.id = hp.hand_id
            JOIN sessions s ON h.session_id = s.id
            WHERE hp.player_id = ?
            ORDER BY s.start_time DESC, h.id DESC
        """, conn, params=(hero_id,))
    finally:
        conn.close()

    rows = []
    for _, row in df.iterrows():
        pnl = float(row["net_result"]) if row["net_result"] is not None else 0.0
        date_val = row["start_time"].replace("T", " ")[:16] if row["start_time"] else "-"
        rows.append({
            "id": int(row["id"]),
            "date": date_val,
            "hand_num": str(row["source_hand_id"]),
            "hole_cards": _format_cards_text(row["hole_cards"]),
            "pot": f"{float(row['total_pot']):,.6g}",
            "_pnl_raw": pnl,
        })

    return html.Div([
        html.H2("🃏 Hands"),
        dcc.Link(
            "← Back to Home",
            href="/",
            style={"fontSize": "13px", "color": "#0074D9"},
        ),
        html.Hr(),
        dash_table.DataTable(
            id="all-hands-table",
            columns=[
                {"name": "Date", "id": "date"},
                {"name": "Hand #", "id": "hand_num"},
                {"name": "Hero Cards", "id": "hole_cards"},
                {"name": "Pot", "id": "pot"},
                {"name": "Hero benefit", "id": "_pnl_raw", "type": "numeric"},
            ],
            data=rows,
            sort_action="native",
            sort_by=[{"column_id": "date", "direction": "desc"}],
            style_as_list_view=True,
            style_header={
                "backgroundColor": "#0074D9",
                "color": "white",
                "fontWeight": "bold",
                "padding": "10px",
            },
            style_cell={
                "textAlign": "left",
                "padding": "10px",
                "fontSize": "14px",
                "fontFamily": "sans-serif",
            },
            style_data_conditional=[
                {
                    "if": {"filter_query": "{_pnl_raw} >= 0", "column_id": "_pnl_raw"},
                    "color": "#2ecc71", "fontWeight": "600",
                },
                {
                    "if": {"filter_query": "{_pnl_raw} < 0", "column_id": "_pnl_raw"},
                    "color": "#e74c3c", "fontWeight": "600",
                },
            ],
        )
    ], style={"maxWidth": "1000px", "margin": "40px auto", "padding": "0 20px"})