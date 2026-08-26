import socket
import threading
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

class ProxyCore:
    def __init__(self, host='127.0.0.1', port=8080, split_pos=2):
        self.host = host
        self.port = int(port)
        self.split_pos = int(split_pos)
        self.running = False
        self.server_sock = None

    def start(self):
        self.running = True
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind((self.host, self.port))
            self.server_sock.listen(128)
            threading.Thread(target=self._listen, daemon=True).start()
        except Exception:
            self.running = False

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass

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

class BratvaDPIApp(toga.App):
    def startup(self):
        self.proxy = ProxyCore()

        main_box = toga.Box(style=Pack(direction=COLUMN, padding=20, alignment=CENTER))

        title_label = toga.Label(
            "BratvaDPI",
            style=Pack(padding_bottom=15, font_size=20, font_weight="bold")
        )

        self.status_label = toga.Label(
            "Статус: Остановлен",
            style=Pack(padding_bottom=15)
        )

        self.port_input = toga.TextInput(
            value="8080",
            placeholder="Порт SOCKS5",
            style=Pack(padding_bottom=10, width=200)
        )

        self.split_input = toga.TextInput(
            value="2",
            placeholder="Split Position",
            style=Pack(padding_bottom=20, width=200)
        )

        self.toggle_button = toga.Button(
            "Запустить",
            on_press=self.toggle_proxy,
            style=Pack(width=200, height=45)
        )

        main_box.add(title_label)
        main_box.add(self.status_label)
        main_box.add(self.port_input)
        main_box.add(self.split_input)
        main_box.add(self.toggle_button)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = main_box
        self.main_window.show()

    def toggle_proxy(self, widget):
        if not self.proxy.running:
            try:
                port = int(self.port_input.value)
                split_pos = int(self.split_input.value)
                self.proxy.port = port
                self.proxy.split_pos = split_pos
                self.proxy.start()
                self.status_label.text = f"Статус: Работает (127.0.0.1:{port})"
                self.toggle_button.text = "Остановить"
            except Exception:
                self.status_label.text = "Ошибка параметров"
        else:
            self.proxy.stop()
            self.status_label.text = "Статус: Остановлен"
            self.toggle_button.text = "Запустить"

def main():
    return BratvaDPIApp()
