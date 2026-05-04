"""Player detail page - shows information about a specific player."""

from dash import html, dcc, register_page, dash_table, callback, Input, Output, State
import dash
import pandas as pd
from pokerhero.database.db import get_connection, get_setting, upsert_player

register_page(__name__, path_template="/player/<player_id>")

_SECTION_STYLE = {
    "marginBottom": "32px",
    "padding": "20px",
    "border": "1px solid var(--border, #e0e0e0)",
    "borderRadius": "8px",
    "background": "var(--bg-2, #fafafa)",
}

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
            COALESCE(hp_hero.net_result, 0) as hero_net_result,
            CASE WHEN hp.went_to_showdown = 1 AND hp_hero.went_to_showdown = 1 THEN '✓' ELSE '' END as both_showdown
        FROM hand_players hp
        JOIN hands h ON hp.hand_id = h.id
        LEFT JOIN hand_players hp_hero ON h.id = hp_hero.hand_id AND hp_hero.player_id = ?
        WHERE hp.player_id = ?
    """
    df_hands = pd.read_sql_query(hands_query, conn, params=(hero_id, player_id))

    # Obtener sesiones del jugador
    sessions_query = """
        SELECT
            s.id,
            REPLACE(s.start_time, 'T', ' ') AS start_time,
            COUNT(h.id) AS hands_played,
            ROUND(COALESCE(SUM(hp.net_result), 0), 2) AS net_profit
        FROM sessions s
        JOIN hands h ON h.session_id = s.id
        JOIN hand_players hp ON hp.hand_id = h.id AND hp.player_id = ?
        GROUP BY s.id
        ORDER BY s.start_time DESC
    """
    df_sessions = pd.read_sql_query(sessions_query, conn, params=(player_id,))
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
                 html.Div(
                    style=_SECTION_STYLE,
                    children=[
                        html.Div(
                            style={"fontSize": "16px", "fontWeight": "bold", "display": "flex", "gap": "40px"},
                            children=[
                                html.Div([
                                    "His benefit: ",
                                    html.Span(
                                        f"{df_hands['net_result'].sum():.1f}",
                                        style={"color": "green" if df_hands['net_result'].sum() >= 0 else "red"}
                                    )
                                ]),
                                html.Div([
                                    "Hero benefit: ",
                                    html.Span(
                                        f"{df_hands['hero_net_result'].sum():.1f}",
                                        style={"color": "green" if df_hands['hero_net_result'].sum() >= 0 else "red"}
                                    )
                                ]),
                            ]
                        ),
                    ]
                ),
                html.Div(
                    style=_SECTION_STYLE,
                    children=[
                        html.Details([
                            html.Summary(
                                "Sessions",
                                style={"fontSize": "18px", "fontWeight": "bold", "cursor": "pointer"}
                            ),
                            html.Div(
                                style={"paddingTop": "20px"},
                                children=[
                                    dash_table.DataTable(
                                        id="player-sessions-table",
                                        columns=[
                                            {"name": "Date", "id": "start_time"},
                                            {"name": "Hands", "id": "hands_played"},
                                            {"name": "Net profit", "id": "net_profit", "type": "numeric"},
                                        ],
                                        data=df_sessions.to_dict("records"),
                                        sort_action="native",
                                        page_action="native",
                                        page_size=20,
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
                                                "if": {"filter_query": "{net_profit} >= 0", "column_id": "net_profit"},
                                                "color": "green",
                                                "fontWeight": "bold",
                                            },
                                            {
                                                "if": {"filter_query": "{net_profit} < 0", "column_id": "net_profit"},
                                                "color": "red",
                                                "fontWeight": "bold",
                                            },
                                        ],
                                    ),
                                ]
                            )
                        ], open=False),
                    ]
                ),
                html.Div(
                    style=_SECTION_STYLE,
                    children=[
                        html.Details([
                            html.Summary(
                                "Hands",
                                style={"fontSize": "18px", "fontWeight": "bold", "cursor": "pointer"}
                            ),
                            html.Div(
                                style={"paddingTop": "20px"},
                                children=[
                                    dcc.Checklist(
                                        id="player-showdown-filter",
                                        options=[{"label": " Solo manos con Showdown vs Hero", "value": "only_sd"}],
                                        style={"marginBottom": "10px", "fontSize": "14px"}
                                    ),
                                    dcc.Store(id="player-id-store", data=player_id),
                                    dash_table.DataTable(
                                        id="player-hands-table",
                                        columns=[
                                            {"name": "ID Mano", "id": "hand_id"},
                                            {"name": "Net Result", "id": "net_result", "type": "numeric"},
                                            {"name": "Hero Result", "id": "hero_net_result", "type": "numeric"},
                                            # {"name": "SD vs Hero", "id": "both_showdown"},
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
                                ]
                            )
                        ], open=False),
                    ]
                ),
            ]),
        ],
    )

@callback(
    Output("player-hands-table", "data"),
    Input("player-showdown-filter", "value"),
    State("player-id-store", "data"),
    prevent_initial_call=True
)
def _filter_player_hands(showdown_filter, player_id):
    if player_id is None:
        return []

    db_path = _get_db_path()
    conn = get_connection(db_path)
    hero_username = get_setting(conn, "hero_username", default="")
    hero_id = upsert_player(conn, hero_username) if hero_username else -1

    query = """
        SELECT
            h.source_hand_id as hand_id,
            hp.net_result,
            COALESCE(hp_hero.net_result, 0) as hero_net_result,
            CASE WHEN hp.went_to_showdown = 1 AND hp_hero.went_to_showdown = 1 THEN '✓' ELSE '' END as both_showdown
        FROM hand_players hp
        JOIN hands h ON hp.hand_id = h.id
        LEFT JOIN hand_players hp_hero ON h.id = hp_hero.hand_id AND hp_hero.player_id = ?
        WHERE hp.player_id = ?
    """
    df = pd.read_sql_query(query, conn, params=(hero_id, player_id))
    conn.close()

    if showdown_filter and "only_sd" in showdown_filter:
        df = df[df["both_showdown"] == '✓']

    return df.to_dict("records")