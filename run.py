"""MethodFlow launcher.

Usage:
    python run.py                      # use config.json / defaults (127.0.0.1:8780, data in .\\data)
    python run.py --port 8790          # override port
    python run.py --host 0.0.0.0       # listen on all interfaces (LAN) - read README first
    python run.py --data D:\\mf_data    # use another data folder
    python run.py --no-browser         # do not open the browser automatically

Command-line options override config.json, which overrides the built-in defaults.
"""
import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))


def _say(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:  # console with a legacy code page
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def _port_in_use(host, port):
    probe = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((probe, port)) == 0


def _open_browser_when_up(url, host, port, timeout=30.0):
    probe = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection((probe, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.3)
    else:
        return
    try:
        webbrowser.open(url)
    except Exception:  # pragma: no cover
        pass


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="MethodFlow - analytical method development management")
    ap.add_argument("--host", help="listen address (default from config.json, normally 127.0.0.1)")
    ap.add_argument("--port", type=int, help="listen port (default from config.json, normally 8780)")
    ap.add_argument("--data", help="data folder (db, uploads, backups, documents); default .\\data")
    ap.add_argument("--no-browser", action="store_true", help="do not open the web browser")
    args = ap.parse_args()

    os.chdir(HERE)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)

    # app.config reads these environment variables when it is imported, so set them first
    if args.data:
        os.environ["METHODFLOW_DATA"] = os.path.abspath(args.data)
    if args.host:
        os.environ["METHODFLOW_HOST"] = args.host
    if args.port:
        os.environ["METHODFLOW_PORT"] = str(args.port)

    try:
        from app import config
    except ImportError as e:
        _say("Cannot start: %s" % e)
        _say("Missing packages? Run:  python -m pip install -r requirements.txt")
        return 1

    host, port = config.get("host"), int(config.get("port"))
    if _port_in_use(host, port):
        _say("Port %d is already in use - MethodFlow may already be running." % port)
        _say("Open http://127.0.0.1:%d/ or choose another port:  python run.py --port %d" % (port, port + 1))
        return 2

    shown_host = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    url = "http://%s:%d/" % (shown_host, port)
    _say("=" * 60)
    _say(" MethodFlow  |  URL: %s" % url)
    _say(" Data folder : %s" % config.DATA)
    if host not in ("127.0.0.1", "localhost", "::1"):
        _say(" WARNING: listening on %s - reachable from other computers." % host)
        _say("          Use an HTTPS reverse proxy and a firewall (see README).")
    _say(" Press Ctrl+C (or close this window) to stop the server.")
    _say("=" * 60)

    if not args.no_browser:
        threading.Thread(target=_open_browser_when_up, args=(url, host, port), daemon=True).start()

    try:
        from app import main as app_main
        app_main.run()
    except KeyboardInterrupt:
        _say("Stopped.")
    except OSError as e:
        _say("Server error: %s" % e)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
