"""Intercepting proxy ala mitmproxy (HTTP + HTTPS MITM) dengan intercept interaktif,
upstream proxy (gateway), dan sistem plugin (auto-modify / unblock).

Urutan tiap request : plugin on_request  -> intercept manual -> kirim ke server
Urutan tiap response: plugin on_response -> intercept manual -> balik ke client

Jalankan versi desktop:  python app.py
Jalankan versi CLI/web:  python proxy.py
"""
import base64
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit

import config
import interceptor
import history_log
import cookie_jar as cookies
from plugins_engine import manager as plugins
from ca import generate_ca, cert_for_host

UI_PORT = 8081   # dashboard web (opsional, dipakai main())

STRIP = {"content-length", "transfer-encoding", "connection",
         "proxy-connection", "keep-alive", "te", "upgrade"}


# ------------------------------ parsing HTTP ------------------------------

def read_headers(rfile):
    headers, hd = [], {}
    while True:
        line = rfile.readline()
        if line in (b"\r\n", b"\n", b""):
            break
        k, _, v = line.rstrip(b"\r\n").partition(b": ")
        k = k.decode("latin1")
        v = v.decode("latin1")
        headers.append((k, v))
        hd[k.lower()] = v
    return headers, hd


def read_body(rfile, hd, is_response=False, method="GET", status=200):
    if method == "HEAD" or status in (204, 304) or (is_response and 100 <= status < 200):
        return b""
    if "content-length" in hd:
        try:
            n = int(hd["content-length"])
        except ValueError:
            return b""
        return rfile.read(n) if n > 0 else b""
    if "chunked" in hd.get("transfer-encoding", "").lower():
        out = bytearray()
        while True:
            size_line = rfile.readline()
            if not size_line:
                break
            try:
                size = int(size_line.strip().split(b";")[0] or b"0", 16)
            except ValueError:
                break
            if size == 0:
                rfile.readline()
                break
            out += rfile.read(size)
            rfile.read(2)
        return bytes(out)
    if is_response:
        return rfile.read()
    return b""


def _norm(headers, body, connection):
    out = [(k, v) for k, v in headers if k.lower() not in STRIP]
    out.append(("Content-Length", str(len(body))))
    out.append(("Connection", connection))
    return out


def build_request(method, target, headers, body):
    """target = origin-form ('/path') untuk koneksi langsung,
    atau absolute-form ('http://host/path') kalau lewat upstream proxy."""
    h = _norm(headers, body, "close")
    head = "\r\n".join([f"{method} {target} HTTP/1.1"] + [f"{k}: {v}" for k, v in h])
    return (head + "\r\n\r\n").encode("latin1") + body


def build_response(status_line, headers, body):
    h = _norm(headers, body, "keep-alive")
    head = "\r\n".join([status_line] + [f"{k}: {v}" for k, v in h])
    return (head + "\r\n\r\n").encode("latin1") + body


def send_once(method, scheme, host, port, path, headers, body, timeout=30):
    """Kirim satu request ke server (langsung / via upstream) lalu kembalikan
    (status_line, headers_list, body_bytes). Dipakai oleh fitur Repeater."""
    port = int(port)
    up_sock, form = _dial(host, port, scheme)
    try:
        if form == "absolute":
            default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
            uri = f"{scheme}://{host}{path}" if default_port else f"{scheme}://{host}:{port}{path}"
            auth = _proxy_auth_header()
            send_headers = list(headers) + ([auth] if auth else [])
            up_sock.sendall(build_request(method, uri, send_headers, body))
        else:
            up_sock.sendall(build_request(method, path, headers, body))
        upf = up_sock.makefile("rb")
        status_line = upf.readline().decode("latin1").rstrip("\r\n")
        rheaders, rhd = read_headers(upf)
        try:
            status = int(status_line.split(" ")[1])
        except (IndexError, ValueError):
            status = 200
        rbody = read_body(upf, rhd, is_response=True, method=method, status=status)
        return status_line, rheaders, rbody
    finally:
        try:
            up_sock.close()
        except OSError:
            pass


# ------------------------------ upstream / gateway ------------------------------

def _proxy_auth_header():
    up = config.get().get("upstream") or {}
    user = up.get("user") or ""
    if not user:
        return None
    token = base64.b64encode(f'{user}:{up.get("password", "")}'.encode()).decode()
    return ("Proxy-Authorization", f"Basic {token}")


