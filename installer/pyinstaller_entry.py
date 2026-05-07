"""PyInstaller entry point — uses absolute imports instead of relative."""

from pb_decryptor.app import App


if __name__ == "__main__":
    App().run()
