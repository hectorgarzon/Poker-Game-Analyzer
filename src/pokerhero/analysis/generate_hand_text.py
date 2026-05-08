import sqlite3

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

    # 2. Jugadores (Asientos y Stacks aproximados usando net_result como referencia)
    cursor.execute("""
        SELECT p.username, hp.position, hp.hole_cards, hp.net_result
        FROM hand_players hp
        JOIN players p ON hp.player_id = p.id
        WHERE hp.hand_id = ?
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

    hero_row = next((p for p in players if p[2]), None)
    hero_name = hero_row[0] if hero_row else "Hero"

    lines = []
    lines.append(f"PokerStars Hand #{s_id}: {gtype} ({sb}/{bb}) - {ts}")
    lines.append(f"Table 'PokerHero' 6-max Seat #1 is the button")

    for i, (name, pos, cards, res) in enumerate(players):
        # Stack inicial real no se guarda, usamos un valor genérico o el neto
        lines.append(f"Seat {i+1}: {name} (10000 in chips)")

    # Posts
    for name, street, a_type, amt, is_ai in actions:
        if a_type in ('SMALL_BLIND', 'BIG_BLIND'):
            lines.append(f"{name}: posts {a_type.lower().replace('_', ' ')} {amt}")

    lines.append("*** HOLE CARDS ***")
    if hero_row and hero_row[2]:
        lines.append(f"Dealt to {hero_name} [{hero_row[2]}]")

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

    # Ganadores (basado en net_result positivo)
    winners = [p for p in players if p[3] and p[3] > 0]
    for w_name, _, w_cards, w_res in winners:
        if w_cards:
            lines.append(f"*** SHOW DOWN ***")
            lines.append(f"{w_name}: shows [{w_cards}]")
        lines.append(f"{w_name} collected {w_res + (total_pot/len(winners) if total_pot else 0)} from pot")

    lines.append("*** SUMMARY ***")
    lines.append(f"Total pot {total_pot} | Board [{' '.join(filter(None, [flop, turn, river]))}]")

    return "\n".join(lines)