"""Hand detail page - shows a single hand's action sequence."""

from __future__ import annotations

import os
from pathlib import Path
import json
import math
import sqlite3
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlparse

from pokerhero.analysis.generate_hand_text import generate_hand_text
import dash
import pandas as pd
from dash import Input, Output, State, callback, dcc, html, no_update
from dash.development.base_component import Component

from pokerhero.database.db import get_connection, get_setting, upsert_player
from pokerhero.analysis.queries import get_actions, get_hand_details
from pokerhero.analysis.hand_ai_analysis import analyze_hand_with_ai

dash.register_page(__name__, path_template="/hand/<hand_id>")  # type: ignore[no-untyped-call]

# Estilos compartidos (reutilizados de sessions.py)
_TH = {
    "background": "#0074D9",
    "color": "#fff",
    "padding": "10px 12px",
    "textAlign": "left",
    "fontWeight": "600",
    "fontSize": "13px",
}
_TD = {
    "padding": "9px 12px",
    "borderBottom": "1px solid var(--border-light, #eee)",
    "fontSize": "13px",
    "cursor": "pointer",
}
_STREET_COLOURS = {
    "PREFLOP": "#6c757d",
    "FLOP": "#0074D9",
    "TURN": "#2ECC40",
    "RIVER": "#FF4136",
}
_SUIT_SYMBOLS: dict[str, str] = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
_SUIT_COLORS: dict[str, str] = {
    "s": "#111111",
    "h": "#cc0000",
    "d": "#cc0000",
    "c": "#111111",
}

_ARCHETYPE_COLORS: dict[str | None, str] = {
    "TAG": "#2980b9",
    "LAG": "#e67e22",
    "Nit": "#7f8c8d",
    "Fish": "#27ae60",
}

class _VillainRow(TypedDict):
    """One villain's showdown data."""
    username: str
    position: str
    hole_cards: str
    net_result: float | None

def _save_analysis_to_file(source_hand_id: str, hand_id: int, analysis_text: str) -> str:
    """Guarda el análisis en un archivo .txt y devuelve la ruta.

    Args:
        source_hand_id: Número de mano original (ej: "260684331763")
        hand_id: ID interno de la base de datos
        analysis_text: Texto del análisis a guardar

    Returns:
        Ruta completa del archivo guardado
    """
    # Crear directorio si no existe
    ai_dir = Path("ai_analysis")
    ai_dir.mkdir(exist_ok=True)

    # Nombre del archivo: "260684331763-123.txt" (sin el #)
    filename = f"{source_hand_id}-{hand_id}.txt"
    filepath = ai_dir / filename

    # Guardar el análisis
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(analysis_text)

    return str(filepath)

def _action_row_style(is_hero: bool) -> dict[str, str]:
    """Return the tr style for an action row."""
    if is_hero:
        return {
            "backgroundColor": "var(--bg-hero-row, #edf5ff)",
            "borderLeft": "3px solid #0074D9",
        }
    return {}

def _render_card(card: str) -> html.Span:
    """Render a single PokerStars card code as a styled card element."""
    if not card or len(card) < 2:
        return html.Span()
    rank = card[:-1]
    suit_char = card[-1].lower()
    suit_sym = _SUIT_SYMBOLS.get(suit_char, suit_char)
    color = _SUIT_COLORS.get(suit_char, "#111111")
    return html.Span(
        f"{rank}{suit_sym}",
        style={
            "display": "inline-block",
            "background": "#fff",
            "border": "1px solid #bbb",
            "borderRadius": "4px",
            "padding": "2px 7px",
            "fontWeight": "700",
            "fontSize": "14px",
            "color": color,
            "fontFamily": "monospace",
            "boxShadow": "1px 1px 2px rgba(0,0,0,0.15)",
            "marginRight": "3px",
            "lineHeight": "1.5",
        },
    )

def _render_cards(cards_str: str | None) -> html.Span:
    """Render a space-separated card string as inline card elements."""
    if not cards_str:
        return html.Span("—")
    cards = [c.strip() for c in str(cards_str).split() if c.strip()]
    if not cards:
        return html.Span("—")
    return html.Span([_render_card(c) for c in cards])

def _format_cards_text(cards_str: str | None) -> str:
    """Format a space-separated card string as plain text with suit symbols."""
    if not cards_str:
        return "—"
    parts = []
    for card in str(cards_str).split():
        if len(card) >= 2:
            rank = card[:-1]
            suit = _SUIT_SYMBOLS.get(card[-1].lower(), card[-1])
            parts.append(f"{rank}{suit}")
    return " ".join(parts) if parts else "—"

