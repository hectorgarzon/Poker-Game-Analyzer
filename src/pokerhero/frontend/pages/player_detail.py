"""Player detail page - shows information about a specific player."""

from dash import html, dcc, register_page
import dash
from pokerhero.database.db import get_connection

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
    row = conn.execute("SELECT username FROM players WHERE id = ?", (player_id,)).fetchone()
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
                html.Div(f"Nombre: {username}"),
                html.Div(f"ID del jugador: {player_id}"),
            ]),
        ],
    )