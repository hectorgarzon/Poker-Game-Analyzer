from __future__ import annotations
import dash
import pandas as pd
from dash import html, dash_table, dcc
from pokerhero.database.db import get_connection, get_setting, upsert_player
from pokerhero.analysis.queries import get_hero_hand_players, get_actions
from flask import request
import urllib.parse
from flask import request

dash.register_page(__name__, path="/leaks", name="Leaks")

MIN_HANDS = 3

def _get_db_path() -> str:
    return dash.get_app().server.config.get("DB_PATH", ":memory:")

def _get_player_id(db_path: str, player_id_param: int | None = None) -> int | None:
    """Obtiene el ID del jugador: si se pasa player_id_param, lo usa DIRECTAMENTE; si no, usa el Hero."""
    if player_id_param is not None:
        return player_id_param 

    # Solo si no hay player_id_param, usa el Hero
    conn = get_connection(db_path)
    try:
        username = get_setting(conn, "hero_username", default="")
        return upsert_player(conn, username) if username else None
    finally:
        conn.close()

def get_hero_hands_with_actions_existing_queries(db_path: str, player_id: int) -> pd.DataFrame:
    """Obtiene todas las manos del jugador con sus acciones usando consultas existentes."""
    conn = get_connection(db_path)
    try:
        hero_hands = get_hero_hand_players(conn, player_id)
        hero_info = conn.execute("SELECT id, username FROM players WHERE id = ?", (player_id,)).fetchone()
        username = hero_info[1] if hero_info else "Desconocido"
        results = []
        for _, row in hero_hands.iterrows():
            hand_id = row['hand_id']
            net_profit = row['net_result']
            actions_df = get_actions(conn, hand_id)
            player_actions = actions_df[actions_df['player_id'] == player_id]
            def get_actions_for_street(street):
                street_actions = player_actions[player_actions['street'] == street]
                if street_actions.empty:
                    return None
                return " | ".join(
                    f"{action['action_type']}"
                    f"{f'({action['amount']})' if action['action_type'] in ['BET', 'RAISE'] else ''}"
                    f"{f' to call {action['amount_to_call']}' if action['action_type'] == 'CALL' else ''}"
                    for _, action in street_actions.iterrows()
                )
            results.append({
                'username': username,
                'id': player_id,
                'hand_id': hand_id,
                'net_profit': net_profit,
                'preflop_actions': get_actions_for_street('PREFLOP'),
                'flop_actions': get_actions_for_street('FLOP'),
                'turn_actions': get_actions_for_street('TURN'),
                'river_actions': get_actions_for_street('RIVER')
            })
        return pd.DataFrame(results)
    finally:
        conn.close()

def analyze_losing_action_combinations(df: pd.DataFrame) -> list[dict]:
    """Analiza las combinaciones de acciones del jugador (solo última acción por calle) y devuelve los top 5 que más pierden."""
    df_filtered = df[df['flop_actions'].notna()].copy()
    def create_action_combo(row):
        combo_parts = []
        def get_last_action_with_street(actions_str, street_prefix):
            if pd.isna(actions_str):
                return None
            actions = actions_str.split(' | ')
            last_action = actions[-1]
            clean_action = last_action.split('(')[0].split(' to call')[0].strip()
            return f"{street_prefix}/{clean_action}" if clean_action else None
        for col, pref in [('preflop_actions', 'PR'), ('flop_actions', 'F'), ('turn_actions', 'T'), ('river_actions', 'R')]:
            part = get_last_action_with_street(row[col], pref)
            if part:
                combo_parts.append(part)
        return ' -> '.join(combo_parts) if combo_parts else None
    df_filtered['action_combo'] = df_filtered.apply(create_action_combo, axis=1)
    df_filtered = df_filtered.dropna(subset=['action_combo'])
    combo_stats = df_filtered.groupby('action_combo').agg(
        total_loss=('net_profit', 'sum'),
        hand_count=('hand_id', 'count'),
        avg_loss=('net_profit', 'mean'),
        median_loss=('net_profit', 'median'),
        hand_ids=('hand_id', lambda x: list(x))
    ).reset_index()
    worst_combos = combo_stats[combo_stats['hand_count'] > MIN_HANDS].sort_values('total_loss', ascending=True).head(5)
    worst_combos['hand_ids'] = worst_combos['hand_ids'].apply(lambda x: ', '.join(map(str, x)))
    return worst_combos[['action_combo', 'total_loss', 'avg_loss', 'median_loss', 'hand_count', 'hand_ids']].to_dict('records')

