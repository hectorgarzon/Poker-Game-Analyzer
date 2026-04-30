def get_vpip_color(vpip: float) -> str:
    """Returns a color according to the VPIP range values."""
    if vpip < 22:
        return "green"
    if 22 <= vpip <= 35:
        return "#CC9900"  # Golden because yellow with white background is unreadable
    if vpip > 35:
        return "red"
    return "var(--text-1, #333)"