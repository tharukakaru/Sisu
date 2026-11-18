"""Serve marketing/ locally with the same routes as production nginx (scripts/main-domain-https.conf).

/            -> marketing/index.html, and /students/, /teachers/, ... -> their index.html
/marketing/* -> marketing/* (production aliases this path to the same release folder)
/campus      -> local LMS preview (frontend `npm run dev`), since the real LMS is not running here

Usage: python scripts/serve-marketing-local.py [port]   (default 5180, loopback only)
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'marketing'
CAMPUS = 'http://127.0.0.1:5178/?preview=1'


class Handler(SimpleHTTPRequestHandler):
    def route(self):
        """Return True when the request was answered with a redirect."""
        path = self.path.split('?', 1)[0]
        if path == '/campus' or path.startswith('/campus/'):
            self.send_response(302)
            self.send_header('Location', CAMPUS)
            self.end_headers()
            return True
        if path == '/marketing' or path.startswith('/marketing/'):
            self.path = self.path[len('/marketing'):] or '/'
        return False

    def do_GET(self):
        if not self.route():
            super().do_GET()

    def do_HEAD(self):
        if not self.route():
            super().do_HEAD()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')  # edits show on a normal refresh
        super().end_headers()


if __name__ == '__main__':
    sys.stdout.reconfigure(line_buffering=True)  # show the URL and stale-image warning even when output is piped
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5180
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from optimize_landing_images import stale
        if old := stale():
            print('WARNING: these images changed but their WebP/AVIF copies did not, so the site still shows the old picture.')
            print('  Run: python scripts/optimize_landing_images.py ' + ' '.join(old))
    except ImportError:  # Pillow missing: serving still works, the check is skipped
        pass
    print(f'Marketing site: http://127.0.0.1:{port}/')
    ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=str(ROOT))).serve_forever()