def layout(player_id=None, **kwargs):
    """
    Dash pasa automáticamente los parámetros de la URL (p.ej. ?player_id=8906)
    como argumentos a la función layout.
    """
    db_path = _get_db_path()

    # Convertir el parámetro de la URL a entero si existe
    p_id_param = None
    if player_id is not None:
        try:
            p_id_param = int(player_id)
        except (ValueError, TypeError):
            p_id_param = None

    # Si hay p_id_param, se usa ese; si no, se busca al Hero configurado
    target_player_id = _get_player_id(db_path, p_id_param)

    if not target_player_id:
        return html.Div("⚠️ No se pudo determinar el jugador. Configura el Hero o pasa un player_id válido.",
                       style={"color": "orange", "padding": "20px"})

    # Las consultas SQL ahora usan target_player_id (el del parámetro o el hero)
    df = get_hero_hands_with_actions_existing_queries(db_path, target_player_id)
    if df.empty:
        return html.Div("No se encontraron manos para analizar.", style={"padding": "20px"})

    worst_combos = analyze_losing_action_combinations(df)
    if not worst_combos:
        return html.Div("⚠️ No se encontraron combinaciones.",
                       style={"padding": "20px", "color": "#666"})

    # Obtener el nombre del jugador específico para el título
    conn = get_connection(db_path)
    try:
        player_row = conn.execute("SELECT username FROM players WHERE id = ?", (target_player_id,)).fetchone()
        player_name = player_row[0] if player_row else "Jugador desconocido"
    finally:
        conn.close()

    origin = kwargs.get('origin', '')

    if origin == "/player" and player_id:
        sep = "&" if "?" in origin else "?"
        back_href = f"player/{player_id}"
    else:
        back_href = origin

    return html.Div([
        html.H2(f"🔍 Patrones de Pérdida de {player_name}"),
        dcc.Link(
            "← Volver",
            href=back_href,
            style={"fontSize": "13px", "color": "#0074D9", "marginBottom": "10px"},
        ),
        html.P(f"Top 5 combinaciones de acciones (mínimo {MIN_HANDS} manos) que más dinero hacen perder a {player_name}."),
        dash_table.DataTable(
            id="leaks-table",
            columns=[
                {"name": "Patrón de Acciones", "id": "action_combo"},
                {"name": "Pérdida Total", "id": "total_loss", "type": "numeric", "format": {"specifier": ".2f"}},
                {"name": "Pérdida Media", "id": "avg_loss", "type": "numeric", "format": {"specifier": ".2f"}},
                {"name": "Pérdida Mediana", "id": "median_loss", "type": "numeric", "format": {"specifier": ".2f"}},
                {"name": "Manos", "id": "hand_count"},
                {"name": "IDs de Manos", "id": "hand_ids", "type": "text"},
            ],
            data=worst_combos,
            style_header={'backgroundColor': '#8B0000', 'color': 'white', 'fontWeight': 'bold'},
            style_cell={'textAlign': 'left', 'padding': '10px', 'fontFamily': 'sans-serif'},
            style_data_conditional=[
                {'if': {'column_id': 'total_loss'}, 'color': '#8B0000', 'fontWeight': 'bold'},
                {'if': {'column_id': 'hand_ids'}, 'maxWidth': '200px', 'whiteSpace': 'normal', 'wordBreak': 'break-word'},
            ],
            tooltip_data=[
                {
                    "hand_ids": {
                        "value": f"Manos: {row['hand_ids']}",
                        "type": "markdown"
                    }
                } for row in worst_combos
            ],
            tooltip_delay=0,
            tooltip_duration=None,
        ),
        html.Div([
            html.H3("📊 Estadísticas Generales"),
            html.P(f"Total perdido en estas combinaciones: ${sum(row['total_loss'] for row in worst_combos):.2f}"),
        ], style={"marginTop": "30px", "padding": "15px", "backgroundColor": "#f8f9fa", "borderRadius": "6px"})
    ], style={"maxWidth": "1000px", "margin": "40px auto", "padding": "0 20px"})