def _archetype_badge_attrs(archetype: str, hands_played: int) -> tuple[str, dict[str, str]]:
    """Return (label, extra_style) for an archetype badge."""
    from pokerhero.analysis.stats import confidence_tier

    tier = confidence_tier(hands_played)
    if tier == "confirmed":
        return f"{archetype} ✓", {}
    if tier == "preliminary":
        return archetype, {"opacity": "0.55"}
    return archetype, {}

def _build_showdown_section(
    villain_rows: list[_VillainRow],
    hero_name: str | None = None,
    hero_cards: str | None = None,
    board: str = "",
    opp_stats: pd.DataFrame | None = None,
    min_hands: int = 15,
    hero_net_result: float | None = None,
) -> html.Div | None:
    """Construye una sección de Showdown mostrando las cartas de todos los jugadores y el board."""
    if not villain_rows:
        return None

    # Determinar la calle del showdown (basado en el board)
    board_parts = [p for p in board.split() if p]
    street = "PREFLOP"
    if len(board_parts) == 3:
        street = "FLOP"
    elif len(board_parts) == 4:
        street = "TURN"
    elif len(board_parts) >= 5:
        street = "RIVER"

    # Construir el título con la calle y el board
    street_color = _STREET_COLOURS.get(street, "#a855f7")
    title = f"Showdown"
    if board_parts:
        title += f" - Board: {_format_cards_text(' '.join(board_parts))}"

    # Construir la lista de jugadores
    players: list[tuple[str, str]] = []
    label_to_username: dict[str, str] = {}
    label_to_result: dict[str, float] = {}

    if hero_name and hero_cards:
        players.append((hero_name, hero_cards))
        if hero_net_result is not None:
            label_to_result[hero_name] = hero_net_result

    for v in villain_rows:
        label = v["username"]
        if v.get("position"):
            label += f" ({v['position']})"
        players.append((label, v["hole_cards"]))
        label_to_username[label] = v["username"]
        if v.get("net_result") is not None:
            label_to_result[label] = float(v["net_result"])

    # Evaluar las mejores manos de cada jugador
    import itertools
    import re
    from pokerkit import Card, StandardHighHand

    board_card_list = [c for c in board.split() if c]
    descriptions: dict[str, str | None] = {}
    winner_labels: set[str] = set()

    if len(board_card_list) >= 3:
        best_hands: dict[str, object] = {}
        for label, hole in players:
            try:
                all_cards = list(Card.parse(hole.replace(" ", ""))) + list(
                    Card.parse("".join(board_card_list))
                )
                best = max(
                    StandardHighHand(list(combo)) for combo in itertools.combinations(all_cards, 5)
                )
                best_hands[label] = best
                descriptions[label] = re.sub(r"\s*\(.*\)", "", str(best))
            except Exception:
                best_hands[label] = None
                descriptions[label] = None

        # Determinar el ganador
        valid = {lb: h for lb, h in best_hands.items() if h is not None}
        if valid:
            top = max(valid.values())
            winner_labels = {lb for lb, h in valid.items() if h == top}

    # Renderizar las filas de jugadores
    rows: list[html.Div] = []
    for label, hole in players:
        result = label_to_result.get(label, None)
        result_str = f" ({_fmt_pnl(result)})" if result is not None else ""
        desc = descriptions.get(label)
        trophy = "🏆 " if label in winner_labels else ""

        # Archetype badge
        archetype_badge: list[Component] = []
        username = label_to_username.get(label)
        if opp_stats is not None and username:
            stats = opp_stats[opp_stats['username'] == username]
            if not stats.empty:
                s = stats.iloc[0]
                hands_played = int(s["hands_played"])
                vpip = int(s["vpip_count"]) / hands_played * 100 if hands_played > 0 else 0
                pfr = int(s["pfr_count"]) / hands_played * 100 if hands_played > 0 else 0

                from pokerhero.analysis.stats import classify_player
                archetype = classify_player(vpip, pfr, hands_played, min_hands=min_hands)

                if archetype:
                    arch_label, arch_extras = _archetype_badge_attrs(archetype, hands_played)
                    archetype_badge = [
                        html.Span(
                            arch_label,
                            style={
                                "background": _ARCHETYPE_COLORS.get(archetype, "#999"),
                                "color": "#fff",
                                "borderRadius": "4px",
                                "padding": "1px 6px",
                                "fontSize": "11px",
                                "fontWeight": "700",
                                "marginLeft": "5px",
                                **arch_extras,
                            },
                        )
                    ]

        rows.append(
            html.Div(
                [
                    html.Span(
                        f"{trophy}{label}: ",
                        style={
                            "fontWeight": "600",
                            "fontSize": "13px",
                            "marginRight": "6px",
                            "color": "#f5a623" if trophy else "var(--text-3, #555)",
                        },
                    ),
                    *archetype_badge,
                    _render_cards(hole),
                    *(
                        [
                            html.Span(
                                f"  — {desc}",
                                style={
                                    "fontSize": "12px",
                                    "color": "var(--text-4, #888)",
                                    "marginLeft": "6px",
                                },
                            )
                        ]
                        if desc
                        else []
                    ),
                    html.Span(
                        result_str,
                        style={"marginLeft": "6px", "color": "#27ae60" if result and result >= 0 else "#e74c3c"},
                    ),
                ],
                style={"marginBottom": "6px", "display": "flex", "alignItems": "center"},
            )
        )

    return html.Div(
        [
            html.H5(
                title,
                style={
                    "color": street_color,
                    "borderBottom": f"2px solid {street_color}",
                    "paddingBottom": "4px",
                    "marginBottom": "8px",
                },
            ),
            *rows,
        ]
    )

