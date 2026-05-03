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
                "total_bankroll": round(float(row["total_bankroll"]), 1),
                "days_seen": float(row["days_seen"]),
                "max_win_showdown": round(float(row["max_win_showdown"]), 1),
                "days_since_last_played": int(row["days_since_last_played"]) if pd.notna(row["days_since_last_played"]) else 0,
                "peak_hour": str(row["peak_hour"]) if pd.notna(row["peak_hour"]) else "",
                "peak_hour_days": int(row["peak_hour_days"]) if pd.notna(row["peak_hour_days"]) else 0,
            }
        )
    return dash_table.DataTable(
        id="player-table",
        columns=[
            {"name": "Username", "id": "username"},
            {"name": "Hands", "id": "hands_played"},
            {"name": "His benefit", "id": "total_bankroll"},
            {"name": "Days played", "id": "days_seen"},
            {"name": "Days since last time", "id": "days_since_last_played"},
            {"name": "His benefit when we went to showdown", "id": "max_win_showdown"},
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
        style_cell_conditional=[
            {
                'if': {'column_id': 'username'},
                'cursor': 'pointer',
                'color': '#0074D9'
            }
        ],
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
            html.Div(
                [
                    html.Span("Username:", style={"fontSize": "13px", "marginRight": "5px"}),
                    dcc.Input(
                        id="player-filter-username",
                        type="text",
                        placeholder="name...",
                        debounce=True,
                        style={**_input_style, "width": "150px"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center"}
            ),
            html.Div(
                [
                    html.Span("Min Hands:", style={"fontSize": "13px", "marginRight": "5px"}),
                    dcc.Input(
                        id="player-filter-min-hands",
                        type="number",
                        placeholder="0",
                        min=0,
                        debounce=True,
                        style={**_input_style, "width": "80px"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center"}
            ),
            html.Div(
                [
                    html.Span("Min Days:", style={"fontSize": "13px", "marginRight": "5px"}),
                    dcc.Input(
                        id="player-filter-min-days",
                        type="number",
                        placeholder="0",
                        min=0,
                        debounce=True,
                        style={**_input_style, "width": "80px"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center"}
            ),
            html.Button(
                "Limpiar filtros",
                id="player-clear-filters",
                style={
                    **_input_style,
                    "width": "auto",
                    "backgroundColor": "#f8f9fa",
                    "border": "1px solid #ced4da",
                    "color": "#495057",
                    "cursor": "pointer",
                    "padding": "4px 12px",
                    "marginLeft": "auto"  # Empuja el botón a la derecha
                }
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "gap": "20px",
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
    Input("player-filter-min-hands", "value"),
    Input("player-filter-min-days", "value"),
    State("player-data-store", "data"),
    prevent_initial_call=True,
)
def _apply_player_filters(
    username: str | None,
    min_hands: int | None,
    min_days: int | None,
    data: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not data:
        raise dash.exceptions.PreventUpdate
    df = pd.DataFrame(data)

    if username:
        parts = username.split()
        if parts:
            pattern = "|".join(parts)
            df = df[df["username"].str.contains(pattern, case=False, na=False)]

    if min_hands is not None:
        df = df[df["hands_played"] >= min_hands]

    if min_days is not None:
        df = df[df["days_seen"] >= min_days]

    return list(_build_player_table(df).data)

@callback(
    Output("player-filter-username", "value"),
    Output("player-filter-min-hands", "value"),
    Output("player-filter-min-days", "value"),
    Input("player-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)
def clear_filters(n_clicks: int) -> tuple[None, None, None]:
    """Limpia todos los filtros de la página de Players."""
    return None, None, None

@callback(
    Output("_pages_location", "href"),
    Input("player-table", "active_cell"),
    State("player-table", "data"),
    prevent_initial_call=True,
)
def navigate_to_player_detail(active_cell, table_data):
    """Captura el clic en la tabla y redirige a la página de detalle del jugador."""
    if not active_cell:
        raise dash.exceptions.PreventUpdate

    # Obtiene el username de la fila pulsada
    player_username = table_data[active_cell["row"]]["username"]
    return f"/player/{player_username}"