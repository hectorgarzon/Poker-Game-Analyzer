"""Players page — list and filter players."""

from __future__ import annotations

import sqlite3
from typing import Any, TypedDict
from dash import Input, Output, State, callback, dash_table, dcc, html
import dash
import pandas as pd

from pokerhero.database.db import get_connection, get_setting, upsert_player

dash.register_page(__name__, path="/players", name="Players")

class _PlayerRow(TypedDict):
    """One player's data."""
    id: int
    username: str
    hands_played: int
    # Agrega otros campos que necesites

# Estilos (igual que en sessions.py)
_TH = {
    "background": "#0074D9",
    "color": "#fff",
    "padding": "10px 12px",
    "textAlign": "left",
    "fontWeight": "600",
    "fontSize": "13px",
}

_TD = {
        "padding": "6px 8px",
        "borderBottom": "1px solid var(--border-light, #eee)",
        "fontSize": "13px",
        "maxWidth": "80px",
        "whiteSpace": "normal",
        "wordBreak": "break-word"
    }

# Layout
layout = html.Div(
    style={
        "fontFamily": "sans-serif",
        "maxWidth": "1000px",
        "margin": "40px auto",
        "padding": "0 20px",
    },
    children=[
        html.H2("👥 Players"),
        dcc.Link(
            "← Back to Home",
            href="/",
            style={"fontSize": "13px", "color": "#0074D9"},
        ),
        html.Hr(),
        html.Div(id="player-filter-container", style={"marginBottom": "12px"}),
        dcc.Loading(html.Div(id="player-table-container")),
        dcc.Store(id="player-data-store"),
    ],
)

def _get_hero_player_id(db_path: str) -> int | None:
    if db_path == ":memory:":
        return None
    conn = get_connection(db_path)
    try:
        username = get_setting(conn, "hero_username", default="")
        return upsert_player(conn, username) if username else None
    finally:
        conn.close()

def _get_db_path() -> str:
    result: str = dash.get_app().server.config.get("DB_PATH", ":memory:")
    return result

def _build_player_table(df: pd.DataFrame) -> Any:
    """Render a filtered players DataFrame as a sortable DataTable."""
    _col_style = {
        "textAlign": "left",
        "padding": "8px 12px",
        "fontSize": "14px",
        "maxWidth": "80px",
        "whiteSpace": "normal",
        "wordBreak": "break-word"
    }
    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "hands_played": int(row["hands_played"]),
                "total_bankroll": float(row["total_bankroll"]),
                "days_seen": float(row["days_seen"]),
                "max_win_showdown": float(row["max_win_showdown"]),
                "last_played_date": str(row["last_played_date"]) if pd.notna(row["last_played_date"]) else "",
                "peak_hour": str(row["peak_hour"]) if pd.notna(row["peak_hour"]) else "",
                "peak_hour_days": int(row["peak_hour_days"]) if pd.notna(row["peak_hour_days"]) else 0,
            }
        )
    return dash_table.DataTable(
        id="player-table",
        columns=[
            {"name": "Username", "id": "username"},
            {"name": "Hands", "id": "hands_played"},
            {"name": "Benefit", "id": "total_bankroll"},
            {"name": "Days played", "id": "days_seen"},
            {"name": "Last Played", "id": "last_played_date"},
            {"name": "Max win when showdown", "id": "max_win_showdown"},
            {"name": "Peak Hour", "id": "peak_hour"},
            {"name": "Days at Peak Hour", "id": "peak_hour_days"},
        ],
        data=rows,
        sort_action="native",
        style_table={"width": "100%", "overflowX": "auto"},
        style_header={
            "backgroundColor": "#0074D9",
            "color": "white",
            "fontWeight": "bold",
            "padding": "8px 12px",
            "fontSize": "13px",
            "textAlign": "left",
        },
        style_cell=_col_style,
        style_as_list_view=True,
        row_selectable=False,
        cell_selectable=True,
        page_action="none",
    )

def _render_players(db_path: str) -> html.Div | str:
    """Render the players list view."""
    if db_path == ":memory:":
        return html.Div("⚠️ No database connected.", style={"color": "orange"})

    player_id = _get_hero_player_id(db_path)
    if player_id is None:
        return html.Div(
            "⚠️ No hero username set. Please set it on the Upload page first.",
            style={"color": "orange"},
        )

    from pokerhero.analysis.queries import get_players 

    conn = get_connection(db_path)
    try:
        df = get_players(conn,player_id)
    finally:
        conn.close()

    if df.empty:
        return html.Div("No players found.")

    _input_style = {
        "border": "1px solid var(--border, #ddd)",
        "borderRadius": "4px",
        "padding": "4px 8px",
        "fontSize": "13px",
        "height": "30px",
    }

    filter_bar = html.Div(
        [
            dcc.Input(
                id="player-filter-username",
                type="text",
                placeholder="Search by username...",
                debounce=True,
                style={**_input_style, "minWidth": "200px"},
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "gap": "8px",
            "flexWrap": "wrap",
            "marginBottom": "12px",
            "padding": "8px 10px",
            "background": "var(--bg-2, #f8f9fa)",
            "borderRadius": "6px",
            "border": "1px solid var(--border, #e0e0e0)",
        },
    )

    return html.Div(
        [
            filter_bar,
            _build_player_table(df),
            dcc.Store(id="player-data-store", data=df.to_dict("records")),
        ]
    )

@callback(
    Output("player-filter-container", "children"),
    Output("player-table-container", "children"),
    Input("_pages_location", "pathname"),
    prevent_initial_call=False,
)
def _render(pathname: str) -> tuple[html.Div, html.Div | str]:
    if pathname != "/players":
        raise dash.exceptions.PreventUpdate
    db_path = _get_db_path()
    content = _render_players(db_path)
    return html.Div(), content

@callback(
    Output("player-table", "data"),
    Input("player-filter-username", "value"),
    State("player-data-store", "data"),
    prevent_initial_call=True,
)
def _apply_player_filters(
    username: str | None,
    data: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not data:
        raise dash.exceptions.PreventUpdate
    df = pd.DataFrame(data)
    
    if username:
        df = df[df["username"].str.contains(username, case=False, na=False)]
    
    return list(_build_player_table(df).data)