def _fmt_pnl(pnl: float) -> str:
    """Format a P&L value with leading sign."""
    sign = "+" if pnl >= 0 else ""
    formatted = f"{sign}{pnl:,.6g}"
    if "e" in formatted or "E" in formatted:
        formatted = f"{sign}{pnl:,.2f}"
    return formatted

def _format_math_cell(
    spr: float | None,
    mdf: float | None,
    is_hero: bool,
    amount_to_call: float,
    pot_before: float,
) -> str:
    """Build the math/context cell text for an action row."""
    parts: list[str] = []

    if is_hero and amount_to_call > 0:
        pot_odds = amount_to_call / (pot_before + amount_to_call) * 100
        parts.append(f"Pot odds: {pot_odds:.1f}%")
        if mdf is not None and not math.isnan(mdf):
            parts.append(f"MDF: {mdf * 100:.1f}%")

    result = "  |  ".join(parts)

    if spr is not None and not math.isnan(spr):
        spr_str = f"SPR: {spr:.2f}"
        result = f"{spr_str}  |  {result}" if result else spr_str

    return result

def layout(hand_id: int | str | None = None, **kwargs: str) -> Component:
    """Layout principal de la página de mano."""
    if hand_id is None:
        return html.Div("ID de mano no proporcionado", style={"color": "red"})

    # Determinar URL y texto de retorno basado en el origen
    origin = kwargs.get("origin")
    session_id = kwargs.get("session_id")
    player_id = kwargs.get("player_id")

    if origin == "charts":
        back_href = f"/session-charts?session_id={session_id}" if session_id else "/session-charts"
        back_text = "← Volver a Gráficos"
    elif origin == "player": # Nueva condición para retorno a jugador
        back_href = f"/player/{player_id}" if player_id else "/players"
        back_text = "← Volver al Jugador"
    elif session_id:
        back_href = f"/sessions?session_id={session_id}&level=hands"
        back_text = "← Volver a Lista de Manos"
    else:
        back_href = "/sessions"
        back_text = "← Volver a Sesiones"

    return html.Div(
        style={
            "fontFamily": "sans-serif",
            "maxWidth": "1000px",
            "margin": "40px auto",
            "padding": "0 20px",
        },
        children=[
            html.H2("🃏 Detalle de Mano"),
            dcc.Link(
                back_text,
                href=back_href,
                style={"fontSize": "13px", "color": "#0074D9"},
            ),
            html.Hr(),
            dcc.Loading(html.Div(id="hand-content")),
            dcc.Store(id="hand-state", data={"hand_id": int(hand_id)}),
            dcc.Store(id="hand-text-store", data=""),
            dcc.Store(id="hand-details-store", data={}),
            dcc.Store(id="hand-fav-id-store", data=hand_id),
            dcc.Store(id="ai-analysis-store", data=None),
        ],
    )

@callback(
    Output("hand-content", "children"),
    Input("hand-state", "data"),
)
def render_hand(state: dict) -> Component:
    """Renderiza el contenido de la mano."""
    hand_id = state["hand_id"]
    db_path = _get_db_path()
    conn = get_connection(db_path)

    try:
        # Obtener detalles de la mano
        hand_details = get_hand_details(conn, hand_id)
        if not hand_details:
            return html.Div("Mano no encontrada", style={"color": "red"})

        # Obtener acciones de la mano
        actions_df = get_actions(conn, hand_id)

        # Construir la visualización de la mano
        return _render_hand_view(hand_id, hand_details, actions_df)  # Solo devuelve componentes visuales

    finally:
        conn.close()

