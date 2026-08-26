import socket
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

class ProxyCore:
    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 8080
        self.split_pos = 2
        self.running = False
        self.server_sock = None

    def start(self, port=8080, split_pos=2):
        self.port = int(port)
        self.split_pos = int(split_pos)
        self.running = True
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind((self.host, self.port))
            self.server_sock.listen(128)
            threading.Thread(target=self._listen, daemon=True).start()
            return True
        except Exception:
            self.running = False
            return False

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None

    def _listen(self):
        while self.running:
            try:
                client_sock, _ = self.server_sock.accept()
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
            except Exception:
                break

    def _handle_client(self, client_sock):
        try:
            client_sock.recv(262)
            client_sock.sendall(b'\x05\x00')
            data = client_sock.recv(4)
            if not data or data[0] != 5:
                client_sock.close()
                return

            atyp = data[3]
            if atyp == 1:
                dest_ip = socket.inet_ntoa(client_sock.recv(4))
            elif atyp == 3:
                domain_len = client_sock.recv(1)[0]
                dest_ip = client_sock.recv(domain_len).decode('utf-8')
            elif atyp == 4:
                dest_ip = socket.inet_ntop(socket.AF_INET6, client_sock.recv(16))
            else:
                client_sock.close()
                return

            dest_port = int.from_bytes(client_sock.recv(2), 'big')
            remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_sock.connect((dest_ip, dest_port))
            
            bind_addr = remote_sock.getsockname()
            client_sock.sendall(b'\x05\x00\x00\x01' + socket.inet_aton(bind_addr[0]) + bind_addr[1].to_bytes(2, 'big'))

            threading.Thread(target=self._pipe_desync, args=(client_sock, remote_sock), daemon=True).start()
            threading.Thread(target=self._pipe_raw, args=(remote_sock, client_sock), daemon=True).start()
        except Exception:
            try:
                client_sock.close()
            except Exception:
                pass

    def _pipe_desync(self, src, dst):
        try:
            first_chunk = src.recv(4096)
            if first_chunk:
                if len(first_chunk) > self.split_pos:
                    dst.sendall(first_chunk[:self.split_pos])
                    dst.sendall(first_chunk[self.split_pos:])
                else:
                    dst.sendall(first_chunk)
            self._pipe_raw(src, dst)
        except Exception:
            pass
        finally:
            try:
                src.close()
                dst.close()
            except Exception:
                pass

    def _pipe_raw(self, src, dst):
        try:
            while self.running:
                buf = src.recv(4096)
                if not buf:
                    break
                dst.sendall(buf)
        except Exception:
            pass
        finally:
            try:
                src.close()
                dst.close()
            except Exception:
                pass

proxy = ProxyCore()

