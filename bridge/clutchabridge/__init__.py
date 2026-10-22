"""Clutcha Bridge — moves encrypted mail between the Clutcha app and an agent.

The bridge is transport only: it decrypts, hands the text to a command line,
encrypts the answer and sends it back. Conversation state, tools and memory
belong to the runtime (pi, or any CLI command).
"""

__version__ = "1.0.0"

APP_NAME = "Clutcha Bridge"
WIRE_NAME = "vmessager"  # KDF context strings — changing these breaks the app.