def _get_hero_player_id(db_path: str) -> int | None:
    """Obtiene el ID del jugador héroe desde la base de datos."""
    if db_path == ":memory:":
        return None
    conn = get_connection(db_path)
    try:
        username = get_setting(conn, "hero_username", default="")
        return upsert_player(conn, username) if username else None
    finally:
        conn.close()

def _render_hand_view(
    hand_id: int,
    hand_details: dict,
    actions_df: pd.DataFrame
) -> Component:
    """Construye la vista detallada de la mano."""
    # Extraer información de la mano
    source_id = hand_details.get("source_hand_id", hand_id)
    flop = hand_details.get("board_flop", "")
    turn = hand_details.get("board_turn", "")
    river = hand_details.get("board_river", "")
    hero_cards = hand_details.get("hero_cards", "")
    hero_name = "Hero"  # Siempre mostrar "Hero"
    hero_net_result = hand_details.get("hero_net_result")
    hand_is_fav = hand_details.get("is_favorite", False)
    session_id = hand_details.get("session_id", 0)
    opp_stats = hand_details.get("opp_stats", pd.DataFrame())

    # Generar el texto de la mano
    db_path = _get_db_path()
    conn = get_connection(db_path)
    try:
        hand_text = generate_hand_text(conn, hand_id)
    finally:
        conn.close()

    # Sección de información básica
    header_children = [
        html.Div(
            [
                html.H3(f"Hand #{source_id}", style={"marginTop": "0", "marginBottom": "0"}),
                # Componente Clipboard en lugar de botón
                dcc.Clipboard(
                    id="hand-clipboard",
                    content=hand_text,  # Texto a copiar
                    title="Copiar historial de mano",
                    style={
                        "display": "inline-block",
                        "fontSize": "20px",
                        "marginRight": "10px",
                        "cursor": "pointer",
                        "verticalAlign": "middle"
                    },
                ),
                html.Div(id="copy-status-message", style={"display": "inline-block"}),
                # Nuevo botón de análisis con IA
                html.Button(
                    "🤖 Analizar con IA",
                    id="ai-analysis-btn",
                    n_clicks=0,
                    style={
                        "background": "#6c5ce7",
                        "color": "white",
                        "border": "none",
                        "borderRadius": "4px",
                        "padding": "6px 12px",
                        "marginRight": "10px",
                        "cursor": "pointer",
                        "fontSize": "14px"
                    }
                ),
                dcc.Loading(
                    id="ai-analysis-loading",
                    type="circle",
                    children=html.Div(id="ai-analysis-result")
                ),
                html.Button(
                    [
                        "★" if hand_is_fav else "☆",
                        " Favourite hand",
                    ],
                    id="hand-fav-btn-hand-page",
                    n_clicks=0,
                    style={
                        "display": "flex",
                        "alignItems": "center",
                        "gap": "6px",
                        "background": "#fff8ec" if hand_is_fav else "var(--bg-2, #f5f5f5)",
                        "border": "1px solid #f5a623" if hand_is_fav else "1px solid var(--border-light, #ccc)",
                        "borderRadius": "20px",
                        "padding": "4px 12px",
                        "fontSize": "15px",
                        "cursor": "pointer",
                        "color": "#f5a623" if hand_is_fav else "var(--text-4, #888)",
                        "fontWeight": "600",
                        "lineHeight": "1.4",
                    },
                ),
            ],
            style={
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "center",
                "marginBottom": "8px",
            },
        ),
        # Mensaje de confirmación de copia
        html.Div(
            id="copy-status-message",
            style={
                "color": "#27ae60",
                "fontSize": "14px",
                "marginBottom": "10px",
                "height": "20px"
            }
        ),
    ]

    # Verificar si hay EV calculado
    ev_cache = _load_ev_cache_for_hand(hand_id)
    has_ev = any(ev_cache.values())

    if not has_ev:
        header_children.insert(
            1,  # Insertar después del título de la mano
            html.Div(
                "⚠️ El EV no ha sido calculado para esta mano. Usa el botón '📊 Calculate EVs' en la vista de sesiones.",
                style={
                    "background": "#fff3cd",
                    "border": "1px solid #ffeeba",
                    "borderRadius": "4px",
                    "padding": "8px",
                    "marginBottom": "12px",
                    "fontSize": "13px",
                }
            )
        )

     # Sección de Villains (oponentes) - ahora incluye al Hero
    hero_username = hand_details.get("hero_username", "enygma9999")  # Obtener el nombre de usuario del Hero
    villain_section = _build_villain_section(hand_details.get("villains", []), opp_stats, hero_username)
    if villain_section:
        header_children.append(villain_section)

    # Board
    _sep = html.Span(
        "│",
        style={"color": "var(--text-4, #ccc)", "margin": "0 8px", "fontWeight": "300"},
    )
    board_elems = [
        html.Span(
            "Board: ",
            style={
                "fontWeight": "600",
                "color": "var(--text-3, #555)",
                "fontSize": "13px",
                "marginRight": "6px",
            },
        )
    ]
    if flop:
        board_elems.append(_render_cards(flop))
        if turn:
            board_elems.append(_sep)
            board_elems.append(_render_cards(turn))
            if river:
                board_elems.append(_sep)
                board_elems.append(_render_cards(river))
    else:
        board_elems.append(html.Span("—", style={"color": "var(--text-4, #888)"}))

    board_div = html.Div(
        board_elems,
        style={
            "display": "flex",
            "alignItems": "center",
            "marginBottom": "12px",
        },
    )

    # Sección de acciones
    sections = _build_action_sections(actions_df, flop, turn, river, bb_size=hand_details.get("bb_size", 0.05), hand_id=hand_id)

    # Showdown
    board_str = " ".join(p for p in [flop, turn, river] if p)
    showdown_div = _build_showdown_section(
        hand_details.get("villain_showdown", []),
        hero_name=hero_name,
        hero_cards=hero_cards,
        board=board_str,
        opp_stats=opp_stats,
        hero_net_result=hero_net_result,
    )

    if showdown_div is not None:
        sections.append(showdown_div)

    return html.Div([*header_children, board_div, *sections])


