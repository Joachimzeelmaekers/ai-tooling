#!/usr/bin/env python3
import http.server
import socketserver
import subprocess
import os
import webbrowser

PORT = 9999
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(TOOL_DIR, "output")

class RegeneratingHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(302)
            self.send_header('Location', '/latest.html')
            self.end_headers()
            return
        if self.path == '/latest.html' or self.path.endswith('.html'):
            print('Regenerating report...')
            subprocess.run(['python3', 'main.py'], cwd=TOOL_DIR)
        return super().do_GET()

os.chdir(OUTPUT_DIR)
with socketserver.TCPServer(('', PORT), RegeneratingHandler) as httpd:
    url = f'http://localhost:{PORT}/latest.html'
    print(f'Serving at {url}')
    print('Regenerates on each page refresh')
    webbrowser.open(url)
    httpd.serve_forever()
