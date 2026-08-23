import socket
import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.core.window import Window

Window.clearcolor = (0.12, 0.12, 0.12, 1)

class ProxyCore:
    def __init__(self, host='127.0.0.1', port=8080, split_pos=2):
        self.host = host
        self.port = int(port)
        self.split_pos = int(split_pos)
        self.running = False
        self.server_sock = None

    def start(self):
        self.running = True
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(128)
        threading.Thread(target=self._listen, daemon=True).start()

    def stop(self):
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except:
                pass

    def _listen(self):
        while self.running:
            try:
                client_sock, _ = self.server_sock.accept()
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
            except:
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
        except:
            try:
                client_sock.close()
            except:
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
        except:
            pass
        finally:
            try:
                src.close()
                dst.close()
            except:
                pass

    def _pipe_raw(self, src, dst):
        try:
            while self.running:
                buf = src.recv(4096)
                if not buf:
                    break
                dst.sendall(buf)
        except:
            pass
        finally:
            try:
                src.close()
                dst.close()
            except:
                pass

class BratvaDPI(App):
    def build(self):
        self.proxy = ProxyCore()
        layout = BoxLayout(orientation='vertical', padding=30, spacing=15)
        
        title = Label(
            text='[b]BratvaDPI[/b]',
            markup=True,
            font_size='28sp',
            size_hint_y=0.2,
            color=(0.9, 0.9, 0.9, 1)
        )
        layout.add_widget(title)

        self.status_label = Label(
            text='Статус: Остановлен',
            font_size='16sp',
            size_hint_y=0.15,
            color=(0.8, 0.2, 0.2, 1)
        )
        layout.add_widget(self.status_label)

        self.port_input = TextInput(
            text='8080',
            multiline=False,
            hint_text='SOCKS5 Port',
            size_hint_y=0.15,
            background_color=(0.2, 0.2, 0.2, 1),
            foreground_color=(1, 1, 1, 1)
        )
        layout.add_widget(self.port_input)

        self.split_input = TextInput(
            text='2',
            multiline=False,
            hint_text='Split Position (Bytes)',
            size_hint_y=0.15,
            background_color=(0.2, 0.2, 0.2, 1),
            foreground_color=(1, 1, 1, 1)
        )
        layout.add_widget(self.split_input)

        self.btn_toggle = Button(
            text='Запустить',
            size_hint_y=0.2,
            background_color=(0.1, 0.6, 0.3, 1),
            font_size='18sp'
        )
        self.btn_toggle.bind(on_press=self.toggle_proxy)
        layout.add_widget(self.btn_toggle)

        return layout

    def toggle_proxy(self, instance):
        if not self.proxy.running:
            try:
                port = int(self.port_input.text)
                split_pos = int(self.split_input.text)
                self.proxy.port = port
                self.proxy.split_pos = split_pos
                self.proxy.start()
                self.status_label.text = f'Статус: Работает (127.0.0.1:{port})'
                self.status_label.color = (0.2, 0.8, 0.2, 1)
                self.btn_toggle.text = 'Остановить'
                self.btn_toggle.background_color = (0.8, 0.2, 0.2, 1)
            except:
                self.status_label.text = 'Ошибка запуска'
        else:
            self.proxy.stop()
            self.status_label.text = 'Статус: Остановлен'
            self.status_label.color = (0.8, 0.2, 0.2, 1)
            self.btn_toggle.text = 'Запустить'
            self.btn_toggle.background_color = (0.1, 0.6, 0.3, 1)

if __name__ == '__main__':
    BratvaDPI().run()
