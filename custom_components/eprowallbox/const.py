"""Constants for the eProWallbox integration."""

DOMAIN = "eprowallbox"

DEFAULT_PORT = 502  # port Modbus TCP standard

FRONTEND_SCRIPT_URL = f"/{DOMAIN}/{DOMAIN}-card.js"
# À incrémenter avec la version de la carte pour contourner le cache du navigateur
FRONTEND_VERSION = "0.3.0"
