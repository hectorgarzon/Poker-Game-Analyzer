"""Player detail page - shows information about a specific player."""

from dash import html, dcc, register_page, dash_table
import dash
import pandas as pd
from pokerhero.database.db import get_connection, get_setting, upsert_player

register_page(__name__, path_template="/player/<player_id>")

# Data we are showing here
# Sessions the player played (so that we can see usual times and days. We can show the day of the week for each session)
# Leaks of the player, or the type of player
# Hands played


def _get_db_path() -> str:
    return dash.get_app().server.config.get("DB_PATH", ":memory:")

def layout(player_id: str = None, **kwargs):
    """Render the player detail page."""
    if player_id is None:
        return html.Div("Jugador no encontrado", style={"color": "red"})

    db_path = _get_db_path()
    conn = get_connection(db_path)

    # Obtener Hero ID
    hero_username = get_setting(conn, "hero_username", default="")
    hero_id = upsert_player(conn, hero_username) if hero_username else -1

    row = conn.execute("SELECT username FROM players WHERE id = ?", (player_id,)).fetchone()

    # Obtener las manos y resultados del jugador y del Hero
    hands_query = """
        SELECT
            h.source_hand_id as hand_id,
            hp.net_result,
            COALESCE(hp_hero.net_result, 0) as hero_net_result
        FROM hand_players hp
        JOIN hands h ON hp.hand_id = h.id
        LEFT JOIN hand_players hp_hero ON h.id = hp_hero.hand_id AND hp_hero.player_id = ?
        WHERE hp.player_id = ?
    """
    df_hands = pd.read_sql_query(hands_query, conn, params=(hero_id, player_id))
    conn.close()

    username = row[0] if row else "Desconocido"

    return html.Div(
        style={
            "fontFamily": "sans-serif",
            "maxWidth": "1000px",
            "margin": "40px auto",
            "padding": "0 20px",
        },
        children=[
            html.H2(f"👤 Detalles del Jugador: {username}"),
            dcc.Link(
                "← Volver a Players",
                href="/players",
                style={"fontSize": "13px", "color": "#0074D9"},
            ),
            html.Hr(),
            html.Div(id="player-detail-content", children=[
                html.H4("Historial de Manos", style={"marginTop": "30px"}),
                dash_table.DataTable(
                    id="player-hands-table",
                    columns=[
                        {"name": "ID Mano", "id": "hand_id"},
                        {"name": "Net Result", "id": "net_result", "type": "numeric"},
                        {"name": "Hero Result", "id": "hero_net_result", "type": "numeric"},
                    ],
                    data=df_hands.to_dict("records"),
                    sort_action="native",
                    page_action="native",
                    page_size=100,
                    style_header={
                        "backgroundColor": "#0074D9",
                        "color": "white",
                        "fontWeight": "bold",
                        "textAlign": "left",
                        "padding": "10px",
                    },
                    style_cell={
                        "textAlign": "left",
                        "padding": "10px",
                        "fontSize": "13px",
                    },
                    style_data_conditional=[
                        {
                            "if": {"filter_query": "{net_result} >= 0", "column_id": "net_result"},
                            "color": "green",
                            "fontWeight": "bold",
                        },
                        {
                            "if": {"filter_query": "{net_result} < 0", "column_id": "net_result"},
                            "color": "red",
                            "fontWeight": "bold",
                        },
                        {
                            "if": {"filter_query": "{hero_net_result} >= 0", "column_id": "hero_net_result"},
                            "color": "green",
                            "fontWeight": "bold",
                        },
                        {
                            "if": {"filter_query": "{hero_net_result} < 0", "column_id": "hero_net_result"},
                            "color": "red",
                            "fontWeight": "bold",
                        },
                    ],
                ),
            ]),
        ],
    )