HTML_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>BratvaDPI</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; user-select: none; -webkit-tap-highlight-color: transparent; }
        body { background-color: #121212; color: #E0E0E0; padding: 16px; }
        .container { width: 100%; display: flex; flex-direction: column; gap: 16px; }
        .app-bar { padding: 8px 4px 4px 4px; display: flex; align-items: center; justify-content: space-between; }
        .app-title { font-size: 20px; font-weight: 600; color: #FFFFFF; }
        .badge { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 4px; background-color: #212121; color: #757575; }
        .badge.active { background-color: rgba(33, 150, 243, 0.15); color: #2196F3; }
        .status-card { background-color: #1E1E1E; border-radius: 12px; padding: 20px; display: flex; align-items: center; justify-content: space-between; border: 1px solid #2C2C2C; }
        .status-info { display: flex; flex-direction: column; gap: 4px; }
        .status-title { font-size: 16px; font-weight: 600; color: #FFFFFF; }
        .status-subtitle { font-size: 13px; color: #757575; }
        .status-subtitle.active { color: #2196F3; }
        .switch { position: relative; display: inline-block; width: 52px; height: 30px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #333333; transition: .25s; border-radius: 30px; }
        .slider:before { position: absolute; content: ""; height: 22px; width: 22px; left: 4px; bottom: 4px; background-color: #9E9E9E; transition: .25s; border-radius: 50%; }
        input:checked + .slider { background-color: #2196F3; }
        input:checked + .slider:before { transform: translateX(22px); background-color: #FFFFFF; }
        .section-title { font-size: 12px; font-weight: 600; text-transform: uppercase; color: #616161; padding: 4px 4px 0 4px; }
        .settings-card { background-color: #1E1E1E; border-radius: 12px; border: 1px solid #2C2C2C; overflow: hidden; }
        .setting-item { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; }
        .setting-item:not(:last-child) { border-bottom: 1px solid #282828; }
        .setting-label { display: flex; flex-direction: column; gap: 2px; }
        .setting-name { font-size: 14px; color: #EEEEEE; font-weight: 500; }
        .setting-desc { font-size: 12px; color: #757575; }
        .setting-input { width: 76px; background-color: #282828; border: 1px solid #383838; border-radius: 6px; color: #2196F3; font-size: 14px; font-weight: 600; text-align: center; padding: 6px 8px; outline: none; }
        .setting-input:focus { border-color: #2196F3; }
        .setting-input:disabled { opacity: 0.5; color: #757575; }
        .footer { margin-top: 30px; text-align: center; font-size: 12px; color: #424242; }
    </style>
</head>
<body>
    <div class="container">
        <div class="app-bar">
            <span class="app-title">BratvaDPI</span>
            <span id="badge" class="badge">SOCKS5</span>
        </div>
        <div class="status-card">
            <div class="status-info">
                <span id="statusTitle" class="status-title">Отключено</span>
                <span id="statusSub" class="status-subtitle">Служба остановлена</span>
            </div>
            <label class="switch">
                <input type="checkbox" id="toggleSwitch" onchange="toggleProxy()">
                <span class="slider"></span>
            </label>
        </div>
        <div class="section-title">Параметры соединения</div>
        <div class="settings-card">
            <div class="setting-item">
                <div class="setting-label">
                    <span class="setting-name">Локальный порт</span>
                    <span class="setting-desc">Входящий SOCKS5 порт</span>
                </div>
                <input type="number" id="port" class="setting-input" value="8080">
            </div>
            <div class="setting-item">
                <div class="setting-label">
                    <span class="setting-name">Split Позиция</span>
                    <span class="setting-desc">Разбиение пакета (байты)</span>
                </div>
                <input type="number" id="split" class="setting-input" value="2">
            </div>
        </div>
        <div class="footer">127.0.0.1 • TCP Desync Core</div>
    </div>
    <script>
        let isRunning = false;
        async function toggleProxy() {
            const toggle = document.getElementById('toggleSwitch');
            const port = document.getElementById('port').value;
            const split = document.getElementById('split').value;
            const statusTitle = document.getElementById('statusTitle');
            const statusSub = document.getElementById('statusSub');
            const badge = document.getElementById('badge');
            const portInp = document.getElementById('port');
            const splitInp = document.getElementById('split');

            if (toggle.checked) {
                const res = await fetch('/api/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({port: parseInt(port), split: parseInt(split)})
                });
                const data = await res.json();
                if (data.success) {
                    isRunning = true;
                    statusTitle.textContent = 'Подключено';
                    statusSub.textContent = '127.0.0.1:' + port;
                    statusSub.classList.add('active');
                    badge.classList.add('active');
                    portInp.disabled = true;
                    splitInp.disabled = true;
                } else {
                    toggle.checked = false;
                }
            } else {
                await fetch('/api/stop', {method: 'POST'});
                isRunning = false;
                statusTitle.textContent = 'Отключено';
                statusSub.textContent = 'Служба остановлена';
                statusSub.classList.remove('active');
                badge.classList.remove('active');
                portInp.disabled = false;
                splitInp.disabled = false;
            }
        }
    </script>
</body>
</html>
"""

class UIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode('utf-8'))

    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_len)
        data = json.loads(post_data.decode('utf-8')) if post_data else {}

        if self.path == '/api/start':
            p = data.get('port', 8080)
            s = data.get('split', 2)
            success = proxy.start(p, s)
            res = {"success": success}
        elif self.path == '/api/stop':
            proxy.stop()
            res = {"success": True}
        else:
            res = {"error": "unknown"}

        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(res).encode('utf-8'))

    def log_message(self, format, *args):
        return

def start_server():
    server = HTTPServer(('127.0.0.1', 5000), UIHandler)
    server.serve_forever()
