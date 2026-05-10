"""Players page — list and filter players."""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any, TypedDict
from dash import Input, Output, State, callback, dash_table, dcc, html
import dash
import pandas as pd
from pokerhero.analysis.stats import classify_player

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
        "padding": "2px 5px",
        "fontSize": "13px",
        "wordBreak": "break-word",
        "minWidth": "80px",  # Ancho mínimo por columna (ajusta según necesidad)
        "width": "80px",     # Ancho fijo por columna
        "maxWidth": "180px",  # Ancho máximo por columna
        "whiteSpace": "normal",  # Permite saltos de línea si el texto es largo
    }
    rows = []
    for _, row in df.iterrows():
        display_name = str(row["username"])
        if row.get("has_note"):
            display_name += " <span style='color: green;'>✎</span>"

        rows.append(
            {
                "id": int(row["id"]),
                "username": display_name,
                "note_text": str(row.get("note_text", "")),
                "label": str(row.get("label", "")).upper(),
                "stakes": str(row.get("stakes", "")),
                "hands_played": int(row["hands_played"]),
                "total_bankroll": round(float(row["total_bankroll"]), 1),
                "days_seen": float(row["days_seen"]),
                "showdown_benefit": round(float(row["showdown_benefit"]), 1),
                "days_since_last_played": int(row["days_since_last_played"]) if pd.notna(row["days_since_last_played"]) else 0,
                "peak_hour": str(row["peak_hour"]) if pd.notna(row["peak_hour"]) else "",
                "peak_hour_days": int(row["peak_hour_days"]) if pd.notna(row["peak_hour_days"]) else 0,
                # Calcula VPIP y PFR (necesitarás estos datos en tu consulta)
                "vpip_pct": float(row.get("vpip_pct", 0)),
                "pfr_pct": float(row.get("pfr_pct", 0)),

                "archetype": row["archetype"]
            }
        )
    return dash_table.DataTable(
        id="player-table",
        columns=[
            {"name": "Type", "id": "archetype"},
            {"name": "Username", "id": "username", "presentation": "markdown"},
            {"name": "Hands", "id": "hands_played"},
            {"name": "Stakes", "id": "stakes"},
            {"name": "His benefit", "id": "total_bankroll"},
            {"name": "Days played", "id": "days_seen"},
            {"name": "Days since last time", "id": "days_since_last_played"},
            {"name": "His benefit when we went to showdown", "id": "showdown_benefit"},
            {"name": "Peak Hour", "id": "peak_hour"},
            {"name": "Days at Peak Hour", "id": "peak_hour_days"},
        ],
        data=rows,
        sort_action="custom",
        style_table={
            "overflowX": "auto",  # Habilita scroll horizontal
            "minWidth": "100%",   # Ancho mínimo del contenedor
        },
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
                # 'fontWeight': 'bold'
            }
        ],
        style_data_conditional=[
            {
                "if": {"filter_query": "{archetype} = 'TAG'"},
                "color": "#006400"
            },
            {
                "if": {"filter_query": "{archetype} = 'LAG'"},
                "color": "#8B0000"
            },
            {
                "if": {"filter_query": "{archetype} = 'Fish'"},
                "color": "#FF8C00"
            },
            {
                "if": {"filter_query": "{archetype} = 'Nit'"},
                "color": "#4682B4"
            }
        ],
        markdown_options={"html": True},
        tooltip_data=[
            {
                "username": {
                    "value": (
                        f"**{r.get('label', '')}**\n{r.get('note_text', '')}"
                        if r.get("label") and r.get("note_text")
                        else f"**{r.get('label', '')}**" if r.get("label")
                        else f"{r.get('note_text', '')}"
                    ).strip(),
                    "type": "markdown"
                }
            } if r.get("note_text") or r.get("label") else {}
            for r in rows
        ],
        tooltip_delay=0,
        tooltip_duration=None,
        css=[{
            "selector": ".dash-table-tooltip",
            "rule": "font-size: 15px; max-width: 400px !important; background-color: #f0fff0;"
        }],
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

    # Cargar notas para marcar jugadores
    notes_path = Path("player_notes.json")
    notes_dict = {}
    if notes_path.exists():
        try:
             with open(notes_path, "r", encoding="utf-8") as f:
                notes_dict = json.load(f)
        except Exception:
            pass
    # Mapear el texto de la nota y marcar si existe
    df["note_text"] = df["username"].map(lambda x: notes_dict.get(x, {}).get("notes", ""))
    df["label"] = df["username"].map(lambda x: notes_dict.get(x, {}).get("label", ""))
    df["has_note"] = (df["note_text"] != "") | (df["label"] != "")

    # Calcular arquetipo aquí para que esté disponible en el Store y filtros
    df["archetype"] = df.apply(
        lambda r: classify_player(
            float(r.get("vpip_pct", 0)),
            float(r.get("pfr_pct", 0)),
            int(r["hands_played"]),
            min_hands=15
        ), axis=1
    )
    _input_style = {
        "border": "1px solid var(--border, #ddd)",
        "borderRadius": "4px",
        "padding": "4px 4px",
        "fontSize": "13px",
        "height": "30px",
    }

    # Obtener opciones de stakes para el dropdown inicial
    all_stakes = set()
    for s_val in df["stakes"].dropna():
        all_stakes.update([s.strip() for s in str(s_val).split(",")])
    stakes_options = [{"label": s, "value": s} for s in sorted(all_stakes)]

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
                        style={**_input_style, "width": "40px"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center"}
            ),
            html.Div(
                [
                    html.Span("Min Days played:", style={"fontSize": "13px", "marginRight": "5px"}),
                    dcc.Input(
                        id="player-filter-min-days",
                        type="number",
                        placeholder="0",
                        min=0,
                        debounce=True,
                        style={**_input_style, "width": "40px"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center"}
            ),
            html.Div(
            [
                html.Span("Max days since last time:", style={"fontSize": "13px", "marginRight": "5px"}),
                dcc.Input(
                    id="player-filter-max-days",
                    type="number",
                    placeholder="",
                    min=0,
                    debounce=True,
                    style={**_input_style, "width": "40px"},
                ),
            ],
            style={"display": "flex", "alignItems": "center"}
            ),
            html.Div(
                [
                    dcc.Checklist(
                        id="player-filter-has-notes",
                        options=[{"label": " Solo con notas", "value": "has_notes"}],
                        style={"fontSize": "13px", "marginLeft": "5px"}
                    ),
                ],
                style={"display": "flex", "alignItems": "center"}
            ),
            html.Div(
            [
                html.Span("Type:", style={"fontSize": "13px", "marginRight": "5px"}),
                dcc.Dropdown(
                    id="player-filter-type",
                    options=[
                        # {"label": "All", "value": "all"},
                        {"label": "TAG", "value": "TAG"},
                        {"label": "LAG", "value": "LAG"},
                        {"label": "Fish", "value": "Fish"},
                        {"label": "Nit", "value": "Nit"},
                    ],
                    placeholder="All types...",
                    clearable=True,
                    style={**_input_style, "width": "120px"},
                ),
            ],
            style={"display": "flex", "alignItems": "center"}
            ),
            html.Div(
                [
                    html.Span("Stakes:", style={"fontSize": "13px", "marginRight": "5px"}),
                    dcc.Dropdown(
                        id="player-filter-stakes",
                        options=stakes_options,
                        multi=True,
                        placeholder="Todos los stakes...",
                        style={**_input_style, "width": "200px", "minWidth": "200px"}
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
                    "marginLeft": "auto"
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
    Output("player-table", "tooltip_data"),
    Output("player-filter-stakes", "options"),
    Input("player-filter-username", "value"),
    Input("player-filter-min-hands", "value"),
    Input("player-filter-min-days", "value"),
    Input("player-filter-max-days", "value"),
    Input("player-filter-has-notes", "value"),
    Input("player-filter-stakes", "value"),
    Input("player-filter-type", "value"), 
    Input("player-table", "sort_by"),
    State("player-data-store", "data"),
    prevent_initial_call=True,
)
def _apply_player_filters(
    username: str | None,
    min_hands: int | None,
    min_days: int | None,
    max_days: int | None,
    has_notes: list[str] | None,
    stakes_filter: list[str] | None,
    type_filter: str | None,
    sort_by: list[dict[str, str]] | None,
    data: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    if not data:
        raise dash.exceptions.PreventUpdate

    df = pd.DataFrame(data)

    # Aplica filtros existentes
    if username:
        parts = username.split()
        if parts:
            pattern = "|".join(parts)
            df = df[df["username"].str.contains(pattern, case=False, na=False)]

    if min_hands is not None:
        df = df[df["hands_played"] >= min_hands]

    if min_days is not None:
        df = df[df["days_seen"] >= min_days]

    if max_days is not None:
        df = df[df["days_since_last_played"] <= max_days]

    if has_notes and "has_notes" in has_notes:
        df = df[df["has_note"] == True]

    # Filtro de stakes
    if stakes_filter:
        df["stakes_list"] = df["stakes"].str.split(", ")
        df = df[df["stakes_list"].apply(lambda x: any(stake in x for stake in stakes_filter))]
    
    # Filtro de tipo (archetype)
    if type_filter and type_filter != "all":
        df = df[df["archetype"] == type_filter]
    
    # Ordenación
    if sort_by:
        df = df.sort_values(
            [col["column_id"] for col in sort_by],
            ascending=[col["direction"] == "asc" for col in sort_by],
        )

    # Obtener opciones de stakes para el dropdown
    all_stakes = set()
    for row in data:
        if row.get("stakes"):
            # Dividimos los stakes por comas y eliminamos espacios
            stakes_list = [s.strip() for s in row["stakes"].split(",")]
            all_stakes.update(stakes_list)

    # Ordenamos y creamos las opciones
    stakes_options = [{"label": stake, "value": stake} for stake in sorted(all_stakes)]

    # Reconstruye la tabla
    table = _build_player_table(df)
    return table.data, table.tooltip_data, stakes_options

@callback(
    Output("player-filter-username", "value"),
    Output("player-filter-min-hands", "value"),
    Output("player-filter-min-days", "value"),
    Output("player-filter-max-days", "value"),
    Output("player-filter-has-notes", "value"),
    Output("player-filter-stakes", "value"),
    Output("player-filter-type", "value"),
    Input("player-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)
def clear_filters(n_clicks: int) -> tuple[None, None, None, None, None, None, None]:
    """Limpia todos los filtros de la página de Players."""
    return None, None, None, None, None, None, None

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

    # Obtiene el id de la fila pulsada
    player_id = table_data[active_cell["row"]]["id"]
    return f"/player/{player_id}"