def _build_villain_section(
    villain_rows: list[_VillainRow],
    opp_stats: pd.DataFrame,
    hero_username: str = "enygma9999"  # Nombre de usuario del Hero que queremos reemplazar
) -> Component | None:
    """Construye la sección de oponentes (villains) con sus stats en línea horizontal."""
    if not villain_rows:
        return None

    # Crear contenedor flexible para villains
    villain_elements = []
    for villain in villain_rows:
        username = villain["username"]
        # Reemplazar el nombre de usuario del Hero con "Hero"
        display_name = "Hero" if username == hero_username else username

        position = villain.get("position", "")
        hole_cards = villain.get("hole_cards", "")

        # Buscar stats del villain
        stats = opp_stats[opp_stats['username'] == username]
        stats_info = []
        if not stats.empty:
            s = stats.iloc[0]
            hands_played = int(s["hands_played"])
            vpip = int(s["vpip_count"]) / hands_played * 100 if hands_played > 0 else 0
            pfr = int(s["pfr_count"]) / hands_played * 100 if hands_played > 0 else 0
            stats_info = [f"VPIP: {vpip:.1f}%", f"PFR: {pfr:.1f}%"]

            # Clasificar arquetipo
            from pokerhero.analysis.stats import classify_player
            archetype = classify_player(vpip, pfr, hands_played, min_hands=15)

            if archetype:
                arch_label, arch_extras = _archetype_badge_attrs(archetype, hands_played)
                archetype_badge = html.Span(
                    arch_label,
                    style={
                        "background": _ARCHETYPE_COLORS.get(archetype, "#999"),
                        "color": "#fff",
                        "borderRadius": "4px",
                        "padding": "1px 6px",
                        "fontSize": "11px",
                        "fontWeight": "700",
                        "marginLeft": "5px",
                        **arch_extras,
                    },
                )
            else:
                archetype_badge = None
        else:
            archetype_badge = None

        # Crear elemento de villain
        villain_elements.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                f"{display_name} ({position}): " if position else f"{display_name}: ",
                                style={
                                    "fontWeight": "600",
                                    "fontSize": "13px",
                                    "marginRight": "6px",
                                },
                            ),
                            _render_cards(hole_cards) if hole_cards else html.Span("—"),
                            archetype_badge if archetype_badge else None,
                        ],
                        style={"display": "flex", "alignItems": "center", "marginBottom": "4px"}
                    ),
                    html.Div(
                        [
                            html.Span(stat, style={"fontSize": "11px", "marginRight": "6px"})
                            for stat in stats_info
                        ],
                        style={"display": "flex", "color": "var(--text-3, #555)"}
                    )
                ],
                style={
                    "marginRight": "20px",
                    "paddingBottom": "8px",
                    "borderBottom": "1px solid #eee",
                    "minWidth": "180px"
                }
            )
        )

    return html.Div(
        [
            html.H5(
                "Players",
                style={
                    "color": "#e67e22",
                    "borderBottom": "2px solid #e67e22",
                    "paddingBottom": "4px",
                    "marginBottom": "12px",
                },
            ),
            html.Div(
                villain_elements,
                style={
                    "display": "flex",
                    "flexWrap": "wrap",
                    "gap": "10px"
                }
            )
        ],
        style={"marginBottom": "20px"}
    )


