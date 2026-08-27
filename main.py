import flet as ft
import asyncio
import threading
import sys
import webbrowser
import subprocess

class LocalDPIProxy:
    def __init__(self, host, port, split_pos, log_callback):
        self.host = host
        self.port = port
        self.split_pos = int(split_pos)
        self.log_callback = log_callback
        self.server = None
        self.loop = None
        self.is_running = False

    async def handle_client(self, reader, writer):
        try:
            initial_data = await reader.read(8192)
            if not initial_data:
                writer.close()
                return

            first_line = initial_data.split(b'\r\n')[0].decode('utf-8', errors='ignore')
            
            if first_line.startswith('CONNECT'):
                target_str = first_line.split(' ')[1]
                target_host, target_port = target_str.split(':')
                target_port = int(target_port)

                writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                await writer.drain()

                server_reader, server_writer = await asyncio.open_connection(target_host, target_port)
                client_hello = await reader.read(8192)
                
                if client_hello:
                    self.log_callback(f"[+] Перехват -> {target_host}", "#90CAF9")
                    
                    server_writer.write(client_hello[:self.split_pos])
                    await server_writer.drain()
                    
                    await asyncio.sleep(0.05)
                    
                    server_writer.write(client_hello[self.split_pos:])
                    await server_writer.drain()

                await asyncio.gather(
                    self.forward_stream(reader, server_writer),
                    self.forward_stream(server_reader, writer)
                )
            else:
                writer.close()

        except Exception:
            pass
        finally:
            writer.close()

    async def forward_stream(self, source_reader, dest_writer):
        try:
            while True:
                data = await source_reader.read(8192)
                if not data:
                    break
                dest_writer.write(data)
                await dest_writer.drain()
        except Exception:
            pass
        finally:
            dest_writer.close()

    async def start_server(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        self.log_callback(f"[*] Движок запущен на {self.host}:{self.port}", "#4CAF50")
        async with self.server:
            await self.server.serve_forever()

    def run_in_thread(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.is_running = True
        try:
            self.loop.run_until_complete(self.start_server())
        except asyncio.CancelledError:
            pass
        finally:
            self.loop.close()

    def stop(self):
        self.is_running = False
        if self.server:
            self.server.close()
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)


class BratvaDPIApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.proxy = None
        self.proxy_thread = None

        self.setup_window()
        self.build_ui()

    def setup_window(self):
        self.page.title = "BratvaDPI"
        self.page.window.width = 460
        self.page.window.height = 700
        self.page.bgcolor = "#161616"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0 

        self.page.fonts = {
            "InterLight": "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter-Light.ttf",
        }
        self.page.theme = ft.Theme(font_family="InterLight")

    def build_ui(self):
        self.ip_input = ft.TextField(
            label="IP адрес", value="127.0.0.1", text_size=13, height=48,
            border_color="#333333", focused_border_color="#666666",
            label_style=ft.TextStyle(color="#888888", size=12, weight=ft.FontWeight.W_300),
            color="#DDDDDD", cursor_color="#AAAAAA",
        )
        self.port_input = ft.TextField(
            label="Порт прокси", value="8080", text_size=13, height=48,
            border_color="#333333", focused_border_color="#666666",
            label_style=ft.TextStyle(color="#888888", size=12, weight=ft.FontWeight.W_300),
            color="#DDDDDD", cursor_color="#AAAAAA",
        )
        self.split_input = ft.TextField(
            label="Размер фрагмента (Split)", value="3", text_size=13, height=48,
            border_color="#333333", focused_border_color="#666666",
            label_style=ft.TextStyle(color="#888888", size=12, weight=ft.FontWeight.W_300),
            color="#DDDDDD", cursor_color="#AAAAAA",
        )

        self.settings_dialog = ft.AlertDialog(
            bgcolor="#1E1E1E",
            shape=ft.RoundedRectangleBorder(radius=8),
            title=ft.Text("Настройки", color="#E0E0E0", size=16, weight=ft.FontWeight.W_300),
            content=ft.Column([self.ip_input, self.port_input, self.split_input], tight=True, spacing=15),
            actions=[
                ft.Container(
                    content=ft.Text("СОХРАНИТЬ", color="#90CAF9", size=13, weight=ft.FontWeight.W_500),
                    padding=10,
                    on_click=self.close_settings,
                    ink=True
                )
            ]
        )
        self.page.overlay.append(self.settings_dialog)

        self.title_text = ft.Text("BRATVADPI", size=24, weight=ft.FontWeight.W_200, color="#E0E0E0", style=ft.TextStyle(letter_spacing=3))
        self.subtitle_text = ft.Text("ROOT MOBILE", size=10, weight=ft.FontWeight.W_300, color="#757575", style=ft.TextStyle(letter_spacing=2))

        github_button = ft.Container(
            content=ft.Text("GITHUB", color="#888888", size=11, weight=ft.FontWeight.W_400, style=ft.TextStyle(letter_spacing=1)),
            padding=8,
            on_click=lambda _: webbrowser.open("https://github.com/SalvatoreBonpinsiero/BratvaDPI"),
            ink=True
        )

        settings_button = ft.Container(
            content=ft.Text("НАСТРОЙКИ", color="#888888", size=11, weight=ft.FontWeight.W_400, style=ft.TextStyle(letter_spacing=1)),
            padding=8,
            on_click=self.open_settings,
            ink=True
        )

        header = ft.Row(
            [
                ft.Column([self.title_text, self.subtitle_text], spacing=2),
                ft.Container(expand=True), 
                github_button,
                settings_button
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        )

        self.status_dot = ft.Container(width=8, height=8, border_radius=4, bgcolor="#555555")
        self.status_text = ft.Text("Служба остановлена", size=12, weight=ft.FontWeight.W_300, color="#888888")

        self.action_btn_text = ft.Text("ЗАПУСТИТЬ", size=15, weight=ft.FontWeight.W_400, color="#E0E0E0", style=ft.TextStyle(letter_spacing=1.5))
        
        self.btn_border_default = ft.Border(
            top=ft.BorderSide(1, "#3A3A3A"), right=ft.BorderSide(1, "#3A3A3A"),
            bottom=ft.BorderSide(1, "#3A3A3A"), left=ft.BorderSide(1, "#3A3A3A")
        )
        self.btn_border_active = ft.Border(
            top=ft.BorderSide(1, "#662B2B"), right=ft.BorderSide(1, "#662B2B"),
            bottom=ft.BorderSide(1, "#662B2B"), left=ft.BorderSide(1, "#662B2B")
        )

        self.action_btn = ft.Container(
            content=ft.Row([self.action_btn_text], alignment=ft.MainAxisAlignment.CENTER),
            padding=15, 
            height=54,
            bgcolor="#262626",
            border_radius=6,
            border=self.btn_border_default,
            on_click=self.toggle_service,
            ink=True
        )

        action_btn_container = ft.Container(content=self.action_btn, width=float('inf'))

        self.log_view = ft.ListView(expand=True, spacing=4, padding=10, auto_scroll=True)
        
        custom_border = ft.Border(
            top=ft.BorderSide(1, "#282828"), right=ft.BorderSide(1, "#282828"),
            bottom=ft.BorderSide(1, "#282828"), left=ft.BorderSide(1, "#282828")
        )
        
        self.log_container = ft.Container(
            content=self.log_view, expand=True, bgcolor="#111111", border=custom_border, border_radius=6, padding=5
        )

        main_layout = ft.Column(
            [
                header,
                ft.Divider(height=40, color="transparent"),
                ft.Column(
                    [
                        ft.Row([self.status_dot, self.status_text], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                        ft.Container(height=5),
                        action_btn_container,
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                ft.Divider(height=40, color="transparent"),
                ft.Row([ft.Text("Логи процесса", size=11, weight=ft.FontWeight.W_300, color="#666666")], alignment=ft.MainAxisAlignment.START),
                self.log_container
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True
        )

        safe_area = ft.SafeArea(content=ft.Container(content=main_layout, padding=20, expand=True), expand=True)
        self.page.add(safe_area)

    def open_settings(self, e):
        self.settings_dialog.open = True
        self.page.update()

    def close_settings(self, e):
        self.settings_dialog.open = False
        self.page.update()

    def log(self, message: str, color="#888888"):
        self.log_view.controls.append(
            ft.Text(message, size=11, font_family="Consolas, monospace", color=color, weight=ft.FontWeight.W_300)
        )
        self.page.update()

    def toggle_service(self, e):
        if not self.proxy or not self.proxy.is_running:
            self.start_service()
        else:
            self.stop_service()

    def start_service(self):
        ip = self.ip_input.value.strip()
        port = int(self.port_input.value.strip())
        split = self.split_input.value.strip()

        self.proxy = LocalDPIProxy(ip, port, split, self.log)
        self.proxy_thread = threading.Thread(target=self.proxy.run_in_thread, daemon=True)
        self.proxy_thread.start()

        try:
            pkg = "com.salvatorebonpinsiero.bratvadpi"
            
            uid_res = subprocess.run(["su", "-c", f"dumpsys package {pkg} | grep userId"], capture_output=True, text=True, check=False)
            uid = ""
            for line in uid_res.stdout.splitlines():
                if "userId=" in line:
                    uid = line.split("userId=")[1].strip()
                    break

            subprocess.run(["su", "-c", f"dumpsys deviceidle whitelist +{pkg}"], check=False)

            if uid:
                rule = f"iptables -t nat -A OUTPUT -p tcp -m owner ! --uid-owner {uid} -j REDIRECT --to-ports {port}"
            else:
                rule = f"iptables -t nat -A OUTPUT -p tcp -j REDIRECT --to-ports {port}"
                
            subprocess.run(["su", "-c", rule], check=True)
            
            self.log("[+] Root: Весь трафик приложений перехвачен", "#4CAF50")
            self.log("[+] Фоновый режим активирован", "#4CAF50")
        except Exception:
            self.log("[!] Ошибка: Нет Root-прав или iptables недоступен", "#CF6679")

        self.status_dot.bgcolor = "#4CAF50"
        self.status_text.value = f"Активен: {ip}:{port}"
        self.status_text.color = "#E0E0E0"
        
        self.action_btn_text.value = "ОСТАНОВИТЬ"
        self.action_btn.bgcolor = "#3A1E1E"
        self.action_btn.border = self.btn_border_active
        self.page.update()

    def stop_service(self):
        if self.proxy:
            self.proxy.stop()
            self.proxy = None

        port = int(self.port_input.value.strip())
        try:
            subprocess.run(["su", "-c", f"iptables -t nat -D OUTPUT -p tcp -j REDIRECT --to-ports {port}"], check=False)
            self.log("[-] Root: Маршрутизация сброшена", "#888888")
        except Exception:
            pass

        self.status_dot.bgcolor = "#555555"
        self.status_text.value = "Служба остановлена"
        self.status_text.color = "#888888"
        
        self.action_btn_text.value = "ЗАПУСТИТЬ"
        self.action_btn.bgcolor = "#262626"
        self.action_btn.border = self.btn_border_default
        
        self.log("[-] Движок остановлен", color="#888888")
        self.page.update()

def main(page: ft.Page):
    app = BratvaDPIApp(page)

    def on_window_event(e):
        if e.data == "close":
            if app.proxy:
                app.proxy.stop()
            page.window.destroy()

    page.window.prevent_close = True
    page.window.on_event = on_window_event

if __name__ == "__main__":
    ft.app(target=main)
