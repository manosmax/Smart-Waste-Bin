import http.server

class YAMLHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        if self.path.endswith('.yml'):
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
        super().end_headers()

http.server.HTTPServer(('', 5002), YAMLHandler).serve_forever()