def _build_ev_cell(
    cache_row: dict[str, object] | None,
    action_type: str,
) -> str | html.Div:
    """Construye la celda de EV para la tabla de acciones.

    Args:
        cache_row: Diccionario con los datos del EV desde action_ev_cache,
                  o None si no hay datos.
        action_type: Tipo de acción ('BET', 'RAISE', 'CALL', 'FOLD', etc.)

    Returns:
        Contenido de la celda (texto o componente HTML).
    """
    if cache_row is None:
        return "—"

    equity = float(cache_row["equity"])
    ev = float(cache_row["ev"])
    ev_type = str(cache_row["ev_type"])
    ev_str = _fmt_pnl(ev)

    if action_type == "FOLD":
        # EV almacenado es el "EV de pagar" (para evaluar si el fold fue correcto)
        if ev > 0:
            label = f"⚠ Deberías haber pagado (EV: {ev_str})"
            color = "#e74c3c"  # Rojo
        else:
            label = f"✓ Buen fold (EV: {ev_str})"
            color = "#27ae60"  # Verde
        return html.Div(html.Span(label, style={"color": color, "fontSize": "12px"}))

    # Para acciones de rango (BET, RAISE, CALL)
    equity_pct = f"{equity * 100:.0f}%"
    multiway_note = " (aprox. multiway)" if ev_type == "range_multiway_approx" else ""
    summary = f"Equity: {equity_pct} | EV: {ev_str}{multiway_note}"

    # Información adicional en tooltip
    preflop_action = str(cache_row.get("villain_preflop_action", "desconocido"))
    contracted = cache_row.get("contracted_range_size")
    sample_count = int(float(cache_row.get("sample_count", 0)))
    tooltip_parts = [f"Tipo de rango preflop: {preflop_action}"]
    if contracted is not None:
        tooltip_parts.append(f"Rango contraído: {int(float(contracted))} combos")
    tooltip_parts += [
        f"Muestras: {sample_count}",
        "Nota: Los bluffs no están modelados explícitamente.",
    ]
    tooltip = " | ".join(tooltip_parts)

    children = [
        html.Span(summary),
        html.Span(
            " ℹ️",
            title=tooltip,
            style={
                "cursor": "help",
                "color": "#aaa",
                "fontSize": "11px",
                "marginLeft": "4px",
            },
        ),
    ]

    # Advertencia para calls con EV negativo
    if action_type == "CALL" and ev < 0:
        children.append(
            html.Div(
                "[Fold era mejor ↑]",
                style={"color": "#e74c3c", "fontSize": "11px"},
            )
        )

    return html.Div(children, style={"lineHeight": "1.3"})

