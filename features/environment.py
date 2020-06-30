import json
import threading

from http.server import HTTPServer, BaseHTTPRequestHandler

def before_all(context):
    context.peer_queue = None

    class DummyPeeringHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            self.send_response(200)
            self.end_headers()
            if context.peer_queue is not None:
                context.peer_queue.put(json.loads(body))

    httpd = HTTPServer(('0.0.0.0', 31337), DummyPeeringHandler)
    context.peerserv = threading.Thread(target=httpd.serve_forever, daemon=True)
    context.peerserv.start()
