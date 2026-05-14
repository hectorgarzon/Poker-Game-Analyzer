from __future__ import annotations

import dash
import pandas as pd
from pathlib import Path
from dash import html, dash_table, dcc, Input, Output, State, callback
from pokerhero.database.db import get_connection, get_setting, upsert_player, toggle_hand_favorite

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

def _has_ai_report(source_hand_id: str, hand_id: int) -> str:
    """Devuelve '📄' si existe el archivo de análisis de IA, '' si no."""
    ai_dir = Path("ai_analysis")
    filename = f"{source_hand_id}-{hand_id}.txt"
    filepath = ai_dir / filename
    return "📄" if filepath.exists() else ""

def layout(session_id: str | None = None) -> html.Div:
    db_path = dash.get_app().server.config.get("DB_PATH", ":memory:")
    conn = get_connection(db_path)
    header_text = "🃏 Hands"
    try:
        username = get_setting(conn, "hero_username", default="")
        hero_id = upsert_player(conn, username) if username else None
        if hero_id is None:
            return html.Div("Configure el usuario Hero en la página de ajustes primero.")

        sql = """
            SELECT s.start_time, h.id, h.source_hand_id, h.is_favorite, hp.hole_cards, h.total_pot, hp.net_result
            FROM hands h
            JOIN hand_players hp ON h.id = hp.hand_id
            JOIN sessions s ON h.session_id = s.id
            WHERE hp.player_id = ?
        """
        params = [hero_id]
        if session_id:
            sql += " AND h.session_id = ?"
            params.append(int(session_id))
        sql += " ORDER BY s.start_time DESC, h.id DESC"

        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()

    # Procesamiento de datos (igual que antes)
    rows = []
    for _, row in df.iterrows():
        pnl = float(row["net_result"]) if row["net_result"] is not None else 0.0
        date_val = row["start_time"].replace("T", " ")[:16] if row["start_time"] else "-"
        is_fav = "★" if row["is_favorite"] else "☆"
        source_hand_id = str(row["source_hand_id"])
        hand_id = int(row["id"])
        ai_report_icon = _has_ai_report(source_hand_id, hand_id)
        rows.append({
            "id": hand_id,
            "favorite": is_fav,
            "date": date_val,
            "hand_num": source_hand_id,
            "hole_cards": _format_cards_text(row["hole_cards"]),
            "_pnl_raw": pnl,
            "ai_report": ai_report_icon,
        })

    # Estilo para los filtros
    _input_style = {
        "border": "1px solid var(--border, #ddd)",
        "borderRadius": "4px",
        "padding": "4px 4px",
        "fontSize": "13px",
        "height": "30px",
    }

    # Sección de filtros
    filter_section = html.Div(
        [
            html.Div(
                [
                    dcc.Checklist(
                        id="hands-filter-favorites",
                        options=[{"label": " Solo favoritas", "value": "favorites"}],
                        style={"fontSize": "13px", "marginRight": "20px"}
                    ),
                ],
                style={"display": "flex", "alignItems": "center"}
            ),
            html.Div(
                [
                    dcc.Checklist(
                        id="hands-filter-ai-reports",
                        options=[{"label": " Solo con análisis de IA", "value": "ai_reports"}],
                        style={"fontSize": "13px"}
                    ),
                ],
                style={"display": "flex", "alignItems": "center"}
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

    return html.Div([
        dcc.Location(id="url-hands"),
        html.H2(header_text),
        dcc.Link(
            "← Back to Home", href="/", style={"fontSize": "13px", "color": "#0074D9"},
        ),
        html.Hr(),
        filter_section,  # Añadido aquí
        dcc.Store(id="hands-data-store", data=rows),
        dash_table.DataTable(
            id="all-hands-table",
            columns=[
                {
                    "name": "Fav",
                    "id": "favorite",
                    "type": "text",
                    "presentation": "markdown"
                },
                {"name": "Date", "id": "date"},
                {"name": "Hand #", "id": "hand_num"},
                {"name": "Hero cards", "id": "hole_cards"},
                {"name": "Hero benefit", "id": "_pnl_raw", "type": "numeric"},
                {"name": "AI Report", "id": "ai_report", "type": "text", "presentation": "markdown"},
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
                    "color": "#2ecc71",
                    "fontWeight": "600",
                },
                {
                    "if": {"filter_query": "{_pnl_raw} < 0", "column_id": "_pnl_raw"},
                    "color": "#e74c3c",
                    "fontWeight": "600",
                },
                {
                    "if": {"filter_query": "{favorite} = '★'", "column_id": "favorite"},
                    "color": "#f5a623",
                    "fontSize": "18px",
                    "fontWeight": "bold",
                },
                {
                    "if": {"filter_query": "{favorite} = '☆'", "column_id": "favorite"},
                    "color": "#aaa",
                    "fontSize": "18px",
                },
                { "if": {"column_id": "ai_report"}, "color": "#6c5ce7", "fontSize": "16px", "textAlign": "center", "fontWeight": "bold" },
            ],
        )
    ], style={"maxWidth": "1000px", "margin": "40px auto", "padding": "0 20px"})

@callback(
    Output("all-hands-table", "data"),
    Output("_pages_location", "href", allow_duplicate=True),
    Input("hands-filter-favorites", "value"),
    Input("hands-filter-ai-reports", "value"),
    Input("all-hands-table", "active_cell"),
    State("all-hands-table", "data"),
    State("url-hands", "search"),  # Para obtener el session_id si viene de sessions
    prevent_initial_call=True,
)
def update_hands_table(
    favorites_filter,
    ai_reports_filter,
    active_cell,
    table_data,
    search
):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    # Obtener el ID del trigger
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    # Si el trigger es un clic en la tabla
    if trigger_id == "all-hands-table" and active_cell:
        if not table_data or not active_cell:
            raise dash.exceptions.PreventUpdate

        # Si es clic en la columna de favoritos
        if active_cell["column_id"] == "favorite":
            hand_id = table_data[active_cell["row"]]["id"]
            is_fav_now = table_data[active_cell["row"]]["favorite"] == "★"

            # Toggle en la base de datos
            db_path = dash.get_app().server.config.get("DB_PATH", ":memory:")
            conn = get_connection(db_path)
            try:
                toggle_hand_favorite(conn, hand_id)
                conn.commit()
                # Refrescar el estado de favorito
                is_fav = conn.execute(
                    "SELECT is_favorite FROM hands WHERE id = ?", (hand_id,)
                ).fetchone()[0]
                table_data[active_cell["row"]]["favorite"] = "★" if is_fav else "☆"
            finally:
                conn.close()

            return table_data, dash.no_update

        # Si es clic en cualquier otra columna, navegar a la página de la mano
        else:
            hand_id = table_data[active_cell["row"]]["id"]

            # Verificar si viene de sessions (tiene parámetro session_id)
            session_id = None
            origin = "hands"  # Valor por defecto

            if search and "session_id=" in search:
                session_id = search.split("session_id=")[1].split("&")[0]
                origin = "sessions"

            # Construir la URL con los parámetros necesarios
            if session_id:
                return dash.no_update, f"/hand/{hand_id}?session_id={session_id}&origin={origin}"
            else:
                return dash.no_update, f"/hand/{hand_id}?origin={origin}"

    # Si el trigger es un cambio en los filtros
    elif trigger_id in ["hands-filter-favorites", "hands-filter-ai-reports"]:
        if not table_data:
            raise dash.exceptions.PreventUpdate

        df = pd.DataFrame(table_data)

        # Aplicar filtros
        if favorites_filter and "favorites" in favorites_filter:
            df = df[df["favorite"] == "★"]

        if ai_reports_filter and "ai_reports" in ai_reports_filter:
            df = df[df["ai_report"] == "📄"]

        return df.to_dict("records"), dash.no_update

    raise dash.exceptions.PreventUpdate