def _build_action_sections(
    df: pd.DataFrame,
    flop: str,
    turn: str,
    river: str,
    bb_size: float,
    hand_id: int
) -> list[Component]:
    """Construye las secciones de acciones por calle, incluyendo columna EV."""
    sections: list[html.Div] = []
    current_street: str | None = None
    street_rows: list[html.Tr] = []

    # Cargar el cache de EV para esta mano (si existe)
    ev_cache = _load_ev_cache_for_hand(hand_id) if not df.empty else {}

    def _flush(street: str, rows: list[html.Tr]) -> html.Div:
        colour = _STREET_COLOURS.get(street, "#333")
        street_cards = {"FLOP": flop, "TURN": turn, "RIVER": river}
        cards_str = street_cards.get(street)
        header_children = [street]
        if cards_str:
            header_children.append(
                html.Span(
                    _render_cards(cards_str),
                    style={"marginLeft": "10px", "verticalAlign": "middle"},
                )
            )
        return html.Div(
            [
                html.H5(
                    header_children if len(header_children) > 1 else street,
                    style={
                        "color": colour,
                        "borderBottom": f"2px solid {colour}",
                        "paddingBottom": "4px",
                        "marginBottom": "4px",
                        "display": "flex",
                        "alignItems": "center",
                        "gap": "8px",
                    },
                ),
                html.Table(
                    [
                        html.Thead(html.Tr([
                            html.Th("Jugador", style={**_TH, "width": "200px"}),
                            html.Th("Acción", style={**_TH, "width": "150px"}),
                            html.Th("Bote", style=_TH),
                            html.Th("Contexto", style=_TH),
                            html.Th("EV", style=_TH),  # Nueva columna EV
                        ])),
                        html.Tbody(rows)
                    ],
                    style={
                        "width": "100%",
                        "borderCollapse": "collapse",
                        "marginBottom": "12px",
                    },
                ),
            ]
        )

    for row_idx, action in df.iterrows():
        street = str(action["street"])
        if street != current_street:
            if current_street is not None:
                sections.append(_flush(current_street, street_rows))
            current_street = street
            street_rows = []

        username = str(action["username"])
        position = str(action["position"]) if action["position"] else ""
        actor_str = f"{username} ({position})" if position else username
        if action["is_hero"]:
            actor_str = f"🦸 {actor_str}"

        action_type = str(action["action_type"])
        # Determinar color de fondo según el tipo de acción
        action_bg_map = {
            "BET": "#f39c12",
            "RAISE": "#e74c3c",
            "CALL": "#3498db",
            "FOLD": "#bdc3c7",
            "CHECK": "#3458db", 
        }
        bg_color = action_bg_map.get(action_type.upper(), "transparent")

        amount = float(action["amount"])
        pot_before = float(action["pot_before"])
        amount_to_call = float(action["amount_to_call"])

        label = action_type
        if amount > 0:
            label += f"  {amount:,.6g}"
        if action["is_all_in"]:
            label += "  🚨 ALL-IN"

        raw_spr = action["spr"]
        raw_mdf = action["mdf"]
        spr_val = (
            float(raw_spr)
            if raw_spr is not None and not math.isnan(float(raw_spr))
            else None
        )
        mdf_val = (
            float(raw_mdf)
            if raw_mdf is not None and not math.isnan(float(raw_mdf))
            else None
        )
        extra = _format_math_cell(
            spr=spr_val,
            mdf=mdf_val,
            is_hero=bool(action["is_hero"]),
            amount_to_call=amount_to_call,
            pot_before=pot_before,
        )

        # Construir celda de EV
        ev_cell_content = _build_ev_cell(
            ev_cache.get(int(action["id"])) if action["is_hero"] else None,
            action_type
        )

        street_rows.append(
            html.Tr(
                [
                    html.Td(actor_str, style={**_TD, "width": "200px", "fontWeight": "600"}),
                    html.Td(
                        label,
                        style={
                            **_TD,
                            "width": "150px",
                            "backgroundColor": bg_color,
                            "color": "white" if bg_color != "transparent" else "inherit",
                            "fontWeight": "600" if bg_color != "transparent" else "normal"
                        }
                    ),
                    html.Td(
                        f"Pot: {pot_before:,.6g} ({pot_before/bb_size:,.1f} bb)",
                        style={**_TD, "color": "var(--text-4, #888)", "fontSize": "12px"},
                    ),
                    html.Td(
                        extra,
                        style={**_TD, "color": "var(--text-3, #555)", "fontSize": "12px"},
                    ),
                    html.Td(  # Nueva celda EV
                        ev_cell_content,
                        style={
                            **_TD,
                            "fontSize": "12px",
                            "minWidth": "150px",
                            "whiteSpace": "normal",
                        },
                    ),
                ],
                style=_action_row_style(bool(action["is_hero"])),
            )
        )

    if current_street is not None:
        sections.append(_flush(current_street, street_rows))

    return sections


html.Div(
    style={
        "@keyframes fadeOut": {
            "0%": {"opacity": "1"},
            "100%": {"opacity": "0", "display": "none"}
        }
    }
)

def _load_ev_cache_for_hand(hand_id: int) -> dict[int, dict[str, object]]:
    """Carga el cache de EV para una mano específica."""
    db_path = _get_db_path()
    conn = get_connection(db_path)
    ev_cache = {}

    try:
        hero_id = _get_hero_player_id(db_path)
        if hero_id is None:
            return ev_cache

        old_factory = conn.row_factory
        conn.row_factory = sqlite3.Row
        for ev_row in conn.execute(
            """
            SELECT aec.*
            FROM action_ev_cache aec
            JOIN actions a ON aec.action_id = a.id
            WHERE a.hand_id = ? AND aec.hero_id = ?
            """,
            (hand_id, hero_id),
        ).fetchall():
            ev_cache[int(ev_row["action_id"])] = dict(ev_row)
        conn.row_factory = old_factory
    finally:
        conn.close()

    return ev_cache

def _get_db_path() -> str:
    """Get the database path from the app config."""
    result: str = dash.get_app().server.config.get("DB_PATH", ":memory:")  # type: ignore[no-untyped-call]
    return result