def _dial(host, port, scheme):
    """Buka koneksi ke tujuan. Kalau upstream proxy aktif, lewat proxy itu.
    Return (socket, form) di mana form 'origin' atau 'absolute'."""
    up = config.get().get("upstream") or {}
    if up.get("enabled") and up.get("host"):
        s = socket.create_connection((up["host"], int(up.get("port") or 8080)), timeout=30)
        if scheme == "https":
            line = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            hdr = _proxy_auth_header()
            if hdr:
                line += f"{hdr[0]}: {hdr[1]}\r\n"
            line += "\r\n"
            s.sendall(line.encode("latin1"))
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
            status = resp.split(b"\r\n", 1)[0]
            if b" 200" not in status:
                s.close()
                raise OSError(f"CONNECT ke upstream ditolak: {status!r}")
            s = ssl.create_default_context().wrap_socket(s, server_hostname=host)
            return s, "origin"
        return s, "absolute"

    s = socket.create_connection((host, port), timeout=30)
    if scheme == "https":
        s = ssl.create_default_context().wrap_socket(s, server_hostname=host)
    return s, "origin"


# ------------------------------ inti proxy ------------------------------

def _drop_client(sock, code, reason):
    try:
        sock.sendall(f"HTTP/1.1 {code} {reason}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
    except OSError:
        pass


def _parse_sni(data):
    """Ambil nama host (SNI) dari TLS ClientHello. None kalau gagal."""
    try:
        if len(data) < 5 or data[0] != 0x16:
            return None
        idx = 5
        if data[idx] != 0x01:        # harus ClientHello
            return None
        idx += 4                      # lewati handshake type+len
        idx += 2 + 32                 # client version + random
        sid_len = data[idx]; idx += 1 + sid_len
        cs_len = int.from_bytes(data[idx:idx + 2], "big"); idx += 2 + cs_len
        comp_len = data[idx]; idx += 1 + comp_len
        ext_total = int.from_bytes(data[idx:idx + 2], "big"); idx += 2
        end = idx + ext_total
        while idx + 4 <= end:
            etype = int.from_bytes(data[idx:idx + 2], "big")
            elen = int.from_bytes(data[idx + 2:idx + 4], "big")
            idx += 4
            if etype == 0x0000:       # server_name
                p = idx + 2 + 1       # list length + name type
                nlen = int.from_bytes(data[p:p + 2], "big"); p += 2
                return data[p:p + nlen].decode("latin1")
            idx += elen
    except Exception:
        return None
    return None


def handle_conn(sock):
    """Entry tiap koneksi. Kalau invisible proxy aktif & klien langsung TLS
    (tanpa CONNECT), deteksi SNI lalu MITM. Selain itu lanjut sebagai HTTP biasa."""
    if config.get().get("invisible"):
        try:
            peek = sock.recv(4096, socket.MSG_PEEK)
        except OSError:
            peek = b""
        if peek[:1] == b"\x16":       # TLS handshake langsung
            sni = _parse_sni(peek) or ""
            if sni:
                crt, key = cert_for_host(sni)
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(crt, key)
                try:
                    tls = ctx.wrap_socket(sock, server_side=True)
                except ssl.SSLError:
                    return
                serve(tls, tls_host=sni, tls_port=443)
                return
    serve(sock)


def serve(sock, tls_host=None, tls_port=None):
    rfile = sock.makefile("rb")
    while True:
        first = rfile.readline()
        if not first:
            break
        try:
            method, target, _ = first.decode("latin1").split()
        except ValueError:
            break

        # --- HTTPS: terowongan ke client, lalu MITM ---
        if method == "CONNECT":
            read_headers(rfile)
            host, _, port = target.partition(":")
            port = int(port or 443)
            sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            crt, key = cert_for_host(host)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(crt, key)
            try:
                tls = ctx.wrap_socket(sock, server_side=True)
            except ssl.SSLError:
                return
            serve(tls, tls_host=host, tls_port=port)
            return

        headers, hd = read_headers(rfile)
        if tls_host:
            scheme, host, port, path = "https", tls_host, tls_port, target
        elif target.startswith("/"):
            # origin-form (invisible/transparent proxy: klien tidak di-set proxy)
            hostv = hd.get("host", "")
            h, _, p = hostv.partition(":")
            scheme, host, port, path = "http", h, int(p or 80), target
        else:
            u = urlsplit(target)
            scheme, host, port = "http", u.hostname, (u.port or 80)
            path = (u.path or "/") + (("?" + u.query) if u.query else "")
        body = read_body(rfile, hd, method=method)

        # ====== PLUGIN on_request (otomatis) ======
        fields = {"method": method, "scheme": scheme, "host": host, "port": port, "path": path}
        res = plugins.apply_request(fields, headers, body)
        if res is None:
            _drop_client(sock, 444, "Blocked by plugin")
            break
        fields, headers, body = res

        # ====== INTERCEPT REQUEST (manual) ======
        res = interceptor.intercept_request(fields, headers, body)
        if res is None:
            _drop_client(sock, 444, "Dropped")
            break
        fields, headers, body = res
        method, scheme = fields["method"], fields["scheme"]
        host, port, path = fields["host"], int(fields["port"]), fields["path"]
        req_info = {"method": method, "scheme": scheme, "host": host, "port": port, "path": path}

        # ====== Cookie jar (session): sisipkan cookie tersimpan ======
        if config.get().get("cookie_jar"):
            headers = cookies.apply(host, headers)

        # ====== teruskan (langsung / via upstream) ======
        try:
            up_sock, form = _dial(host, port, scheme)
        except OSError:
            _drop_client(sock, 502, "Bad Gateway")
            break

        if form == "absolute":
            default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
            uri = f"{scheme}://{host}{path}" if default_port else f"{scheme}://{host}:{port}{path}"
            auth = _proxy_auth_header()
            send_headers = headers + ([auth] if auth else [])
            up_sock.sendall(build_request(method, uri, send_headers, body))
        else:
            up_sock.sendall(build_request(method, path, headers, body))

        upf = up_sock.makefile("rb")
        status_line = upf.readline().decode("latin1").rstrip("\r\n")
        if not status_line:
            up_sock.close()
            break
        rheaders, rhd = read_headers(upf)
        if config.get().get("cookie_jar"):
            cookies.capture(host, rheaders)
        try:
            status = int(status_line.split(" ")[1])
        except (IndexError, ValueError):
            status = 200
        rbody = read_body(upf, rhd, is_response=True, method=method, status=status)
        up_sock.close()

        # ====== PLUGIN on_response (otomatis) ======
        fields = {"status_line": status_line}
        res = plugins.apply_response(fields, rheaders, rbody, req_info)
        if res is None:
            break
        fields, rheaders, rbody = res

        # ====== INTERCEPT RESPONSE (manual) ======
        req_view = {
            "line": f"{method} {scheme}://{host}{path}",
            "headers": [list(h) for h in headers],
            "body_text": interceptor._decode(headers, body)[0],
        }
        res = interceptor.intercept_response(fields, rheaders, rbody, request=req_view)
        if res is None:
            break
        fields, rheaders, rbody = res

        # ====== CATAT ke HTTP History (selalu, walau intercept off) ======
        try:
            history_log.record(
                {"method": method, "scheme": scheme, "host": host, "port": port,
                 "path": path, "headers": headers, "body": body},
                {"status_line": fields["status_line"], "headers": rheaders, "body": rbody})
        except Exception:
            pass

        sock.sendall(build_response(fields["status_line"], rheaders, rbody))

    try:
        sock.close()
    except OSError:
        pass


def _safe(conn):
    try:
        handle_conn(conn)
    except (ConnectionError, ssl.SSLError, OSError, BrokenPipeError):
        pass
    except Exception as e:  # noqa
        print("err:", e)


# ------------------------------ server (bisa restart) ------------------------------

class ProxyServer:
    def __init__(self):
        self._srv = None
        self._thread = None
        self._running = False
        self.host = None
        self.port = None

    def start(self, host, port):
        self.stop()
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, int(port)))
        srv.listen(200)
        self._srv = srv
        self._running = True
        self.host, self.port = host, int(port)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[proxy] listen {host}:{port}")

    def _loop(self):
        while self._running:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                break
            threading.Thread(target=_safe, args=(conn,), daemon=True).start()

    def stop(self):
        self._running = False
        if self._srv:
            try:
                self._srv.close()
            except OSError:
                pass
            self._srv = None


def serve_forever():
    cfg = config.get()
    server = ProxyServer()
    server.start(cfg["listen_host"], cfg["listen_port"])
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[proxy] stop")
        server.stop()


def main():
    generate_ca()
    plugins.load_all()
    try:
        import dashboard
        threading.Thread(target=dashboard.run,
                         kwargs={"host": config.get()["listen_host"], "port": UI_PORT},
                         daemon=True).start()
        print(f"[ui]    dashboard: http://127.0.0.1:{UI_PORT}")
    except ImportError:
        interceptor.enabled["request"] = interceptor.enabled["response"] = False
        print("[ui]    Flask belum ada (pip install flask) -> passthrough tanpa UI")
    serve_forever()


if __name__ == "__main__":
    main()
