import dash
from dash import html, dcc
from pokerhero.database.db import get_connection

dash.register_page(__name__, path="/session-charts")

def _get_session_label(session_id: int) -> str:
    """Obtiene la etiqueta formateada de la sesión (Fecha + Stakes)."""
    db_path = dash.get_app().server.config.get("DB_PATH", ":memory:")
    if db_path == ":memory:":
        return f"Session #{session_id}"
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT start_time, small_blind, big_blind FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return f"Session #{session_id}"
    date = str(row[0])[:10] if row[0] else "—"
    sb, bb = float(row[1]), float(row[2])
    return f"{date}  {sb:g}/{bb:g}"

def _render_breadcrumb(session_id: int):
    """Renderiza el breadcrumb de navegación."""
    label = _get_session_label(session_id)
    sep = html.Span(" › ", style={"color": "#aaa", "margin": "0 6px"})
    link_style = {"textDecoration": "none", "color": "#0074D9", "fontSize": "14px"}

    return html.Div([
        dcc.Link("Sessions", href="/sessions", style=link_style),
        sep,
        dcc.Link(label, href=f"/sessions?session_id={session_id}", style=link_style),
        sep,
        html.Span("Charts", style={"fontSize": "14px", "color": "#333", "fontWeight": "600"})
    ], style={"marginBottom": "12px"})

def layout(session_id: str | None = None, **kwargs: object) -> html.Div:
    """Diseño de la página con breadcrumb dinámico."""
    s_id = int(session_id) if session_id else None

    return html.Div(
        style={"fontFamily": "sans-serif", "maxWidth": "1000px", "margin": "40px auto", "padding": "0 20px"},
        children=[
            html.H2("📈 Gráficos de la Sesión"),
            _render_breadcrumb(s_id) if s_id else dcc.Link("← Volver", href="/sessions"),
            html.Hr(style={"marginTop": "0"}),
        ]
    )