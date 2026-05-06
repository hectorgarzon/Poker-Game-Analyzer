"""Hand detail page - shows a single hand's action sequence."""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlparse

import dash
import pandas as pd
from dash import Input, Output, State, callback, dcc, html
from dash.development.base_component import Component

from pokerhero.database.db import get_connection, get_setting, upsert_player
from pokerhero.analysis.queries import get_actions, get_hand_details

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
    opp_stats: pd.DataFrame | None = None,  # Ahora acepta DataFrame
    min_hands: int = 15,
    hero_net_result: float | None = None,
) -> html.Div | None:
    """Build a Showdown section showing all players' cards."""
    if not villain_rows:
        return None

    # Build the full list of players at showdown
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

    # Render one row per player
    rows: list[html.Div] = []
    for label, hole in players:
        # Archetype badge
        archetype_badge: list[Component] = []
        username = label_to_username.get(label)

        if opp_stats is not None and username:
            # Buscar stats para este usuario en el DataFrame
            user_stats = opp_stats[opp_stats['username'] == username]
            if not user_stats.empty:
                from pokerhero.analysis.stats import classify_player

                s = user_stats.iloc[0]
                h = int(s["hands_played"])
                vp = int(s["vpip_count"]) / h * 100 if h > 0 else 0.0
                pf = int(s["pfr_count"]) / h * 100 if h > 0 else 0.0
                archetype = classify_player(vp, pf, h, min_hands=min_hands)
                if archetype is not None:
                    arch_label, arch_extras = _archetype_badge_attrs(archetype, h)
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
                                "verticalAlign": "middle",
                                **arch_extras,
                            },
                        )
                    ]

        rows.append(
            html.Div(
                [
                    html.Span(
                        f"{label}: ",
                        style={
                            "fontWeight": "600",
                            "fontSize": "13px",
                            "marginRight": "6px",
                        },
                    ),
                    *archetype_badge,
                    _render_cards(hole),
                    *(
                        [
                            html.Span(
                                f"({_fmt_pnl(label_to_result[label])})",
                                style={
                                    "fontSize": "12px",
                                    "fontWeight": "600",
                                    "marginLeft": "8px",
                                    "color": (
                                        "#28a745"
                                        if label_to_result[label] >= 0
                                        else "#dc3545"
                                    ),
                                },
                            )
                        ]
                        if label in label_to_result
                        else []
                    ),
                ],
                style={"marginBottom": "4px"},
            )
        )

    return html.Div(
        [
            html.H5(
                "Showdown",
                style={
                    "color": "#a855f7",
                    "borderBottom": "2px solid #a855f7",
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

def layout(hand_id: int | str | None = None) -> Component:
    """Layout principal de la página de mano."""
    if hand_id is None:
        return html.Div("ID de mano no proporcionado", style={"color": "red"})

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
                "← Volver a Sesiones",
                href="/sessions",
                style={"fontSize": "13px", "color": "#0074D9"},
            ),
            html.Hr(),
            dcc.Loading(html.Div(id="hand-content")),
            dcc.Store(id="hand-state", data={"hand_id": int(hand_id)}),
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
        return _render_hand_view(hand_id, hand_details, actions_df)

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
    hero_name = hand_details.get("hero_name", "Hero")
    hero_net_result = hand_details.get("hero_net_result")
    hand_is_fav = hand_details.get("is_favorite", False)
    session_id = hand_details.get("session_id", 0)

    # Sección de información básica
    header_children = [
        html.Div(
            [
                html.H3(f"Hand #{source_id}", style={"marginTop": "0", "marginBottom": "0"}),
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
        dcc.Store(id="hand-fav-id-store", data=hand_id),
    ]

    if hero_cards:
        header_children.append(
            html.Div(
                [
                    html.Span(
                        f"{hero_name}: ",
                        style={
                            "fontWeight": "600",
                            "fontSize": "13px",
                            "marginRight": "6px",
                            "color": "var(--text-3, #555)",
                        },
                    ),
                    _render_cards(hero_cards),
                ],
                style={"marginBottom": "8px"},
            )
        )

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
    sections = _build_action_sections(actions_df, flop, turn, river)

    # Showdown
    board_str = " ".join(p for p in [flop, turn, river] if p)
    showdown_div = _build_showdown_section(
        hand_details.get("villain_showdown", []),
        hero_name=hero_name,
        hero_cards=hero_cards,
        board=board_str,
        opp_stats=hand_details.get("opp_stats"),
        hero_net_result=hero_net_result,
    )

    if showdown_div is not None:
        sections.append(showdown_div)

    return html.Div([*header_children, board_div, *sections])

def _build_action_sections(
    df: pd.DataFrame,
    flop: str,
    turn: str,
    river: str
) -> list[Component]:
    """Construye las secciones de acciones por calle."""
    sections: list[html.Div] = []
    current_street: str | None = None
    street_rows: list[html.Tr] = []

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
                    rows,
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

        street_rows.append(
            html.Tr(
                [
                    html.Td(
                        actor_str,
                        style={**_TD, "width": "200px", "fontWeight": "600"},
                    ),
                    html.Td(label, style=_TD),
                    html.Td(
                        f"Pot: {pot_before:,.6g}",
                        style={
                            **_TD,
                            "color": "var(--text-4, #888)",
                            "fontSize": "12px",
                        },
                    ),
                    html.Td(
                        extra,
                        style={
                            **_TD,
                            "color": "var(--text-3, #555)",
                            "fontSize": "12px",
                        },
                    ),
                ],
                style=_action_row_style(bool(action["is_hero"])),
            )
        )

    if current_street is not None:
        sections.append(_flush(current_street, street_rows))

    return sections

def _get_db_path() -> str:
    """Get the database path from the app config."""
    result: str = dash.get_app().server.config.get("DB_PATH", ":memory:")  # type: ignore[no-untyped-call]
    return result

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