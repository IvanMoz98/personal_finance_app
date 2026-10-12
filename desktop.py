"""Point d'entrée de l'application de bureau : serveur Flask local + fenêtre native (pywebview).

C'est ce fichier que PyInstaller transforme en .exe / .app. Pour développer, il suffit de lancer
`python desktop.py` (fenêtre native) ou `python app.py` (dans le navigateur).
"""
import socket
import threading

import webview
from werkzeug.serving import make_server

from app import app
from db import APP_NAME, init_db


def free_port() -> int:
    """Port libre choisi par le système, pour ne jamais entrer en conflit avec un autre programme."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    init_db()
    port = free_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    webview.create_window(
        APP_NAME, f"http://127.0.0.1:{port}/",
        width=1320, height=860, min_size=(900, 600),
    )
    webview.start()  # bloque jusqu'à la fermeture de la fenêtre
    server.shutdown()


if __name__ == "__main__":
    main()
