import sqlite3
from datetime import datetime

def generate_hand_text(conn: sqlite3.Connection, hand_id: int) -> str:
    """Genera el texto de la mano en formato PokerStars usando datos de la BD."""
    cursor = conn.cursor()

    # 1. Datos básicos de la mano y sesión
    cursor.execute("""
        SELECT h.source_hand_id, h.timestamp, s.small_blind, s.big_blind, s.currency,
               s.game_type, h.board_flop, h.board_turn, h.board_river, h.total_pot
        FROM hands h
        JOIN sessions s ON h.session_id = s.id
        WHERE h.id = ?
    """, (hand_id,))
    hand = cursor.fetchone()
    if not hand:
        return "Mano no encontrada."

    s_id, ts, sb, bb, curr, gtype, flop, turn, river, total_pot = hand

    # 2. Jugadores (usamos net_result como aproximación del stack inicial)
    cursor.execute("""
        SELECT p.username, hp.position, hp.hole_cards, hp.starting_stack, hp.net_result
        FROM hand_players hp
        JOIN players p ON hp.player_id = p.id
        WHERE hp.hand_id = ?
        ORDER BY hp.position
    """, (hand_id,))
    players = cursor.fetchall()

    # 3. Acciones
    cursor.execute("""
        SELECT p.username, a.street, a.action_type, a.amount, a.is_all_in
        FROM actions a
        JOIN players p ON a.player_id = p.id
        WHERE a.hand_id = ?
        ORDER BY a.sequence ASC
    """, (hand_id,))
    actions = cursor.fetchall()

    # Identificar al héroe
    hero_row = next((p for p in players if p[2]), None)
    hero_name = hero_row[0] if hero_row else "Hero"

    # Calcular stacks iniciales aproximados
    # Usamos un valor base alto (10000) y ajustamos según net_result
    base_stack = 10000
    players_with_stacks = []
    for name, pos, cards, stack, res in players:
        players_with_stacks.append((name, pos, cards, stack, res))

    # Construcción del texto
    lines = []
    lines.append(f"PokerStars Hand #{s_id}: {gtype} ({sb}/{bb}) - {ts}")
    lines.append(f"Table 'PokerHero' 6-max Seat #{_get_button_seat(players)} is the button")

    # Asientos y stacks aproximados
    for i, (name, pos, cards, stack, res) in enumerate(players_with_stacks):
        lines.append(f"Seat {i+1}: {name} ({stack} in chips)")

    # Posts
    for name, street, a_type, amt, is_ai in actions:
        if a_type in ('SMALL_BLIND', 'BIG_BLIND'):
            lines.append(f"{name}: posts {a_type.lower().replace('_', ' ')} {amt}")

    lines.append("*** HOLE CARDS ***")
    if hero_row and hero_row[2]:
        lines.append(f"Dealt to {hero_name} [{hero_row[2]}]")

    # Acciones por calle
    curr_street = 'PREFLOP'
    for name, street, a_type, amt, is_ai in actions:
        if a_type in ('SMALL_BLIND', 'BIG_BLIND'): continue

        if street != curr_street:
            if street == 'FLOP': lines.append(f"*** FLOP *** [{flop}]")
            elif street == 'TURN': lines.append(f"*** TURN *** [{flop}] [{turn}]")
            elif street == 'RIVER': lines.append(f"*** RIVER *** [{flop} {turn}] [{river}]")
            curr_street = street

        act = a_type.lower()
        line = f"{name}: {act}"
        if amt > 0: line += f" {amt}"
        if is_ai: line += " and is all-in"
        lines.append(line)

    # Showdown y ganadores
    if any(p[4] > 0 for p in players_with_stacks):  # Si hay ganadores
        lines.append("*** SHOW DOWN ***")

        # Mostrar cartas de los jugadores que fueron al showdown
        for name, _, cards, _, res in players_with_stacks:
            if cards:  # Si tiene cartas, fue al showdown
                lines.append(f"{name}: shows [{cards}]")

        # Mostrar ganadores
        for name, _, _, stack, res in players_with_stacks:
            if res > 0:
                # La cantidad ganada es el net_result + lo que tenía inicialmente
                amount_won = res + (stack - base_stack)
                pot_type = "main pot" if amount_won == total_pot else "side pot"
                lines.append(f"{name} collected {amount_won} from {pot_type}")

    lines.append("*** SUMMARY ***")
    lines.append(f"Total pot {total_pot} | Rake 0")
    board = " ".join(filter(None, [flop, turn, river]))
    if board:
        lines.append(f"Board [{board}]")

    return "\n".join(lines)

def _get_button_seat(players):
    """Determina qué asiento tiene el botón (posición 0 en PokerStars)."""
    # En PokerStars, el botón es el primer asiento (Seat 1)
    return 1