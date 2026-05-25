import http.server

class YAMLHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        if self.path.endswith('.yml'):
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

def main():
    http.server.HTTPServer(('', 5002), YAMLHandler).serve_forever()

if __name__ == "__main__":
    main()
