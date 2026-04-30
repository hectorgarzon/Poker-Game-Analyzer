# Constantes de color
COLOR_GREEN = "green"
COLOR_YELLOW = "#CC9900"  # Golden
COLOR_RED = "red"
COLOR_DEFAULT = "var(--text-1, #333)"

# Umbrales generales
THRESHOLD_LOW = 22
THRESHOLD_HIGH = 35

def _get_traffic_light_color(value: float, low: int, high: int) -> str:
    """Generic function to determine color based on ranges."""
    if value < low:
        return COLOR_GREEN
    if low <= value <= high:
        return COLOR_YELLOW
    if value > high:
        return COLOR_RED
    return COLOR_DEFAULT

def get_vpip_color(vpip: float) -> str:
    """Returns a color according to VPIP range values."""
    return _get_traffic_light_color(vpip, 22, 35)

def get_pfr_color(pfr: float) -> str:
    """Returns a color according to PFR range values."""
    return _get_traffic_light_color(pfr, 22, 35)

def get_3bet_color(three_bet: float) -> str:
    """Returns a color according to 3-Bet range values."""
    return _get_traffic_light_color(three_bet, 10, 25)

def get_limp_color(limp: float) -> str:
    """Returns a color according to Limp range values."""
    return _get_traffic_light_color(limp, 5, 10)