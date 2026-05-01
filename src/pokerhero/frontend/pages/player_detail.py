"""Player detail page - shows information about a specific player."""

from dash import html, dcc, register_page
import dash

register_page(__name__, path_template="/player/<player_id>")

def layout(player_id: str = None, **kwargs):
    """Render the player detail page."""
    if player_id is None:
        return html.Div("Jugador no encontrado", style={"color": "red"})

    return html.Div(
        style={
            "fontFamily": "sans-serif",
            "maxWidth": "1000px",
            "margin": "40px auto",
            "padding": "0 20px",
        },
        children=[
            html.H2(f"👤 Detalles del Jugador: {player_id}"),
            dcc.Link(
                "← Volver a Players",
                href="/players",
                style={"fontSize": "13px", "color": "#0074D9"},
            ),
            html.Hr(),
            html.Div(id="player-detail-content", children=[
                html.Div(f"Nombre de usuario: {player_id}"),
                # Aquí añadiremos más información más adelante
            ]),
        ],
    )