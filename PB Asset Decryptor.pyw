"""Double-click launcher for PB Asset Decryptor (no console window)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pb_decryptor.app import App

App().run()
