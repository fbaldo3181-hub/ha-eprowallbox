"""Constants for the eProWallbox integration."""

DOMAIN = "eprowallbox"

DEFAULT_PORT = 502  # port par défaut (à adapter selon la passerelle RS485/TCP)

# Type de trame Modbus utilisée sur la connexion TCP :
#  - "socket" : Modbus TCP standard (MBAP)
#  - "rtu"    : Modbus RTU encapsulé dans TCP (« rs485tcpip » dans evcc), c'est
#               ce qu'attend l'eProWallbox Move derrière une passerelle RS485/IP
CONF_FRAMER = "framer"
FRAMER_SOCKET = "socket"
FRAMER_RTU = "rtu"
FRAMERS = [FRAMER_RTU, FRAMER_SOCKET]
DEFAULT_FRAMER = FRAMER_SOCKET

FRONTEND_SCRIPT_URL = f"/{DOMAIN}/{DOMAIN}-card.js"
# À incrémenter avec la version de la carte pour contourner le cache du navigateur
FRONTEND_VERSION = "0.3.0"
