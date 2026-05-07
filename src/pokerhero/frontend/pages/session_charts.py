import dash
import pandas as pd
import plotly.express as px
import numpy as np
from dash import html, dcc, Input, Output, callback, State
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

    # Mapeo para preservar el hand_id real (para el clickData)
    hand_id_map = dict(enumerate(pivot_df.index, start=1))

    cumulative_df = pivot_df.cumsum().reset_index(drop=True)
    cumulative_df.index = cumulative_df.index + 1
    cumulative_df.index.name = 'Mano'

    # Preparar datos para Plotly
    plot_df = cumulative_df.melt(ignore_index=False, var_name='Jugador', value_name='Stack').reset_index()

    # Recuperar el hand_id real usando el número de mano
    plot_df['hand_id'] = plot_df['Mano'].map(hand_id_map)

    pivot_pos.index = cumulative_df.index
    plot_df['Posicion'] = pivot_pos.melt(ignore_index=False)['value'].values

    pivot_df.index = cumulative_df.index
    plot_df['Delta'] = pivot_df.melt(ignore_index=False)['value'].values

    plot_df = plot_df.dropna(subset=['Posicion'])

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
    colors = plot_df['Delta'].apply(
        lambda x: '#28a745' if x > 0
        else ('#dc3545' if x < 0 else '#808080')
    )
    for trace in fig.data:
        mask = plot_df['Jugador'] == trace.name
        trace.customdata = np.column_stack([
        plot_df[mask]['Jugador'],
        plot_df[mask]['Stack'],
        colors[mask],
        plot_df[mask]['Posicion'],
        plot_df[mask]['Delta'],
        plot_df[mask]['hand_id']  # Añadimos el hand_id
    ])
    trace.hovertemplate = (
        "<span style='color:%{customdata[2]}'>" +
        "(%{customdata[3]}) <b>%{customdata[0]}</b>: %{customdata[1]:.2f} (%{customdata[4]:+.2f})" +
        "<br>Hand ID: %{customdata[5]}" +  # Mostramos el hand_id en el hover
        "</span><extra></extra>"
    )

    if hero_name:
        fig.update_traces(line=dict(width=4), selector=dict(name=hero_name))

    fig.update_layout(
        legend=dict(orientation="h", y=-0.2, xanchor="center", x=0.5),
        margin=dict(l=40, r=40, t=60, b=80),
        hovermode="x unified"
    )

    return dcc.Graph(
        id="session-chart-graph",  # ID necesario para el callback
        figure=fig
    )

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
            dcc.Location(id="url"),
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

@callback(
    Output("url", "href"),
    Input("session-chart-graph", "clickData"),
    State("url", "search"), # Obtenemos los parámetros actuales de la URL (?session_id=...)
    prevent_initial_call=True,
)
def navigate_to_hand(click_data, search):
    if not click_data:
        raise dash.exceptions.PreventUpdate

    # Extraemos el hand_id del punto clickeado
    hand_id = click_data["points"][0]["customdata"][5]

    # Construimos la URL pasando el origen y los parámetros actuales (session_id)
    query_params = search if search else "?"
    return f"/hand/{hand_id}{query_params}&origin=charts"