@callback(
    Output("copy-status-message", "children", allow_duplicate=True),
    Output("ai-analysis-store", "data"),
    Input("ai-analysis-btn", "n_clicks"),
    Input("hand-clipboard", "n_clicks"),  # Este es el componente dcc.Clipboard
    State("hand-state", "data"),
    State("hand-text-store", "data"),
    State("ai-analysis-store", "data"),
    State("hand-details-store", "data"),
    prevent_initial_call=True
)
def handle_ai_analysis_and_clipboard(
    ai_n_clicks,
    clipboard_n_clicks,
    hand_state,
    hand_text,
    current_analysis,
    hand_details
):
    """Maneja tanto el análisis con IA como la copia al portapapeles."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update, no_update

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    # Manejar clic en el botón de análisis con IA
    if triggered_id == "ai-analysis-btn" and (ai_n_clicks or 0) > 0:
        hand_id = hand_state["hand_id"]
        db_path = _get_db_path()
        conn = get_connection(db_path)

        try:
            if ai_n_clicks == 1 or current_analysis is None:
                analysis = analyze_hand_with_ai(conn, hand_id)

                if analysis["status"] == "success":
                    # Extraer source_id de hand_details o usar hand_id como fallback
                    hand_details = get_hand_details(conn, hand_id)
                    source_id = hand_details.get("source_hand_id", str(hand_id))

                    # Guardar en archivo
                    filepath = _save_analysis_to_file(str(source_id), hand_id, analysis["analysis"])

                    # Copiar al portapapeles usando JavaScript
                    return (
                        html.Div(
                            f"✅ Análisis guardado en {filepath} y copiado al portapapeles",
                            style={
                                "color": "#27ae60",
                                "fontSize": "14px",
                                "marginTop": "10px",
                                "animation": "fadeOut 4s ease-out forwards"
                            }
                        ),
                        analysis
                    )
                else:
                    return (
                        html.Div(
                            f"❌ Error: {analysis['error']}",
                            style={
                                "color": "#e74c3c",
                                "fontSize": "14px",
                                "marginTop": "10px"
                            }
                        ),
                        no_update
                    )
            else:
                # Si ya existe el análisis, copiar al portapapeles usando JavaScript
                return (
                    html.Div(
                        "✅ Análisis copiado al portapapeles",
                        style={
                            "color": "#27ae60",
                            "fontSize": "14px",
                            "marginTop": "10px",
                            "animation": "fadeOut 4s ease-out forwards"
                        }
                    ),
                    current_analysis
                )
        finally:
            conn.close()

    # Manejar clic en el componente Clipboard
    elif triggered_id == "hand-clipboard" and (clipboard_n_clicks or 0) > 0:
        return (
            html.Div(
                "✅ Historial copiado al portapapeles",
                style={
                    "color": "#27ae60",
                    "fontSize": "14px",
                    "marginTop": "10px",
                    "animation": "fadeOut 2s ease-out forwards"
                }
            ),
            no_update
        )

    return no_update, no_update

@callback(
    Output("hand-fav-btn-hand-page", "children"),
    Input("hand-fav-btn-hand-page", "n_clicks"),
    State("hand-fav-id-store", "data"),
    prevent_initial_call=True,
)
def _toggle_hand_fav(
    n_clicks: int | None,
    hand_id: int | None,
) -> tuple[list[str], dict[str, str]]:
    """Toggle favorite status for a hand."""
    if not n_clicks or hand_id is None:
        raise dash.exceptions.PreventUpdate

    from pokerhero.database.db import toggle_hand_favorite

    db_path = _get_db_path()
    conn = get_connection(db_path)
    try:
        toggle_hand_favorite(conn, int(hand_id))
        conn.commit()
        row = conn.execute(
            "SELECT is_favorite FROM hands WHERE id = ?", (int(hand_id),)
        ).fetchone()
    finally:
        conn.close()

    is_fav = bool(row and row[0])
    style: dict[str, str] = {
        "display": "flex",
        "alignItems": "center",
        "gap": "6px",
        "background": "#fff8ec" if is_fav else "var(--bg-2, #f5f5f5)",
        "border": "1px solid #f5a623" if is_fav else "1px solid var(--border-light, #ccc)",
        "borderRadius": "20px",
        "padding": "4px 12px",
        "fontSize": "15px",
        "cursor": "pointer",
        "color": "#f5a623" if is_fav else "var(--text-4, #888)",
        "fontWeight": "600",
        "lineHeight": "1.4",
    }
    return ["★" if is_fav else "☆", " Favourite hand"], style