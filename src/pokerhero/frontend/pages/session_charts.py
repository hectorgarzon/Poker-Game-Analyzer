import dash
import pandas as pd
import plotly.express as px
import numpy as np
from dash import html, dcc
from pokerhero.database.db import get_connection, get_setting

dash.register_page(__name__, path="/session-charts")

def _get_db_path() -> str:
    return dash.get_app().server.config.get("DB_PATH", ":memory:")

def _get_session_label(session_id: int) -> str:
    db_path = _get_db_path()
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
    return f"{date}  {float(row[1]):g}/{float(row[2]):g}"

def _build_session_chart(session_id: int) -> dcc.Graph | html.Div:
    """Consulta los resultados de todos los jugadores y genera el gráfico de líneas."""
    db_path = _get_db_path()
    conn = get_connection(db_path)
    try:
        hero_name = get_setting(conn, "hero_username", default="")
        query = """
            SELECT h.id as hand_id, p.username, hp.net_result, hp.position
            FROM hands h
            JOIN hand_players hp ON h.id = hp.hand_id
            JOIN players p ON hp.player_id = p.id
            WHERE h.session_id = ?
            ORDER BY h.id
        """
        df = pd.read_sql_query(query, conn, params=(session_id,))
    finally:
        conn.close()

    if df.empty:
        return html.Div("No hay datos suficientes para generar el gráfico.")

    # Procesamiento de datos
    pivot_df = df.pivot(index='hand_id', columns='username', values='net_result').fillna(0)
    pivot_pos = df.pivot(index='hand_id', columns='username', values='position')
    cumulative_df = pivot_df.cumsum().reset_index(drop=True)
    cumulative_df.index = cumulative_df.index + 1

    # Preparar datos para Plotly
    plot_df = cumulative_df.melt(ignore_index=False, var_name='Jugador', value_name='Stack')
    pivot_pos.index = cumulative_df.index
    plot_df['Posicion'] = pivot_pos.melt(ignore_index=False)['value']
    plot_df = plot_df.dropna(subset=['Posicion'])
    plot_df.index.name = 'Mano'
    plot_df = plot_df.reset_index()

    # Ordenar jugadores con héroe primero
    players = plot_df['Jugador'].unique().tolist()
    if hero_name and hero_name in players:
        players.remove(hero_name)
        players = [hero_name] + players

    # Crear figura
    fig = px.line(
        plot_df,
        x='Mano',
        y='Stack',
        color='Jugador',
        category_orders={'Jugador': players},
        title="Evolución del Stack por Jugador",
        labels={'Mano': 'Número de Manos', 'Stack': 'Incremento de Stack'}
    )

    # Añadir colores al hover
    colors = plot_df['Stack'].apply(lambda x: '#28a745' if x >= 0 else '#dc3545')
    for trace in fig.data:
        mask = plot_df['Jugador'] == trace.name
        trace.customdata = np.column_stack([
            plot_df[mask]['Jugador'],
            plot_df[mask]['Stack'],
            colors[mask],
            plot_df[mask]['Posicion']
        ])
        trace.hovertemplate = (
            "<span style='color:%{customdata[2]}'>" +
            "<b>%{customdata[0]}</b> (%{customdata[3]}): %{customdata[1]:.2f}" +
            "</span><extra></extra>"
        )

    if hero_name:
        fig.update_traces(line=dict(width=4), selector=dict(name=hero_name))

    fig.update_layout(
        legend=dict(orientation="h", y=-0.2, xanchor="center", x=0.5),
        margin=dict(l=40, r=40, t=60, b=80),
        hovermode="x unified"
    )

    return dcc.Graph(figure=fig)

def _render_breadcrumb(session_id: int):
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

def _get_neighbor_sessions(session_id: int) -> tuple[int | None, int | None]:
    """Obtiene los IDs de la sesión anterior y siguiente."""
    db_path = _get_db_path()
    conn = get_connection(db_path)
    try:
        prev_id = conn.execute(
            "SELECT id FROM sessions WHERE id < ? ORDER BY id DESC LIMIT 1", (session_id,)
        ).fetchone()
        next_id = conn.execute(
            "SELECT id FROM sessions WHERE id > ? ORDER BY id ASC LIMIT 1", (session_id,)
        ).fetchone()
        return (prev_id[0] if prev_id else None, next_id[0] if next_id else None)
    finally:
        conn.close()

def layout(session_id: str | None = None, **kwargs: object) -> html.Div:
    s_id = int(session_id) if session_id else None
    prev_id, next_id = _get_neighbor_sessions(s_id) if s_id else (None, None)

    btn_style = {"padding": "6px 12px", "cursor": "pointer"}

    return html.Div(
        style={"fontFamily": "sans-serif", "maxWidth": "1000px", "margin": "40px auto", "padding": "0 20px"},
        children=[
            html.H2("📈 Gráficos de la Sesión"),
            # Contenedor flex para alinear texto y botones
            html.Div([
                html.Div(_render_breadcrumb(s_id) if s_id else dcc.Link("← Volver", href="/sessions"),
                         style={"marginBottom": "0"}),
                html.Div([
                    dcc.Link(
                        html.Button("← Sesión Anterior", disabled=prev_id is None, style=btn_style),
                        href=f"/session-charts?session_id={prev_id}" if prev_id else "#"
                    ),
                    dcc.Link(
                        html.Button("Siguiente Sesión →", disabled=next_id is None, style=btn_style),
                        href=f"/session-charts?session_id={next_id}" if next_id else "#"
                    ),
                ], style={"display": "flex", "gap": "10px"}),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "12px"}),
            html.Hr(style={"marginTop": "0"}),
            _build_session_chart(s_id) if s_id else html.Div("No se ha especificado ninguna sesión.")
        ]
    )