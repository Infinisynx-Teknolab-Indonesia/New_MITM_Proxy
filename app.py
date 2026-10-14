"""Aplikasi desktop (Tkinter) — Mini MITM Proxy.

Tampilan gaya aplikasi Windows: menu bar, toolbar, status bar, tema native.
Menu Settings bertab: Proxy, Certificate (regenerate/export), Plugins (import/install).

Jalankan:
  pip install cryptography
  python app.py
"""
import os
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

import json
import config
import interceptor
import history_log
import jwt_tool
import cookie_jar as cookies
import ai_explain
import browser_launch
import i18n
from i18n import t
import proxy
from urllib.parse import urlsplit
import ca as ca_mod
from plugins_engine import manager as plugins, PLUGINS_DIR

ACCENT = "#0067c0"        # biru khas Windows
ACCENT_DK = "#005ba1"
OK_GREEN = "#107c10"
STOP_RED = "#c42b1c"


class App:
    def __init__(self, root, server):
        self.root = root
        self.server = server
        self.pending_by_id = {}
        self.order = []
        self.current_id = None
        self.current_kind = None
        self.current_editable = True
        self.entries = {}

        root.title("Mini MITM Proxy")
        root.geometry("1120x760")
        root.minsize(900, 560)
        self._setup_style()
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self._refresh_status()
        self._poll()

    # ------------------------------ style ------------------------------

    def _setup_style(self):
        style = ttk.Style()
        for theme in ("vista", "winnative", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        default = ("Segoe UI", 10)
        self.root.option_add("*Font", default)
        self.mono = ("Consolas", 10)
        style.configure("Accent.TButton", foreground="white", background=ACCENT)
        style.map("Accent.TButton", background=[("active", ACCENT_DK), ("pressed", ACCENT_DK)])
        style.configure("Toolbar.TFrame", background="#f3f3f3")
        style.configure("Card.TLabelframe", padding=10)
        style.configure("Status.TLabel", padding=(8, 3))

    # ------------------------------ menu bar ------------------------------

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Pengaturan…", accelerator="Ctrl+,", command=lambda: self._open_settings(0))
        m_file.add_separator()
        m_file.add_command(label="Keluar", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=m_file)

        m_proxy = tk.Menu(menubar, tearoff=0)
        m_proxy.add_command(label="Start", command=self.start_proxy)
        m_proxy.add_command(label="Stop", command=self.stop_proxy)
        m_proxy.add_separator()
        m_proxy.add_command(label="Pengaturan Proxy…", command=lambda: self._open_settings(0))
        menubar.add_cascade(label="Proxy", menu=m_proxy)

        m_tools = tk.Menu(menubar, tearoff=0)
        m_tools.add_command(label="Regenerate Certificate…", command=self._regenerate_cert)
        m_tools.add_command(label="Export CA (ca.crt)…", command=self._export_ca)
        m_tools.add_separator()
        m_tools.add_command(label="Kelola Plugin…", command=lambda: self._open_settings(2))
        m_tools.add_command(label="Buka Folder Plugin", command=self._open_plugins_folder)
        m_tools.add_separator()
        m_tools.add_command(label="Bersihkan HTTP History", command=self._clear_history)
        m_tools.add_command(label="Kosongkan Cookie Jar",
                            command=lambda: (cookies.clear(), messagebox.showinfo("Cookie", "Cookie jar dikosongkan.")))
        menubar.add_cascade(label="Tools", menu=m_tools)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="Tentang", command=self._about)
        menubar.add_cascade(label="Help", menu=m_help)

        self.root.config(menu=menubar)
        self.root.bind("<Control-comma>", lambda e: self._open_settings(0))

    # ------------------------------ toolbar ------------------------------

    def _build_toolbar(self):
        tb = ttk.Frame(self.root, style="Toolbar.TFrame", padding=6)
        tb.pack(fill="x")

        self.btn_start = ttk.Button(tb, text="▶ Start", style="Accent.TButton", command=self.start_proxy)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(tb, text="■ Stop", command=self.stop_proxy)
        self.btn_stop.pack(side="left", padx=(6, 14))

        # Satu tombol Intercept ON/OFF (ala Burp). Default OFF.
        ttk.Button(tb, text="☰", width=3, command=self._toggle_sidebar).pack(side="left", padx=(0, 8))
        self.btn_intercept = ttk.Button(tb, text=t("intercept_off"), command=self._toggle_intercept)
        self.btn_intercept.pack(side="left")
        self.var_res = tk.IntVar(value=0)
        ttk.Checkbutton(tb, text=t("hold_response"), variable=self.var_res,
                        command=self._toggle_response).pack(side="left", padx=(10, 14))
        ttk.Button(tb, text=t("forward_all"), command=interceptor.resolve_all).pack(side="left")
        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(tb, text=t("browser"), command=self._open_browser_manager).pack(side="left")
        ttk.Button(tb, text=t("settings"), command=lambda: self._open_settings(0)).pack(side="left", padx=(6, 0))

        self.badge = tk.Label(tb, text=t("stopped"), fg="white", bg=STOP_RED, padx=10, pady=2)
        self.badge.pack(side="right")

    # ------------------------------ body ------------------------------

    def _build_body(self):
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True, padx=10, pady=8)

        # --- sidebar kiri: klien (Windows/Android/iOS -> browser/app) ---
        self.sidebar = ttk.Frame(outer, width=240)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        sbar = ttk.Frame(self.sidebar); sbar.pack(fill="x")
        ttk.Label(sbar, text=t("clients"), font=("Segoe UI", 10, "bold")).pack(side="left", pady=(0, 4))
        ttk.Button(sbar, text=t("all"), width=7, command=self._client_filter_clear).pack(side="right")
        self.sb_tree = ttk.Treeview(self.sidebar, show="tree", selectmode="browse")
        self.sb_tree.pack(fill="both", expand=True)
        self.sb_tree.bind("<<TreeviewSelect>>", self._on_client_select)
        self._sb_nodes = {}
        self._sb_sig = None
        self.client_filter = None

        self.nb = ttk.Notebook(outer)
        self.nb.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self._build_intercept_tab()
        self._build_history_tab()
        self._build_repeater_tab()
        self._build_intruder_tab()
        self._build_jwt_tab()
        self._build_airunner_tab()
        self._build_plugins_tab()

    # --- Tab 1: Intercept ---
    def _build_intercept_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text=t("tab_intercept"))
        main = ttk.PanedWindow(tab, orient="horizontal")
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        lf = ttk.Labelframe(left, text="Ditahan", style="Card.TLabelframe")
        lf.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(lf, activestyle="none", borderwidth=0, highlightthickness=0)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Button-3>", self._popup_intercept)
        self.ictx = tk.Menu(self.root, tearoff=0)
        self.ictx.add_command(label="Kirim ke Repeater", command=self._intercept_to_repeater)
        self.ictx.add_command(label="Kirim ke Intruder", command=self._intercept_to_intruder)
        self.ictx.add_command(label="Kirim ke JWT", command=self._intercept_to_jwt)
        main.add(left, weight=1)

        right = ttk.Frame(main)
        main.add(right, weight=3)

        # panel "Request asal" (muncul hanya saat mengedit sebuah RESPONSE)
        self.req_preview_frame = ttk.Labelframe(right, text="Request asal (read-only)",
                                                style="Card.TLabelframe")
        self.req_preview = scrolledtext.ScrolledText(self.req_preview_frame, height=7,
                                                     wrap="none", font=self.mono, state="disabled")
        self.req_preview.pack(fill="both", expand=True)
        self._attach_find(self.req_preview_frame, self.req_preview)

        # grup editor (judulnya berubah: REQUEST / RESPONSE) biar tidak bingung
        self.editor_box = ttk.Labelframe(right, text="Belum ada yang dipilih", style="Card.TLabelframe")
        self.editor_box.pack(fill="both", expand=True)
        self.fields_frame = ttk.Frame(self.editor_box)
        self.fields_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(self.editor_box, text="Headers (satu per baris: Key: Value)").pack(anchor="w")
        self.headers_text = scrolledtext.ScrolledText(self.editor_box, height=8, wrap="none", font=self.mono)
        self.headers_text.pack(fill="both")
        self.body_label = ttk.Label(self.editor_box, text="Body")
        self.body_label.pack(anchor="w", pady=(6, 0))
        self.body_text = scrolledtext.ScrolledText(self.editor_box, height=14, wrap="none", font=self.mono)
        self.body_text.pack(fill="both", expand=True)

        # klik-kanan di editor -> kirim ke Repeater / JWT
        self.ectx = tk.Menu(self.root, tearoff=0)
        self.ectx.add_command(label="Kirim ke Repeater", command=self._editor_to_repeater)
        self.ectx.add_command(label="Kirim ke Intruder", command=self._editor_to_intruder)
        self.ectx.add_command(label="Kirim ke JWT", command=self._editor_to_jwt)
        self.ectx.add_command(label="Jelaskan dengan AI", command=self._editor_explain_ai)
        for w in (self.headers_text, self.body_text, self.req_preview):
            w.bind("<Button-3>", lambda e: self.ectx.tk_popup(e.x_root, e.y_root))

        btns = ttk.Frame(right)
        btns.pack(fill="x", pady=6)
        self.fwd_btn = ttk.Button(btns, text="Forward", style="Accent.TButton",
                                  command=self._forward, state="disabled")
        self.fwd_btn.pack(side="left")
        self.drop_btn = ttk.Button(btns, text="Drop", command=self._drop, state="disabled")
        self.drop_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="\U0001F916 Jelaskan dgn AI", command=self._editor_explain_ai).pack(side="left")
        self.hint = ttk.Label(btns, text="Pilih flow di kiri untuk mengedit", foreground="#666")
        self.hint.pack(side="left", padx=12)

    # --- Tab 2: HTTP History (ala Burp) ---
    def _build_history_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text=t("tab_history"))

        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Kirim ke Repeater", command=self._send_to_repeater).pack(side="left")
        ttk.Button(bar, text="Kirim ke Intruder", command=self._send_to_intruder).pack(side="left", padx=6)
        ttk.Button(bar, text="Kirim ke JWT", command=self._send_to_jwt).pack(side="left")
        ttk.Button(bar, text="\U0001F916 Jelaskan dgn AI", command=self._explain_ai).pack(side="left", padx=6)
        ttk.Button(bar, text="Clear", command=self._clear_history).pack(side="right")

        pane = ttk.PanedWindow(tab, orient="vertical")
        pane.pack(fill="both", expand=True)

        topf = ttk.Frame(pane)
        cols = ("id", "method", "host", "path", "status", "len")
        self.htable = ttk.Treeview(topf, columns=cols, show="headings", height=10)
        for c, txt, w, anchor in (("id", "#", 50, "e"), ("method", "Method", 70, "w"),
                                  ("host", "Host", 200, "w"), ("path", "Path", 360, "w"),
                                  ("status", "Status", 70, "center"), ("len", "Length", 80, "e")):
            self.htable.heading(c, text=txt)
            self.htable.column(c, width=w, anchor=anchor)
        vs = ttk.Scrollbar(topf, orient="vertical", command=self.htable.yview)
        self.htable.configure(yscrollcommand=vs.set)
        self.htable.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.htable.bind("<<TreeviewSelect>>", self._on_history_select)
        self.htable.bind("<Button-3>", self._popup_history)
        self.hctx = tk.Menu(self.root, tearoff=0)
        self.hctx.add_command(label="Kirim ke Repeater", command=self._send_to_repeater)
        self.hctx.add_command(label="Kirim ke Intruder", command=self._send_to_intruder)
        self.hctx.add_command(label="Kirim ke JWT", command=self._send_to_jwt)
        self.hctx.add_command(label="Jelaskan dengan AI", command=self._explain_ai)
        pane.add(topf, weight=2)

        botf = ttk.Frame(pane)
        split = ttk.PanedWindow(botf, orient="horizontal")
        split.pack(fill="both", expand=True)
        reqf = ttk.Labelframe(split, text="Request", style="Card.TLabelframe")
        self.h_req = scrolledtext.ScrolledText(reqf, wrap="none", font=self.mono, state="disabled")
        self.h_req.pack(fill="both", expand=True)
        self._attach_find(reqf, self.h_req)
        split.add(reqf, weight=1)
        resf = ttk.Labelframe(split, text="Response", style="Card.TLabelframe")
        self.h_res = scrolledtext.ScrolledText(resf, wrap="none", font=self.mono, state="disabled")
        self.h_res.pack(fill="both", expand=True)
        self._attach_find(resf, self.h_res)
        split.add(resf, weight=1)
        pane.add(botf, weight=3)

        self.hist_seen = set()
        self.hist_selected = None

    def _clear_history(self):
        history_log.clear()
        self.htable.delete(*self.htable.get_children())
        self.hist_seen.clear()
        for w in (self.h_req, self.h_res):
            w.config(state="normal")
            w.delete("1.0", "end")
            w.config(state="disabled")

    def _on_history_select(self, _evt):
        sel = self.htable.selection()
        if not sel:
            return
        try:
            eid = int(sel[0])
        except ValueError:
            return
        self.hist_selected = eid
        e = history_log.get(eid)
        if not e:
            return
        req = f'{e["method"]} {e["url"]}\n'
        req += "\n".join(f"{k}: {v}" for k, v in e["req_headers"])
        if e["req_text"]:
            req += "\n\n" + e["req_text"]
        res = e["status_line"] + "\n"
        res += "\n".join(f"{k}: {v}" for k, v in e["res_headers"])
        if e["res_text"]:
            res += "\n\n" + e["res_text"]
        for w, txt in ((self.h_req, req), (self.h_res, res)):
            w.config(state="normal")
            w.delete("1.0", "end")
            w.insert("1.0", txt)
            w.config(state="disabled")

    # --- sidebar klien ---
    def _toggle_sidebar(self):
        if self.sidebar.winfo_ismapped():
            self.sidebar.pack_forget()
        else:
            self.sidebar.pack(side="left", fill="y", before=self.nb)

    def _refresh_sidebar(self):
        tree = history_log.aggregate()
        sig = tuple(sorted((p, tuple(sorted(d.items()))) for p, d in tree.items()))
        if sig == self._sb_sig:
            return   # tidak berubah, jangan rebuild (hindari flicker)
        self._sb_sig = sig
        sel = self.client_filter
        self.sb_tree.delete(*self.sb_tree.get_children())
        self._sb_nodes = {}
        for plat in sorted(tree):
            node = tree[plat]
            pid = self.sb_tree.insert("", "end", text=f"{plat}  ({node['_count']})", open=True)
            self._sb_nodes[pid] = (plat, None)
            for brow in sorted(k for k in node if k != "_count"):
                bid = self.sb_tree.insert(pid, "end", text=f"{brow}  ({node[brow]})")
                self._sb_nodes[bid] = (plat, brow)
                if sel == (plat, brow):
                    self.sb_tree.selection_set(bid)
            if sel == (plat, None):
                self.sb_tree.selection_set(pid)

    def _on_client_select(self, _evt):
        sel = self.sb_tree.selection()
        if not sel:
            return
        self.client_filter = self._sb_nodes.get(sel[0])
        self._apply_client_filter()

    def _client_filter_clear(self):
        self.client_filter = None
        for i in self.sb_tree.selection():
            self.sb_tree.selection_remove(i)
        self._apply_client_filter()

    def _client_match(self, r):
        if not self.client_filter:
            return True
        plat, brow = self.client_filter
        return r.get("platform") == plat and (brow is None or r.get("browser") == brow)

    def _apply_client_filter(self):
        self.htable.delete(*self.htable.get_children())
        self.hist_seen = set()
        self._update_history()

    def _update_history(self):
        rows = history_log.snapshot()
        new = [r for r in rows if r["id"] not in self.hist_seen]
        for r in sorted(new, key=lambda x: x["id"]):   # lama->baru, sisip di atas
            self.hist_seen.add(r["id"])
            if not self._client_match(r):
                continue
            status = r["status"] or ""
            self.htable.insert("", 0, iid=str(r["id"]),
                               values=(r["id"], r["method"], r["host"], r["path"][:120],
                                       status, r["res_len"]))
        self._refresh_sidebar()

    def _build_statusbar(self):
        sb = ttk.Frame(self.root, relief="groove")
        sb.pack(fill="x", side="bottom")
        self.st_proxy = ttk.Label(sb, text="", style="Status.TLabel")
        self.st_proxy.pack(side="left")
        ttk.Separator(sb, orient="vertical").pack(side="left", fill="y")
        self.st_up = ttk.Label(sb, text="", style="Status.TLabel")
        self.st_up.pack(side="left")
        ttk.Separator(sb, orient="vertical").pack(side="left", fill="y")
        self.st_plug = ttk.Label(sb, text="", style="Status.TLabel")
        self.st_plug.pack(side="left")
        self.st_count = ttk.Label(sb, text="0 " + t("held"), style="Status.TLabel")
        self.st_count.pack(side="right")

    def _refresh_status(self):
        if not hasattr(self, "st_proxy"):
            return   # status bar belum dibuat (dipanggil saat init awal)
        cfg = config.get()
        up = cfg["upstream"]
        running = self.server.host is not None
        if running:
            self.badge.config(text=t("running"), bg=OK_GREEN)
            self.st_proxy.config(text=f"{t('proxy')}: {self.server.host}:{self.server.port}")
        else:
            self.badge.config(text=t("stopped"), bg=STOP_RED)
            self.st_proxy.config(text=f"{t('proxy')}: {cfg['listen_host']}:{cfg['listen_port']}")
        self.st_up.config(text=t("upstream") + ": " + (f"{up['host']}:{up['port']}" if up["enabled"] and up["host"] else t("direct")))
        active = sum(1 for p in plugins.plugins if plugins.is_enabled(p.name))
        self.st_plug.config(text=f"{t('plugins_active')}: {active}/{len(plugins.plugins)}")

    # ------------------------------ proxy control ------------------------------

    def start_proxy(self):
        cfg = config.get()
        try:
            self.server.start(cfg["listen_host"], cfg["listen_port"])
        except OSError as e:
            messagebox.showerror("Gagal start", f"Tidak bisa bind {cfg['listen_host']}:{cfg['listen_port']}\n{e}")
        self._refresh_status()

    def stop_proxy(self):
        self.server.stop()
        self.server.host = self.server.port = None
        self._refresh_status()

    # ------------------------------ certificate ------------------------------

    def _regenerate_cert(self):
        if not messagebox.askyesno(
                "Regenerate Certificate",
                "Buat ulang CA baru?\n\nCA lama yang sudah diinstal di device TIDAK akan "
                "berlaku lagi — kamu harus menginstal ulang ca.crt yang baru."):
            return
        try:
            path = ca_mod.regenerate_ca()
        except Exception as e:
            messagebox.showerror("Gagal", str(e))
            return
        messagebox.showinfo("Selesai", f"CA baru dibuat:\n{path}\n\nInstal ulang file ini di device kamu.")
        self._refresh_status()

    def _export_ca(self):
        try:
            ca_mod.generate_ca()
        except Exception as e:
            messagebox.showerror("Gagal", str(e))
            return
        dst = filedialog.asksaveasfilename(
            title="Simpan CA", defaultextension=".crt",
            initialfile="ca.crt", filetypes=[("Certificate", "*.crt"), ("All", "*.*")])
        if not dst:
            return
        try:
            with open(ca_mod.CA_CERT, "rb") as f:
                data = f.read()
            with open(dst, "wb") as f:
                f.write(data)
            messagebox.showinfo("Selesai", f"CA disimpan ke:\n{dst}")
        except Exception as e:
            messagebox.showerror("Gagal", str(e))

    def _open_plugins_folder(self):
        os.makedirs(PLUGINS_DIR, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(PLUGINS_DIR)  # noqa
            else:
                import subprocess
                opener = "open" if sys_is_mac() else "xdg-open"
                subprocess.Popen([opener, PLUGINS_DIR])
        except Exception:
            messagebox.showinfo("Folder Plugin", PLUGINS_DIR)

    def _about(self):
        messagebox.showinfo(
            "Tentang",
            "Mini MITM Proxy\n\nIntercept & edit HTTP/HTTPS, upstream gateway, dan plugin.\n"
            "Pakai hanya untuk device & trafik milikmu sendiri.")

    # ------------------------------ Browser manager ------------------------------

    def _open_browser_manager(self):
        browsers = browser_launch.find_browsers()
        win = tk.Toplevel(self.root)
        win.title("Browser (lewat proxy)")
        win.geometry("520x420")
        win.transient(self.root)
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)

        if not browsers:
            ttk.Label(frm, wraplength=480, foreground=STOP_RED, text=(
                "Tidak menemukan Chrome/Edge/Brave. Install salah satunya, atau buka browser "
                "manual lalu set proxy ke 127.0.0.1:8080.")).pack(anchor="w")
            return

        top = ttk.Frame(frm); top.pack(fill="x")
        ttk.Label(top, text="Browser:").pack(side="left")
        names = list(browsers.keys())
        pick = ttk.Combobox(top, width=14, values=names, state="readonly")
        pick.set(names[0])
        pick.pack(side="left", padx=6)

        def open_new():
            if not hasattr(self, "_browser_n"):
                self._browser_n = 0
            self._browser_n += 1
            host = self.server.host or "127.0.0.1"
            port = self.server.port or config.get()["listen_port"]
            try:
                browser_launch.launch(browsers[pick.get()], host, port,
                                      f"{pick.get()} #{self._browser_n}")
            except Exception as ex:
                messagebox.showerror("Gagal buka browser", str(ex), parent=win)
            refresh()

        ttk.Button(top, text="Buka Sesi Baru", style="Accent.TButton", command=open_new).pack(side="left", padx=6)

        ttk.Label(frm, foreground="#666", wraplength=480, pady=6, text=(
            "Tiap 'Buka Sesi Baru' = jendela dengan session sendiri (login terpisah), "
            "lewat proxy & abaikan error sertifikat. Trafiknya muncul di HTTP History.")).pack(anchor="w")

        ttk.Label(frm, text="Sesi aktif:").pack(anchor="w")
        lb = tk.Listbox(frm, height=10)
        lb.pack(fill="both", expand=True, pady=(2, 6))

        sess_ref = []

        def refresh():
            lb.delete(0, "end")
            sess_ref[:] = browser_launch.sessions()
            for s in sess_ref:
                lb.insert("end", s["name"])

        def close_sel():
            sel = lb.curselection()
            if not sel:
                return
            browser_launch.close(sess_ref[sel[0]])
            refresh()

        ttk.Button(frm, text="Tutup Sesi Terpilih", command=close_sel).pack(anchor="w")
        refresh()

    # ------------------------------ SETTINGS (notebook) ------------------------------

    def _open_settings(self, tab=0):
        win = tk.Toplevel(self.root)
        win.title("Pengaturan")
        win.transient(self.root)
        win.grab_set()
        win.geometry("640x520")
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self._tab_proxy(nb)
        self._tab_cert(nb)
        self._tab_plugins(nb)
        self._tab_ai(nb)
        nb.select(tab)

        bar = ttk.Frame(win, padding=(10, 0, 10, 10))
        bar.pack(fill="x")
        ttk.Button(bar, text="Tutup", command=win.destroy).pack(side="right")

    # --- tab 1: proxy ---
    def _tab_proxy(self, nb):
        cfg = config.get()
        up = cfg["upstream"]
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text="  Proxy  ")

        g1 = ttk.Labelframe(f, text="Listen (alamat proxy)", padding=12)
        g1.pack(fill="x")
        ttk.Label(g1, text="Host").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
        e_host = ttk.Entry(g1, width=28)
        e_host.insert(0, cfg["listen_host"])
        e_host.grid(row=0, column=1, sticky="w")
        ttk.Label(g1, text="Port").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))
        e_port = ttk.Entry(g1, width=28)
        e_port.insert(0, str(cfg["listen_port"]))
        e_port.grid(row=1, column=1, sticky="w")

        g2 = ttk.Labelframe(f, text="Upstream gateway (teruskan ke proxy lain)", padding=12)
        g2.pack(fill="x", pady=(14, 0))
        up_var = tk.IntVar(value=1 if up["enabled"] else 0)
        ttk.Checkbutton(g2, text="Aktifkan upstream", variable=up_var).grid(row=0, column=0, columnspan=2, sticky="w")
        rows = [("Host", "host", ""), ("Port", "port", ""), ("User (opsional)", "user", ""),
                ("Password (opsional)", "password", "*")]
        ent = {}
        for i, (lbl, key, show) in enumerate(rows, start=1):
            ttk.Label(g2, text=lbl).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 10))
            e = ttk.Entry(g2, width=28, show=show or "")
            e.insert(0, str(up[key]))
            e.grid(row=i, column=1, sticky="w")
            ent[key] = e

        g3 = ttk.Labelframe(f, text="Lainnya", padding=12)
        g3.pack(fill="x", pady=(14, 0))
        inv_var = tk.IntVar(value=1 if cfg.get("invisible") else 0)
        ttk.Checkbutton(g3, text="Invisible proxy (transparent — klien tanpa setting proxy)",
                        variable=inv_var).pack(anchor="w")
        cj_var = tk.IntVar(value=1 if cfg.get("cookie_jar") else 0)
        ttk.Checkbutton(g3, text="Cookie jar / session (simpan cookie dari response & ikutkan ke request)",
                        variable=cj_var).pack(anchor="w")
        cjrow = ttk.Frame(g3)
        cjrow.pack(anchor="w", pady=(4, 0))
        ttk.Button(cjrow, text="Kosongkan Cookie Jar",
                   command=lambda: (cookies.clear(), messagebox.showinfo("Cookie", "Cookie jar dikosongkan.", parent=f))).pack(side="left")

        lrow = ttk.Frame(g3); lrow.pack(anchor="w", pady=(8, 2))
        ttk.Label(lrow, text=t("language") + ":").pack(side="left")
        lang_cb = ttk.Combobox(lrow, width=14, values=[nm for _c, nm in i18n.LANGS], state="readonly")
        lang_cb.set(dict(i18n.LANGS).get(cfg.get("lang", "id"), "Indonesia"))
        lang_cb.pack(side="left", padx=6)

        def apply_proxy():
            code = next((c for c, nm in i18n.LANGS if nm == lang_cb.get()), "id")
            config.update({"lang": code})
            try:
                lport = int(e_port.get())
                uport = int(ent["port"].get() or 0)
            except ValueError:
                messagebox.showerror("Input salah", "Port harus angka.", parent=f)
                return
            lhost = e_host.get().strip() or "127.0.0.1"
            config.update({
                "listen_host": lhost, "listen_port": lport,
                "invisible": bool(inv_var.get()), "cookie_jar": bool(cj_var.get()),
                "upstream": {"enabled": bool(up_var.get()), "host": ent["host"].get().strip(),
                             "port": uport, "user": ent["user"].get().strip(),
                             "password": ent["password"].get()},
            })
            if self.server.host is not None and (lhost, lport) != (self.server.host, self.server.port):
                try:
                    self.server.start(lhost, lport)
                except OSError as ex:
                    messagebox.showerror("Gagal bind", str(ex), parent=f)
                    return
            self._refresh_status()
            messagebox.showinfo("Tersimpan", "Pengaturan disimpan. Ganti bahasa berlaku setelah aplikasi dijalankan ulang.", parent=f)

        ttk.Button(f, text="Simpan & Terapkan", style="Accent.TButton",
                   command=apply_proxy).pack(anchor="e", pady=(16, 0))

    # --- tab 2: certificate ---
    def _tab_cert(self, nb):
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text="  Certificate  ")
        exists = os.path.exists(ca_mod.CA_CERT)
        ttk.Label(f, text="Certificate Authority (CA)", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(f, text=f"Lokasi: {ca_mod.CA_CERT}").pack(anchor="w", pady=(6, 0))
        ttk.Label(f, text=f"Status: {'ADA' if exists else 'BELUM dibuat'}",
                  foreground=(OK_GREEN if exists else STOP_RED)).pack(anchor="w")
        ttk.Label(f, wraplength=560, foreground="#555", text=(
            "CA ini dipakai untuk menandatangani sertifikat HTTPS on-the-fly. Install ca.crt "
            "sebagai trusted CA di device (laptop/HP) agar HTTPS bisa dibuka. Regenerate akan "
            "membuat CA baru — semua device harus memasang ulang ca.crt.")).pack(anchor="w", pady=12)

        row = ttk.Frame(f)
        row.pack(anchor="w")
        ttk.Button(row, text="Regenerate Certificate", command=self._regenerate_cert).pack(side="left")
        ttk.Button(row, text="Export ca.crt…", command=self._export_ca).pack(side="left", padx=8)

    # --- tab 4: AI ---
    def _tab_ai(self, nb):
        cfg = config.get().get("ai", {})
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text="  AI  ")
        ttk.Label(f, text="Koneksi ke AI lokal (Prakash AI)", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        g = ttk.Frame(f); g.pack(fill="x", pady=(8, 0))

        ttk.Label(g, text="Jenis endpoint").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
        kind = ttk.Combobox(g, width=26, values=["openai", "ollama"], state="readonly")
        kind.set(cfg.get("kind", "openai"))
        kind.grid(row=0, column=1, sticky="w")
        ttk.Label(g, text="URL").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))
        e_url = ttk.Entry(g, width=46); e_url.insert(0, cfg.get("url", "")); e_url.grid(row=1, column=1, sticky="w")
        ttk.Label(g, text="Model").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 10))
        e_model = ttk.Combobox(g, width=44); e_model.set(cfg.get("model", "")); e_model.grid(row=2, column=1, sticky="w")

        def load_models():
            cur = {"kind": kind.get(), "url": e_url.get().strip(),
                   "model": e_model.get().strip(), "api_key": e_key.get()}
            models = ai_explain.list_models(cur)
            if models:
                e_model["values"] = models
                if not e_model.get():
                    e_model.set(models[0])
                messagebox.showinfo("Model", f"Ditemukan {len(models)} model.", parent=f)
            else:
                messagebox.showwarning("Model", "Tidak bisa mengambil daftar model dari gateway.\n"
                                                "Cek URL, atau isi nama model manual.", parent=f)
        ttk.Button(g, text="Muat Model", command=load_models).grid(row=2, column=2, padx=6)
        ttk.Label(g, text="API key (opsional)").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 10))
        e_key = ttk.Entry(g, width=46, show="*"); e_key.insert(0, cfg.get("api_key", "")); e_key.grid(row=3, column=1, sticky="w")

        ttk.Label(f, foreground="#666", wraplength=560, text=(
            "openai = endpoint /v1/chat/completions (llama.cpp, LM Studio, vLLM, text-generation-webui). "
            "ollama = /api/chat. Contoh URL: http://127.0.0.1:1234/v1/chat/completions  atau  "
            "http://127.0.0.1:11434/api/chat")).pack(anchor="w", pady=10)

        def save():
            config.update({"ai": {"kind": kind.get(), "url": e_url.get().strip(),
                                  "model": e_model.get().strip(), "api_key": e_key.get()}})
            messagebox.showinfo("Tersimpan", "Pengaturan AI disimpan.", parent=f)

        def test():
            save()
            try:
                out = ai_explain.explain("GET https://example.com/ HTTP/1.1\nHost: example.com",
                                         "HTTP/1.1 200 OK\n\n<html>ok</html>", config.get().get("ai", {}))
                messagebox.showinfo("Tes AI", "Berhasil! Contoh jawaban:\n\n" + out[:500], parent=f)
            except Exception as ex:
                messagebox.showerror("Tes AI gagal", str(ex), parent=f)

        rowb = ttk.Frame(f); rowb.pack(anchor="w")
        ttk.Button(rowb, text="Simpan", style="Accent.TButton", command=save).pack(side="left")
        ttk.Button(rowb, text="Tes Koneksi", command=test).pack(side="left", padx=8)

    # --- tab 3: plugins ---
    def _tab_plugins(self, nb):
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text="  Plugins  ")

        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Plugin terinstal (folder: plugins/)",
                  font=("Segoe UI", 11, "bold")).pack(side="left")

        cols = ("status", "name", "desc")
        tv = ttk.Treeview(f, columns=cols, show="headings", height=11)
        tv.heading("status", text="Aktif")
        tv.heading("name", text="Nama")
        tv.heading("desc", text="Deskripsi")
        tv.column("status", width=60, anchor="center")
        tv.column("name", width=180)
        tv.column("desc", width=320)
        tv.pack(fill="both", expand=True, pady=(10, 8))

        def reload_list():
            plugins.load_all()
            tv.delete(*tv.get_children())
            for p in plugins.plugins:
                mark = "✓" if plugins.is_enabled(p.name) else ""
                desc = p.description or ("ERROR: " + p.error.splitlines()[-1] if p.error else "")
                tv.insert("", "end", iid=p.filename, values=(mark, p.name, desc))
            self._refresh_status()

        def toggle_selected(_evt=None):
            sel = tv.selection()
            if not sel:
                return
            fn = sel[0]
            p = next((x for x in plugins.plugins if x.filename == fn), None)
            if not p:
                return
            plugins.set_enabled(p.name, not plugins.is_enabled(p.name))
            reload_list()
            tv.selection_set(fn)

        tv.bind("<Double-1>", toggle_selected)

        def install_plugin():
            path = filedialog.askopenfilename(
                title="Pilih file plugin (.py)", filetypes=[("Python", "*.py")], parent=f)
            if not path:
                return
            ok, msg = plugins.import_file(path)
            if ok:
                # plugin baru otomatis diaktifkan
                base = os.path.basename(path)
                newp = next((x for x in plugins.plugins if x.filename == base), None)
                if newp:
                    plugins.set_enabled(newp.name, True)
                reload_list()
                messagebox.showinfo("Install Plugin", msg + " dan diaktifkan.", parent=f)
            else:
                messagebox.showerror("Gagal import", msg, parent=f)

        def remove_plugin():
            sel = tv.selection()
            if not sel:
                return
            fn = sel[0]
            if not messagebox.askyesno("Hapus Plugin", f"Hapus file plugin '{fn}'?", parent=f):
                return
            try:
                os.remove(os.path.join(PLUGINS_DIR, fn))
            except OSError as e:
                messagebox.showerror("Gagal", str(e), parent=f)
                return
            reload_list()

        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Button(bar, text="Install Plugin…", style="Accent.TButton", command=install_plugin).pack(side="left")
        ttk.Button(bar, text="Aktif/Non-aktif", command=toggle_selected).pack(side="left", padx=6)
        ttk.Button(bar, text="Hapus", command=remove_plugin).pack(side="left")
        ttk.Button(bar, text="Reload", command=reload_list).pack(side="left", padx=6)
        ttk.Button(bar, text="Buka Folder", command=self._open_plugins_folder).pack(side="left")
        ttk.Label(f, foreground="#666", wraplength=560, text=(
            "Double-click untuk aktif/non-aktif. Plugin berjalan otomatis: on_request untuk "
            "request, on_response untuk response. Contoh 'Buka Blokir' menghapus header "
            "pemblokir & mengubah 403/451 jadi 200.")).pack(anchor="w", pady=(10, 0))

        reload_list()

    # ------------------------------ Tab: Repeater ------------------------------

    def _build_repeater_tab(self):
        tab = ttk.Frame(self.nb, padding=4)
        self.nb.add(tab, text=t("tab_repeater"))
        self.tab_repeater = tab
        bar = ttk.Frame(tab)
        bar.pack(fill="x")
        ttk.Button(bar, text="+ Tab Baru", command=lambda: self._new_repeater_session()).pack(side="left")
        ttk.Label(bar, text="Tiap kiriman jadi tab sendiri. Tutup lewat tombol ✕ Tutup di dalam tab.",
                  foreground="#666").pack(side="left", padx=10)
        self.rp_nb = ttk.Notebook(tab)
        self.rp_nb.pack(fill="both", expand=True, pady=(4, 0))
        self.rp_sessions = {}
        self.rp_counter = 0
        self._new_repeater_session()

    def _new_repeater_session(self, prefill=None):
        self.rp_counter += 1
        n = self.rp_counter
        s = {}
        f = ttk.Frame(self.rp_nb, padding=6)

        top = ttk.Frame(f); top.pack(fill="x")
        ttk.Label(top, text="Method").pack(side="left")
        s["method"] = ttk.Entry(top, width=8); s["method"].insert(0, "GET")
        s["method"].pack(side="left", padx=(4, 10))
        s["https"] = tk.IntVar(value=1)
        ttk.Checkbutton(top, text="https", variable=s["https"]).pack(side="left")
        ttk.Label(top, text="Host").pack(side="left", padx=(10, 0))
        s["host"] = ttk.Entry(top, width=24); s["host"].pack(side="left", padx=4)
        ttk.Label(top, text="Port").pack(side="left")
        s["port"] = ttk.Entry(top, width=6); s["port"].insert(0, "443")
        s["port"].pack(side="left", padx=4)
        s["send"] = ttk.Button(top, text="Send", style="Accent.TButton", command=lambda: self._session_send(s))
        s["send"].pack(side="right")
        ttk.Button(top, text="Duplikat", command=lambda: self._duplicate_repeater(s)).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Lihat JWT", command=lambda: self._session_view_jwt(s)).pack(side="right", padx=(0, 6))
        ttk.Button(top, text="✕ Tutup", command=lambda: self._close_repeater_session(f)).pack(side="right", padx=(0, 6))

        p2 = ttk.Frame(f); p2.pack(fill="x", pady=(6, 0))
        ttk.Label(p2, text="Path").pack(side="left")
        s["path"] = ttk.Entry(p2); s["path"].insert(0, "/")
        s["path"].pack(side="left", fill="x", expand=True, padx=4)

        split = ttk.PanedWindow(f, orient="horizontal")
        split.pack(fill="both", expand=True, pady=(6, 0))
        reqf = ttk.Frame(split)
        ttk.Label(reqf, text="Request (Headers lalu baris kosong lalu Body)").pack(anchor="w")
        s["headers"] = scrolledtext.ScrolledText(reqf, height=8, wrap="none", font=self.mono)
        s["headers"].pack(fill="both", expand=True)
        ttk.Label(reqf, text="Body").pack(anchor="w")
        s["body"] = scrolledtext.ScrolledText(reqf, height=8, wrap="none", font=self.mono)
        s["body"].pack(fill="both", expand=True)
        split.add(reqf, weight=1)
        resf = ttk.Frame(split)
        s["status"] = ttk.Label(resf, text="Response", foreground="#666"); s["status"].pack(anchor="w")
        s["resp"] = scrolledtext.ScrolledText(resf, wrap="none", font=self.mono, state="disabled")
        s["resp"].pack(fill="both", expand=True)
        self._attach_find(resf, s["resp"])
        split.add(resf, weight=1)

        s["frame"] = f
        self.rp_sessions[str(f)] = s
        self.rp_nb.add(f, text=f"Rep {n}")
        if prefill:
            s["method"].delete(0, "end"); s["method"].insert(0, prefill["method"])
            s["https"].set(1 if prefill["scheme"] == "https" else 0)
            s["host"].delete(0, "end"); s["host"].insert(0, prefill["host"])
            s["port"].delete(0, "end"); s["port"].insert(0, str(prefill["port"]))
            s["path"].delete(0, "end"); s["path"].insert(0, prefill["path"])
            s["headers"].delete("1.0", "end")
            s["headers"].insert("1.0", "\n".join(f"{k}: {v}" for k, v in prefill["headers"]))
            s["body"].delete("1.0", "end"); s["body"].insert("1.0", prefill.get("body_text") or "")
            self.rp_nb.tab(f, text=f"{n}:{(prefill['host'] or '')[:14]}")
        self.rp_nb.select(f)
        return s

    def _close_repeater_session(self, frame):
        self.rp_sessions.pop(str(frame), None)
        try:
            self.rp_nb.forget(frame)
        except Exception:
            pass
        frame.destroy()
        if not self.rp_sessions:
            self._new_repeater_session()

    def _fill_repeater(self, method, scheme, host, port, path, headers, body_text):
        self._new_repeater_session(prefill={
            "method": method, "scheme": scheme, "host": host, "port": port,
            "path": path, "headers": headers, "body_text": body_text})
        self.nb.select(self.tab_repeater)

    def _send_to_repeater(self):
        e = self._selected_history()
        if not e:
            messagebox.showinfo("Repeater", "Pilih satu baris di HTTP History dulu.")
            return
        self._fill_repeater(e["method"], e["scheme"], e["host"], e["port"],
                            e["path"], e["req_headers"], e["req_text"])

    def _duplicate_repeater(self, s):
        headers = []
        for line in s["headers"].get("1.0", "end-1c").splitlines():
            i = line.find(":")
            if i >= 0:
                headers.append((line[:i].strip(), line[i + 1:].strip()))
        self._new_repeater_session(prefill={
            "method": s["method"].get(), "scheme": "https" if s["https"].get() else "http",
            "host": s["host"].get(), "port": s["port"].get(), "path": s["path"].get(),
            "headers": headers, "body_text": s["body"].get("1.0", "end-1c")})

    def _session_view_jwt(self, s):
        headers = []
        for line in s["headers"].get("1.0", "end-1c").splitlines():
            i = line.find(":")
            if i >= 0:
                headers.append((line[:i].strip(), line[i + 1:].strip()))
        tokens = jwt_tool.find_in_headers(headers)
        if not tokens:
            messagebox.showinfo("JWT", "Tidak ada token JWT (eyJ...) di request ini.")
            return
        self.jwt_in.delete("1.0", "end"); self.jwt_in.insert("1.0", tokens[0])
        self.nb.select(self.tab_jwt); self._jwt_decode()

    def _session_send(self, s):
        method = s["method"].get().strip() or "GET"
        scheme = "https" if s["https"].get() else "http"
        host = s["host"].get().strip()
        if not host:
            messagebox.showerror("Repeater", "Host kosong."); return
        try:
            port = int(s["port"].get())
        except ValueError:
            messagebox.showerror("Repeater", "Port harus angka."); return
        path = s["path"].get().strip() or "/"
        headers = []
        for line in s["headers"].get("1.0", "end-1c").splitlines():
            line = line.strip()
            if not line:
                continue
            i = line.find(":")
            headers.append((line[:i].strip(), line[i + 1:].strip()) if i >= 0 else (line, ""))
        body = s["body"].get("1.0", "end-1c").encode("utf-8")
        s["status"].config(text="Mengirim…"); s["send"].config(state="disabled")

        def worker():
            try:
                status_line, rheaders, rbody = proxy.send_once(method, scheme, host, port, path, headers, body)
                dec, _ = interceptor.decompress(rheaders, rbody)
                try:
                    text = dec.decode("utf-8")
                except UnicodeDecodeError:
                    text = dec.decode("latin1")
                out = status_line + "\n" + "\n".join(f"{k}: {v}" for k, v in rheaders) + "\n\n" + text
                self.root.after(0, lambda: self._session_done(s, out, f"{status_line}  ({len(rbody)} bytes)"))
            except Exception as ex:
                self.root.after(0, lambda: self._session_done(s, f"ERROR: {ex}", "Gagal"))

        import threading as _t
        _t.Thread(target=worker, daemon=True).start()

    def _session_done(self, s, text, status):
        s["resp"].config(state="normal"); s["resp"].delete("1.0", "end")
        s["resp"].insert("1.0", text); s["resp"].config(state="disabled")
        s["status"].config(text="Response: " + status)
        s["send"].config(state="normal")

    # ------------------------------ Tab: Intruder ------------------------------

    def _build_intruder_tab(self):
        tab = ttk.Frame(self.nb, padding=4)
        self.nb.add(tab, text=t("tab_intruder"))
        self.tab_intruder = tab
        bar = ttk.Frame(tab); bar.pack(fill="x")
        ttk.Button(bar, text="+ Tab Baru", command=lambda: self._new_intruder_session()).pack(side="left")
        ttk.Label(bar, foreground="#666",
                  text="Taruh {PAYLOAD} di Path/Headers/Body. Tiap kiriman jadi tab sendiri.").pack(side="left", padx=10)
        self.in_nb = ttk.Notebook(tab)
        self.in_nb.pack(fill="both", expand=True, pady=(4, 0))
        self.in_sessions = {}
        self.in_counter = 0
        self._new_intruder_session()

    def _new_intruder_session(self, prefill=None):
        self.in_counter += 1
        n = self.in_counter
        s = {"responses": {}}
        f = ttk.Frame(self.in_nb, padding=6)

        top = ttk.Frame(f); top.pack(fill="x")
        ttk.Label(top, text="Method").pack(side="left")
        s["method"] = ttk.Entry(top, width=8); s["method"].insert(0, "GET")
        s["method"].pack(side="left", padx=(4, 10))
        s["https"] = tk.IntVar(value=1)
        ttk.Checkbutton(top, text="https", variable=s["https"]).pack(side="left")
        ttk.Label(top, text="Host").pack(side="left", padx=(10, 0))
        s["host"] = ttk.Entry(top, width=20); s["host"].pack(side="left", padx=4)
        ttk.Label(top, text="Port").pack(side="left")
        s["port"] = ttk.Entry(top, width=6); s["port"].insert(0, "443")
        s["port"].pack(side="left", padx=4)
        s["start"] = ttk.Button(top, text="Start Attack", style="Accent.TButton",
                                command=lambda: self._intruder_start(s))
        s["start"].pack(side="right")
        ttk.Button(top, text="✕ Tutup", command=lambda: self._close_intruder_session(f)).pack(side="right", padx=(0, 6))

        p2 = ttk.Frame(f); p2.pack(fill="x", pady=(6, 0))
        ttk.Label(p2, text="Path").pack(side="left")
        s["path"] = ttk.Entry(p2); s["path"].insert(0, "/")
        s["path"].pack(side="left", fill="x", expand=True, padx=4)

        split = ttk.PanedWindow(f, orient="horizontal")
        split.pack(fill="both", expand=True, pady=(4, 0))
        leftf = ttk.Frame(split)
        ttk.Label(leftf, text="Headers").pack(anchor="w")
        s["headers"] = scrolledtext.ScrolledText(leftf, height=7, wrap="none", font=self.mono)
        s["headers"].pack(fill="both", expand=True)
        ttk.Label(leftf, text="Body").pack(anchor="w")
        s["body"] = scrolledtext.ScrolledText(leftf, height=4, wrap="none", font=self.mono)
        s["body"].pack(fill="both", expand=True)
        ttk.Label(leftf, text="Payloads (satu per baris)").pack(anchor="w")
        s["payloads"] = scrolledtext.ScrolledText(leftf, height=6, wrap="none", font=self.mono)
        s["payloads"].pack(fill="both", expand=True)
        split.add(leftf, weight=1)

        rightf = ttk.Frame(split)
        cols = ("n", "payload", "status", "len", "ms")
        s["results"] = ttk.Treeview(rightf, columns=cols, show="headings", height=10)
        for c, ttl, w, a in (("n", "#", 36, "e"), ("payload", "Payload", 150, "w"),
                           ("status", "Status", 56, "center"), ("len", "Len", 60, "e"),
                           ("ms", "ms", 50, "e")):
            s["results"].heading(c, text=ttl); s["results"].column(c, width=w, anchor=a)
        s["results"].pack(fill="both", expand=True)
        s["results"].bind("<<TreeviewSelect>>", lambda e, s=s: self._intruder_show(s))
        s["resp"] = scrolledtext.ScrolledText(rightf, height=9, wrap="none", font=self.mono, state="disabled")
        s["resp"].pack(fill="both", expand=True, pady=(6, 0))
        self._attach_find(rightf, s["resp"])
        split.add(rightf, weight=1)

        s["frame"] = f
        self.in_sessions[str(f)] = s
        self.in_nb.add(f, text=f"Intr {n}")
        if prefill:
            s["method"].delete(0, "end"); s["method"].insert(0, prefill["method"])
            s["https"].set(1 if prefill["scheme"] == "https" else 0)
            s["host"].delete(0, "end"); s["host"].insert(0, prefill["host"])
            s["port"].delete(0, "end"); s["port"].insert(0, str(prefill["port"]))
            s["path"].delete(0, "end"); s["path"].insert(0, prefill["path"])
            s["headers"].delete("1.0", "end")
            s["headers"].insert("1.0", "\n".join(f"{k}: {v}" for k, v in prefill["headers"]))
            s["body"].delete("1.0", "end"); s["body"].insert("1.0", prefill.get("body_text") or "")
            self.in_nb.tab(f, text=f"{n}:{(prefill['host'] or '')[:12]}")
        self.in_nb.select(f)
        return s

    def _close_intruder_session(self, frame):
        self.in_sessions.pop(str(frame), None)
        try:
            self.in_nb.forget(frame)
        except Exception:
            pass
        frame.destroy()
        if not self.in_sessions:
            self._new_intruder_session()

    def _fill_intruder(self, method, scheme, host, port, path, headers, body_text):
        self._new_intruder_session(prefill={
            "method": method, "scheme": scheme, "host": host, "port": port,
            "path": path, "headers": headers, "body_text": body_text})
        self.nb.select(self.tab_intruder)

    def _send_to_intruder(self):
        e = self._selected_history()
        if not e:
            messagebox.showinfo("Intruder", "Pilih satu baris di HTTP History dulu.")
            return
        self._fill_intruder(e["method"], e["scheme"], e["host"], e["port"],
                            e["path"], e["req_headers"], e["req_text"])

    def _intruder_start(self, s):
        method0 = s["method"].get().strip() or "GET"
        scheme = "https" if s["https"].get() else "http"
        host0 = s["host"].get().strip()
        if not host0:
            messagebox.showerror("Intruder", "Host kosong."); return
        try:
            port = int(s["port"].get())
        except ValueError:
            messagebox.showerror("Intruder", "Port harus angka."); return
        path0 = s["path"].get().strip() or "/"
        headers0 = s["headers"].get("1.0", "end-1c")
        body0 = s["body"].get("1.0", "end-1c")
        payloads = [p for p in s["payloads"].get("1.0", "end-1c").splitlines() if p.strip() != ""]
        if not payloads:
            messagebox.showinfo("Intruder", "Isi daftar payload dulu.")
            return
        if "{PAYLOAD}" not in (path0 + headers0 + body0 + host0):
            messagebox.showinfo("Intruder", "Belum ada penanda {PAYLOAD} di request.")
            return

        s["results"].delete(*s["results"].get_children())
        s["responses"] = {}
        s["start"].config(state="disabled")
        import time as _time

        def worker():
            for i, pl in enumerate(payloads, start=1):
                def sub(v):
                    return v.replace("{PAYLOAD}", pl)
                method = sub(method0); host = sub(host0); path = sub(path0)
                headers = []
                for line in sub(headers0).splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    j = line.find(":")
                    headers.append((line[:j].strip(), line[j + 1:].strip()) if j >= 0 else (line, ""))
                body = sub(body0).encode("utf-8")
                t0 = _time.time()
                try:
                    status_line, rheaders, rbody = proxy.send_once(method, scheme, host, port, path, headers, body)
                    dec, _ = interceptor.decompress(rheaders, rbody)
                    try:
                        text = dec.decode("utf-8")
                    except UnicodeDecodeError:
                        text = dec.decode("latin1")
                    ms = int((_time.time() - t0) * 1000)
                    status = status_line.split(" ")[1] if len(status_line.split(" ")) > 1 else "?"
                    full = status_line + "\n" + "\n".join(f"{k}: {v}" for k, v in rheaders) + "\n\n" + text
                    self.root.after(0, lambda i=i, pl=pl, status=status, n=len(rbody), ms=ms, full=full:
                                    self._intruder_row(s, i, pl, status, n, ms, full))
                except Exception as ex:
                    self.root.after(0, lambda i=i, pl=pl, ex=ex:
                                    self._intruder_row(s, i, pl, "ERR", 0, 0, f"ERROR: {ex}"))
            self.root.after(0, lambda: s["start"].config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _intruder_row(self, s, i, payload, status, length, ms, full):
        iid = str(i)
        s["results"].insert("", "end", iid=iid, values=(i, payload[:40], status, length, ms))
        s["responses"][iid] = full

    def _intruder_show(self, s):
        sel = s["results"].selection()
        if not sel:
            return
        txt = s["responses"].get(sel[0], "")
        s["resp"].config(state="normal")
        s["resp"].delete("1.0", "end")
        s["resp"].insert("1.0", txt)
        s["resp"].config(state="disabled")

    # ------------------------------ Tab: AI Runner ------------------------------

    def _build_airunner_tab(self):
        tab = ttk.Frame(self.nb, padding=6)
        self.nb.add(tab, text=t("tab_airunner"))
        self.tab_airunner = tab
        self.air_base = ""
        self.air_results = {}

        ttk.Label(tab, text="Instruksi untuk AI (AI menyusun daftar request lalu dijalankan otomatis):").pack(anchor="w")
        self.air_instr = scrolledtext.ScrolledText(tab, height=4, wrap="word", font=("Segoe UI", 10))
        self.air_instr.insert("1.0", "Contoh: akses semua halaman /listings/1 sampai /listings/20 di https://situs-saya.com dan laporkan status-nya.")
        self.air_instr.pack(fill="x")

        bar = ttk.Frame(tab); bar.pack(fill="x", pady=6)
        self.air_run = ttk.Button(bar, text="Generate & Jalankan", style="Accent.TButton", command=self._airunner_start)
        self.air_run.pack(side="left")
        ttk.Button(bar, text="Pakai request dari History", command=self._airunner_use_history).pack(side="left", padx=6)
        self.air_status = ttk.Label(bar, text="", foreground="#0067c0")
        self.air_status.pack(side="left", padx=10)

        split = ttk.PanedWindow(tab, orient="horizontal")
        split.pack(fill="both", expand=True)
        lf = ttk.Frame(split)
        cols = ("n", "method", "url", "status", "len")
        self.air_table = ttk.Treeview(lf, columns=cols, show="headings", height=12)
        for c, ttl, w, a in (("n", "#", 36, "e"), ("method", "Method", 60, "w"),
                           ("url", "URL", 320, "w"), ("status", "Status", 56, "center"),
                           ("len", "Len", 60, "e")):
            self.air_table.heading(c, text=ttl); self.air_table.column(c, width=w, anchor=a)
        self.air_table.pack(fill="both", expand=True)
        self.air_table.bind("<<TreeviewSelect>>", self._airunner_show)
        split.add(lf, weight=1)
        rf = ttk.Frame(split)
        self.air_resp = scrolledtext.ScrolledText(rf, wrap="none", font=self.mono, state="disabled")
        self.air_resp.pack(fill="both", expand=True)
        self._attach_find(rf, self.air_resp)
        split.add(rf, weight=1)

    def _airunner_use_history(self):
        e = self._selected_history()
        if not e:
            messagebox.showinfo("AI Runner", "Pilih satu baris di HTTP History dulu.")
            return
        self.air_base = f'{e["method"]} {e["url"]}\n' + "\n".join(f"{k}: {v}" for k, v in e["req_headers"])
        if e["req_text"]:
            self.air_base += "\n\n" + e["req_text"]
        self.air_status.config(text="Base request diambil dari History.")

    def _airunner_start(self):
        instr = self.air_instr.get("1.0", "end-1c").strip()
        if not instr:
            messagebox.showinfo("AI Runner", "Isi instruksi dulu.")
            return
        cfg = config.get().get("ai", {})
        self.air_table.delete(*self.air_table.get_children())
        self.air_results = {}
        self.air_run.config(state="disabled")
        self.air_status.config(text="AI menyusun daftar request…")

        def worker():
            try:
                plan = ai_explain.plan_requests(instr, self.air_base, cfg)
            except Exception as ex:
                self.root.after(0, lambda: (self.air_status.config(text="Gagal: " + str(ex)[:80]),
                                            self.air_run.config(state="normal")))
                return
            self.root.after(0, lambda: self.air_status.config(text=f"Menjalankan {len(plan)} request…"))
            for i, r in enumerate(plan, start=1):
                u = urlsplit(r["url"])
                scheme = u.scheme or "https"
                host = u.hostname or ""
                port = u.port or (443 if scheme == "https" else 80)
                path = (u.path or "/") + (("?" + u.query) if u.query else "")
                headers = list(r.get("headers", {}).items())
                body = (r.get("body") or "").encode("utf-8")
                try:
                    status_line, rheaders, rbody = proxy.send_once(
                        r["method"], scheme, host, port, path, headers, body)
                    dec, _ = interceptor.decompress(rheaders, rbody)
                    try:
                        text = dec.decode("utf-8")
                    except UnicodeDecodeError:
                        text = dec.decode("latin1")
                    st = status_line.split(" ")[1] if len(status_line.split(" ")) > 1 else "?"
                    full = status_line + "\n" + "\n".join(f"{k}: {v}" for k, v in rheaders) + "\n\n" + text
                    self.root.after(0, lambda i=i, r=r, st=st, n=len(rbody), full=full:
                                    self._airunner_row(i, r["method"], r["url"], st, n, full))
                except Exception as ex:
                    self.root.after(0, lambda i=i, r=r, ex=ex:
                                    self._airunner_row(i, r["method"], r["url"], "ERR", 0, f"ERROR: {ex}"))
            self.root.after(0, lambda: (self.air_status.config(text="Selesai."),
                                        self.air_run.config(state="normal")))

        threading.Thread(target=worker, daemon=True).start()

    def _airunner_row(self, i, method, url, status, length, full):
        iid = str(i)
        self.air_table.insert("", "end", iid=iid, values=(i, method, url[:80], status, length))
        self.air_results[iid] = full

    def _airunner_show(self, _evt):
        sel = self.air_table.selection()
        if not sel:
            return
        txt = self.air_results.get(sel[0], "")
        self.air_resp.config(state="normal")
        self.air_resp.delete("1.0", "end")
        self.air_resp.insert("1.0", txt)
        self.air_resp.config(state="disabled")

    # ------------------------------ Tab: Plugins ------------------------------

    def _build_plugins_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text=t("tab_plugins"))
        self.tab_plugins = tab
        bar = ttk.Frame(tab); bar.pack(fill="x")
        ttk.Button(bar, text="Install Plugin…", style="Accent.TButton", command=self._plugins_install).pack(side="left")
        ttk.Button(bar, text="Aktif/Non-aktif", command=self._pg_toggle).pack(side="left", padx=6)
        ttk.Button(bar, text="Hapus", command=self._pg_remove).pack(side="left")
        ttk.Button(bar, text="Reload", command=self._plugins_reload).pack(side="left", padx=6)
        ttk.Button(bar, text="Buka Folder", command=self._open_plugins_folder).pack(side="left")

        cols = ("status", "name", "type", "desc")
        self.pg_table = ttk.Treeview(tab, columns=cols, show="headings", height=12)
        for c, ttl, w, a in (("status", "Aktif", 60, "center"), ("name", "Nama", 200, "w"),
                           ("type", "Tipe", 90, "center"), ("desc", "Deskripsi", 360, "w")):
            self.pg_table.heading(c, text=ttl); self.pg_table.column(c, width=w, anchor=a)
        self.pg_table.pack(fill="both", expand=True, pady=(8, 6))
        self.pg_table.bind("<Double-1>", lambda e: self._pg_toggle())
        ttk.Label(tab, foreground="#666", wraplength=640, text=(
            "Cukup Install file .py lalu aktifkan — tidak perlu melihat/menulis kode di sini. "
            "Tipe 'auto' = jalan otomatis tiap trafik (on_request/on_response). "
            "Tipe 'action' (mis. OCR) = dipanggil manual: klik-kanan sebuah baris di HTTP History "
            "> Kirim ke Plugin.")).pack(anchor="w")
        self._plugins_reload()

    def _plugins_reload(self, select_filename=None):
        plugins.load_all()
        self.pg_table.delete(*self.pg_table.get_children())
        for p in plugins.plugins:
            mark = "✓" if plugins.is_enabled(p.name) else ""
            typ = "action" if p.has_action else ("auto" if p.module else "ERROR")
            desc = p.description or (p.error.splitlines()[-1] if p.error else "")
            self.pg_table.insert("", "end", iid=p.filename, values=(mark, p.name, typ, desc))
        if select_filename and self.pg_table.exists(select_filename):
            self.pg_table.selection_set(select_filename)
        self._refresh_status()

    def _pg_selected(self):
        sel = self.pg_table.selection()
        if not sel:
            return None
        return next((x for x in plugins.plugins if x.filename == sel[0]), None)

    def _pg_toggle(self):
        p = self._pg_selected()
        if not p:
            return
        turning_on = not plugins.is_enabled(p.name)
        plugins.set_enabled(p.name, turning_on)
        self._plugins_reload(select_filename=p.filename)
        if turning_on:
            self._ensure_plugin_deps(p)

    def _ensure_plugin_deps(self, p):
        reqs = list(getattr(p.module, "REQUIRES", []) or []) if p.module else []
        if not reqs:
            return
        missing = plugins._missing(reqs)
        if not missing:
            return
        if not messagebox.askyesno(
                "Dependensi plugin",
                f"Plugin '{p.name}' butuh paket: {', '.join(missing)}.\n\nInstall otomatis via pip sekarang?"):
            return
        win = self._show_text_window("Install dependensi — " + p.name,
                                     "Menginstall: " + ", ".join(missing) + " …\n\n")

        def log(s):
            self.root.after(0, lambda: self._append_text_window(win, s))

        def worker():
            ok, msg = plugins.ensure_requirements(p, log)
            tail = f"\n\n[SELESAI] {'Berhasil' if ok else 'Gagal'}: {msg}"
            if "OCR" in p.name or "ocr" in p.filename:
                tail += ("\n\nCatatan: OCR juga butuh program Tesseract (bukan paket pip). "
                         "Install dari github.com/UB-Mannheim/tesseract/wiki bila belum.")
            self.root.after(0, lambda: self._append_text_window(win, tail))

        threading.Thread(target=worker, daemon=True).start()

    def _pg_remove(self):
        p = self._pg_selected()
        if not p:
            return
        if not messagebox.askyesno("Hapus Plugin", f"Hapus file plugin '{p.filename}'?"):
            return
        try:
            os.remove(os.path.join(PLUGINS_DIR, p.filename))
        except OSError as e:
            messagebox.showerror("Gagal", str(e)); return
        self._plugins_reload()

    def _plugins_install(self):
        path = filedialog.askopenfilename(title="Pilih file plugin (.py)", filetypes=[("Python", "*.py")])
        if not path:
            return
        ok, msg = plugins.import_file(path)
        if not ok:
            messagebox.showerror("Gagal import", msg)
            return
        base = os.path.basename(path)
        newp = next((x for x in plugins.plugins if x.filename == base), None)
        if newp:
            plugins.set_enabled(newp.name, True)
        self.nb.select(self.tab_plugins)
        self._plugins_reload(select_filename=base)
        messagebox.showinfo("Install Plugin", msg + " dan diaktifkan.")
        if newp:
            self._ensure_plugin_deps(newp)

    def _run_plugin_action(self, plugin_filename):
        e = self._selected_history()
        if not e:
            messagebox.showinfo("Plugin", "Pilih satu baris di HTTP History dulu.")
            return
        p = next((x for x in plugins.plugins if x.filename == plugin_filename), None)
        if not p:
            return
        win = self._show_text_window(f"Plugin: {p.name}", "Memproses…")

        def worker():
            out = plugins.run_action(p, e)
            self.root.after(0, lambda: self._set_text_window(win, out))

        import threading as _t
        _t.Thread(target=worker, daemon=True).start()

    # ------------------------------ Tab: JWT ------------------------------

    def _build_jwt_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text=t("tab_jwt"))
        self.tab_jwt = tab

        ttk.Label(tab, text="Token JWT").pack(anchor="w")
        self.jwt_in = scrolledtext.ScrolledText(tab, height=4, wrap="char", font=self.mono)
        self.jwt_in.pack(fill="x")

        row = ttk.Frame(tab)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="Decode", style="Accent.TButton", command=self._jwt_decode).pack(side="left")
        ttk.Label(row, text="Alg").pack(side="left", padx=(14, 4))
        self.jwt_alg = ttk.Combobox(row, width=8, values=["none", "HS256"], state="readonly")
        self.jwt_alg.set("HS256")
        self.jwt_alg.pack(side="left")
        ttk.Label(row, text="Secret (HS256)").pack(side="left", padx=(10, 4))
        self.jwt_secret = ttk.Entry(row, width=24)
        self.jwt_secret.pack(side="left")
        ttk.Button(row, text="Re-Sign / Encode", command=self._jwt_encode).pack(side="left", padx=10)

        split = ttk.PanedWindow(tab, orient="horizontal")
        split.pack(fill="both", expand=True)
        hf = ttk.Labelframe(split, text="Header (JSON)", style="Card.TLabelframe")
        self.jwt_header = scrolledtext.ScrolledText(hf, height=8, wrap="none", font=self.mono)
        self.jwt_header.pack(fill="both", expand=True)
        split.add(hf, weight=1)
        pf = ttk.Labelframe(split, text="Payload (JSON) — bisa diedit", style="Card.TLabelframe")
        self.jwt_payload = scrolledtext.ScrolledText(pf, height=8, wrap="none", font=self.mono)
        self.jwt_payload.pack(fill="both", expand=True)
        split.add(pf, weight=1)

        orow = ttk.Frame(tab); orow.pack(fill="x", pady=(6, 0))
        ttk.Label(orow, text="Output token").pack(side="left")
        ttk.Button(orow, text="Kirim ke Repeater (Authorization)",
                   command=self._jwt_to_repeater).pack(side="right")
        self.jwt_out = scrolledtext.ScrolledText(tab, height=4, wrap="char", font=self.mono)
        self.jwt_out.pack(fill="x")

    def _jwt_decode(self):
        token = self.jwt_in.get("1.0", "end-1c").strip()
        if not token:
            return
        try:
            header, payload, _sig = jwt_tool.decode(token)
        except Exception as ex:
            messagebox.showerror("JWT", f"Gagal decode: {ex}")
            return
        self.jwt_header.delete("1.0", "end")
        self.jwt_header.insert("1.0", json.dumps(header, indent=2))
        self.jwt_payload.delete("1.0", "end")
        self.jwt_payload.insert("1.0", json.dumps(payload, indent=2))
        if header.get("alg"):
            self.jwt_alg.set(header["alg"] if header["alg"] in ("none", "HS256") else "HS256")

    def _jwt_encode(self):
        try:
            header = json.loads(self.jwt_header.get("1.0", "end-1c") or "{}")
            payload = json.loads(self.jwt_payload.get("1.0", "end-1c") or "{}")
        except Exception as ex:
            messagebox.showerror("JWT", f"JSON tidak valid: {ex}")
            return
        alg = self.jwt_alg.get()
        try:
            token = jwt_tool.encode(header, payload, alg=alg, secret=self.jwt_secret.get())
        except Exception as ex:
            messagebox.showerror("JWT", str(ex))
            return
        self.jwt_out.delete("1.0", "end")
        self.jwt_out.insert("1.0", token)

    def _jwt_to_repeater(self):
        token = self.jwt_out.get("1.0", "end-1c").strip() or self.jwt_in.get("1.0", "end-1c").strip()
        if not token:
            messagebox.showinfo("JWT", "Belum ada token (Decode/Encode dulu).")
            return
        self._new_repeater_session(prefill={
            "method": "GET", "scheme": "https", "host": "", "port": 443, "path": "/",
            "headers": [("Authorization", "Bearer " + token)], "body_text": ""})
        self.nb.select(self.tab_repeater)

    def _send_to_jwt(self):
        e = self._selected_history()
        if not e:
            messagebox.showinfo("JWT", "Pilih satu baris di HTTP History dulu.")
            return
        tokens = jwt_tool.find_in_headers(e["req_headers"]) or jwt_tool.find_in_headers(e["res_headers"])
        if not tokens:
            messagebox.showinfo("JWT", "Tidak ada token JWT (eyJ...) di header request/response ini.")
            return
        self.jwt_in.delete("1.0", "end")
        self.jwt_in.insert("1.0", tokens[0])
        self.nb.select(self.tab_jwt)
        self._jwt_decode()

    def _selected_history(self):
        sel = self.htable.selection()
        if not sel:
            return None
        try:
            return history_log.get(int(sel[0]))
        except ValueError:
            return None

    # --- AI dari editor Intercept (request / response yang sedang dibuka) ---
    def _editor_explain_ai(self):
        if self.current_id is None:
            messagebox.showinfo("AI", "Buka sebuah request/response di editor dulu.")
            return
        headers_txt = self.headers_text.get("1.0", "end-1c")
        body_txt = self.body_text.get("1.0", "end-1c")
        if self.current_kind == "request":
            try:
                line = f'{self.entries["method"].get()} {self.entries["host"].get()}{self.entries["path"].get()}'
            except KeyError:
                line = ""
            req = line + "\n" + headers_txt + ("\n\n" + body_txt if body_txt.strip() else "")
            res = ""
        else:
            req = self.req_preview.get("1.0", "end-1c")
            status = self.entries.get("status_line")
            sline = status.get() if status else ""
            res = sline + "\n" + headers_txt + ("\n\n" + body_txt if body_txt.strip() else "")
        self._open_ai_chat(req, res, f"#{self.current_id}")

    # --- AI: jelaskan request+response ---
    def _explain_ai(self):
        e = self._selected_history()
        if not e:
            messagebox.showinfo("AI", "Pilih satu baris di HTTP History dulu.")
            return
        req = f'{e["method"]} {e["url"]}\n' + "\n".join(f"{k}: {v}" for k, v in e["req_headers"])
        if e["req_text"]:
            req += "\n\n" + e["req_text"]
        res = e["status_line"] + "\n" + "\n".join(f"{k}: {v}" for k, v in e["res_headers"])
        if e["res_text"]:
            res += "\n\n" + e["res_text"]
        self._open_ai_chat(req, res, f'#{e["id"]} {e["method"]} {e["host"]}')

    def _open_ai_chat(self, req_text, res_text, ctx_label):
        cfg = config.get().get("ai", {})
        ctx = ai_explain.context_text(req_text, res_text)
        messages = [{"role": "system", "content": ai_explain.SYSTEM}]
        state = {"first": True}

        win = tk.Toplevel(self.root)
        win.title("Tanya AI — " + ctx_label)
        win.geometry("760x640")
        ttk.Label(win, padding=(8, 6), foreground="#555",
                  text="Request & response disertakan otomatis. Tulis pertanyaanmu (boleh diubah), lalu Kirim.").pack(anchor="w")
        out = scrolledtext.ScrolledText(win, wrap="word", font=("Segoe UI", 10), state="disabled")
        out.pack(fill="both", expand=True, padx=8)
        status = ttk.Label(win, text="", foreground="#0067c0", padding=(10, 2))
        status.pack(anchor="w")
        inbar = ttk.Frame(win, padding=8); inbar.pack(fill="x")
        inp = scrolledtext.ScrolledText(inbar, height=3, wrap="word", font=("Segoe UI", 10))
        inp.insert("1.0", "Jelaskan request & response ini.")
        inp.pack(side="left", fill="x", expand=True)
        send_btn = ttk.Button(inbar, text="Kirim", style="Accent.TButton")
        send_btn.pack(side="right", padx=(6, 0))

        def append(role, text):
            out.config(state="normal")
            out.insert("end", f"{role}: {text}\n\n")
            out.config(state="disabled")
            out.see("end")

        def do_send():
            q = inp.get("1.0", "end-1c").strip()
            if not q:
                return
            inp.delete("1.0", "end")
            append("Anda", q)
            if state["first"]:
                messages.append({"role": "user", "content": ctx + "\n\nPertanyaan: " + q})
                state["first"] = False
            else:
                messages.append({"role": "user", "content": q})
            status.config(text="AI sedang menjawab… (model lokal bisa agak lama)")
            send_btn.config(state="disabled")

            def worker():
                try:
                    ans = ai_explain.chat(messages, cfg)
                except Exception as ex:
                    ans = f"[gagal menghubungi AI: {ex} — cek Settings > AI]"
                messages.append({"role": "assistant", "content": ans})

                def done():
                    append("AI", ans)
                    status.config(text="")
                    send_btn.config(state="normal")
                self.root.after(0, done)

            threading.Thread(target=worker, daemon=True).start()

        send_btn.config(command=do_send)
        inp.bind("<Control-Return>", lambda e: (do_send(), "break"))
        inp.focus_set()

    def _show_text_window(self, title, text):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("680x520")
        t = scrolledtext.ScrolledText(win, wrap="word", font=("Segoe UI", 10))
        t.pack(fill="both", expand=True, padx=8, pady=8)
        t.insert("1.0", text)
        win._txt = t
        return win

    def _set_text_window(self, win, text):
        try:
            win._txt.delete("1.0", "end")
            win._txt.insert("1.0", text)
        except tk.TclError:
            pass

    def _append_text_window(self, win, text):
        try:
            win._txt.insert("end", text)
            win._txt.see("end")
        except tk.TclError:
            pass

    # --- menu klik-kanan ---
    def _popup_history(self, event):
        row = self.htable.identify_row(event.y)
        if not row:
            return
        self.htable.selection_set(row)
        # menu dinamis: item tetap + submenu action plugins yang aktif
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Kirim ke Repeater", command=self._send_to_repeater)
        menu.add_command(label="Kirim ke Intruder", command=self._send_to_intruder)
        menu.add_command(label="Kirim ke JWT", command=self._send_to_jwt)
        menu.add_command(label="Jelaskan dengan AI", command=self._explain_ai)
        actions = plugins.action_plugins()
        if actions:
            sub = tk.Menu(menu, tearoff=0)
            for p in actions:
                sub.add_command(label=p.menu, command=lambda fn=p.filename: self._run_plugin_action(fn))
            menu.add_cascade(label="Kirim ke Plugin", menu=sub)
        menu.tk_popup(event.x_root, event.y_root)

    def _popup_intercept(self, event):
        idx = self.listbox.nearest(event.y)
        if idx < 0 or idx >= len(self.order):
            return
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self._ctx_flow = self.pending_by_id.get(self.order[idx])
        if self._ctx_flow:
            self.ictx.tk_popup(event.x_root, event.y_root)

    def _intercept_to_repeater(self):
        f = getattr(self, "_ctx_flow", None)
        if not f or f["kind"] != "request":
            messagebox.showinfo("Repeater", "Hanya REQUEST yang bisa dikirim ke Repeater.")
            return
        self._fill_repeater(f["method"], f["scheme"], f["host"], f["port"],
                            f["path"], f["headers"], f["body_text"])

    def _intercept_to_intruder(self):
        f = getattr(self, "_ctx_flow", None)
        if not f or f["kind"] != "request":
            messagebox.showinfo("Intruder", "Hanya REQUEST yang bisa dikirim ke Intruder.")
            return
        self._fill_intruder(f["method"], f["scheme"], f["host"], f["port"],
                            f["path"], f["headers"], f["body_text"])

    def _intercept_to_jwt(self):
        f = getattr(self, "_ctx_flow", None)
        if not f:
            return
        tokens = jwt_tool.find_in_headers(f.get("headers", []))
        if not tokens:
            messagebox.showinfo("JWT", "Tidak ada token JWT (eyJ...) di flow ini.")
            return
        self.jwt_in.delete("1.0", "end")
        self.jwt_in.insert("1.0", tokens[0])
        self.nb.select(self.tab_jwt)
        self._jwt_decode()

    # --- klik-kanan dari dalam editor (panel Headers/Body/Request asal) ---
    def _editor_to_repeater(self):
        if self.current_kind != "request" or self.current_id is None:
            messagebox.showinfo("Repeater", "Buka sebuah REQUEST di editor dulu.")
            return
        try:
            method = self.entries["method"].get()
            host = self.entries["host"].get()
            port = self.entries["port"].get()
            path = self.entries["path"].get()
        except KeyError:
            return
        scheme = (self.pending_by_id.get(self.current_id) or {}).get("scheme", "https")
        self._fill_repeater(method, scheme, host, port, path,
                            self._parse_headers(), self.body_text.get("1.0", "end-1c"))

    def _editor_to_intruder(self):
        if self.current_kind != "request" or self.current_id is None:
            messagebox.showinfo("Intruder", "Buka sebuah REQUEST di editor dulu.")
            return
        try:
            method = self.entries["method"].get()
            host = self.entries["host"].get()
            port = self.entries["port"].get()
            path = self.entries["path"].get()
        except KeyError:
            return
        scheme = (self.pending_by_id.get(self.current_id) or {}).get("scheme", "https")
        self._fill_intruder(method, scheme, host, port, path,
                            self._parse_headers(), self.body_text.get("1.0", "end-1c"))

    def _editor_to_jwt(self):
        tokens = jwt_tool.find_in_headers(self._parse_headers())
        if not tokens:
            messagebox.showinfo("JWT", "Tidak ada token JWT (eyJ...) di editor ini.")
            return
        self.jwt_in.delete("1.0", "end")
        self.jwt_in.insert("1.0", tokens[0])
        self.nb.select(self.tab_jwt)
        self._jwt_decode()

    # ------------------------------ Find (ala Burp) ------------------------------

    def _attach_find(self, parent, widget):
        """Bar cari di bawah sebuah text widget: highlight semua match + navigasi."""
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(4, 0))
        ttk.Label(bar, text="Find").pack(side="left")
        ent = ttk.Entry(bar)
        ent.pack(side="left", fill="x", expand=True, padx=4)
        lbl = ttk.Label(bar, text="", width=10, foreground="#666")
        state = {"matches": [], "idx": -1, "term": ""}
        widget.tag_config("find", background="#fff3a3")
        widget.tag_config("find_cur", background="#ffcc33")

        def search(_evt=None):
            term = ent.get()
            widget.tag_remove("find", "1.0", "end")
            widget.tag_remove("find_cur", "1.0", "end")
            state["matches"] = []
            state["idx"] = -1
            state["term"] = term
            if not term:
                lbl.config(text="")
                return
            start = "1.0"
            while True:
                pos = widget.search(term, start, stopindex="end", nocase=True)
                if not pos:
                    break
                end = f"{pos}+{len(term)}c"
                widget.tag_add("find", pos, end)
                state["matches"].append(pos)
                start = end
            if state["matches"]:
                state["idx"] = 0
                jump()
            lbl.config(text=f"{len(state['matches'])} match")

        def jump():
            if not state["matches"]:
                return
            pos = state["matches"][state["idx"]]
            end = f"{pos}+{len(state['term'])}c"
            widget.tag_remove("find_cur", "1.0", "end")
            widget.tag_add("find_cur", pos, end)
            widget.see(pos)
            lbl.config(text=f"{state['idx'] + 1}/{len(state['matches'])}")

        def nxt(_evt=None):
            if ent.get() != state["term"]:
                search()
                return
            if not state["matches"]:
                return
            state["idx"] = (state["idx"] + 1) % len(state["matches"])
            jump()

        def prev(_evt=None):
            if not state["matches"]:
                search()
                return
            state["idx"] = (state["idx"] - 1) % len(state["matches"])
            jump()

        ent.bind("<Return>", nxt)
        ent.bind("<Shift-Return>", prev)
        ttk.Button(bar, text="Find", command=search).pack(side="left")
        ttk.Button(bar, text="▲", width=3, command=prev).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="▼", width=3, command=nxt).pack(side="left")
        lbl.pack(side="left", padx=6)
        return bar

    # ------------------------------ editor (intercept) ------------------------------

    def _field(self, parent, key, label, value, width, full=False):
        col = ttk.Frame(parent)
        col.pack(side="left", fill="x", expand=full, padx=(0, 8))
        ttk.Label(col, text=label).pack(anchor="w")
        e = ttk.Entry(col, width=width)
        e.insert(0, str(value))
        e.pack(fill="x" if full else "none")
        self.entries[key] = e

    def _rebuild_fields(self, kind, ff):
        for w in self.fields_frame.winfo_children():
            w.destroy()
        self.entries = {}
        if kind == "request":
            r1 = ttk.Frame(self.fields_frame)
            r1.pack(fill="x")
            self._field(r1, "method", "Method", ff["method"], 12)
            self._field(r1, "host", "Host", ff["host"], 28)
            self._field(r1, "port", "Port", ff["port"], 6)
            r2 = ttk.Frame(self.fields_frame)
            r2.pack(fill="x")
            self._field(r2, "path", "Path", ff["path"], 80, full=True)
        else:
            r1 = ttk.Frame(self.fields_frame)
            r1.pack(fill="x")
            self._field(r1, "status_line", "Status line", ff["status_line"], 80, full=True)

    def _toggle_intercept(self):
        new = not interceptor.enabled.get("request")
        interceptor.set_enabled("request", new)
        if not new:
            interceptor.resolve_all()   # lepas semua antrean yang masih tertahan
        self._update_intercept_btn()

    def _toggle_response(self):
        on = bool(self.var_res.get())
        interceptor.set_enabled("response", on)
        if not on:
            interceptor.resolve_all()

    def _update_intercept_btn(self):
        on = interceptor.enabled.get("request")
        self.btn_intercept.config(text=t("intercept_on") if on else t("intercept_off"),
                                  style="Accent.TButton" if on else "TButton")

    def _on_select(self, _evt):
        sel = self.listbox.curselection()
        if not sel:
            return
        ff = self.pending_by_id.get(self.order[sel[0]])
        if ff:
            self._load_editor(ff)

    def _load_editor(self, ff):
        self.current_id = ff["id"]
        self.current_kind = ff["kind"]
        self.current_editable = ff["body_editable"]
        self._rebuild_fields(ff["kind"], ff)

        # tampilkan request asal kalau ini sebuah RESPONSE
        req = ff.get("request")
        if ff["kind"] == "response" and req:
            txt = req.get("line", "") + "\n" + "\n".join(f"{k}: {v}" for k, v in req.get("headers", []))
            if req.get("body_text"):
                txt += "\n\n" + req["body_text"]
            self.req_preview.config(state="normal")
            self.req_preview.delete("1.0", "end")
            self.req_preview.insert("1.0", txt)
            self.req_preview.config(state="disabled")
            self.req_preview_frame.pack(fill="both", pady=(0, 6), before=self.editor_box)
        else:
            self.req_preview_frame.pack_forget()

        self.headers_text.delete("1.0", "end")
        self.headers_text.insert("1.0", "\n".join(f"{k}: {v}" for k, v in ff["headers"]))
        self.body_text.config(state="normal")
        self.body_text.delete("1.0", "end")
        self.body_text.insert("1.0", ff["body_text"])
        if ff["body_editable"]:
            self.body_label.config(text="Body")
        else:
            self.body_text.config(state="disabled")
            self.body_label.config(text="Body (read-only / biner)")
        if ff["kind"] == "request":
            self.editor_box.config(text=f"→ REQUEST #{ff['id']} — dikirim ke server (bisa diedit)")
        else:
            self.editor_box.config(text=f"← RESPONSE #{ff['id']} — balasan server (bisa diedit)")

        self.fwd_btn.config(state="normal")
        self.drop_btn.config(state="normal")
        self.hint.config(text=f'Mengedit {ff["kind"].upper()} #{ff["id"]}')

    def _parse_headers(self):
        out = []
        for line in self.headers_text.get("1.0", "end-1c").splitlines():
            line = line.strip()
            if not line:
                continue
            i = line.find(":")
            out.append([line, ""] if i < 0 else [line[:i].strip(), line[i + 1:].strip()])
        return out

    def _forward(self):
        if self.current_id is None:
            return
        if self.current_kind == "request":
            fields = {"method": self.entries["method"].get(), "host": self.entries["host"].get(),
                      "port": self.entries["port"].get(), "path": self.entries["path"].get()}
        else:
            fields = {"status_line": self.entries["status_line"].get()}
        body_text = self.body_text.get("1.0", "end-1c") if self.current_editable else None
        interceptor.resolve(self.current_id, "forward",
                            fields=fields, headers=self._parse_headers(), body_text=body_text)
        self._clear_editor()

    def _drop(self):
        if self.current_id is None:
            return
        interceptor.resolve(self.current_id, "drop")
        self._clear_editor()

    def _clear_editor(self):
        self.current_id = None
        self.current_kind = None
        self.req_preview_frame.pack_forget()
        for w in self.fields_frame.winfo_children():
            w.destroy()
        self.entries = {}
        self.headers_text.delete("1.0", "end")
        self.body_text.config(state="normal")
        self.body_text.delete("1.0", "end")
        self.body_label.config(text="Body")
        self.editor_box.config(text="Belum ada yang dipilih")
        self.fwd_btn.config(state="disabled")
        self.drop_btn.config(state="disabled")
        self.hint.config(text="Pilih flow di kiri untuk mengedit")

    def _poll(self):
        snap = interceptor.snapshot()
        self._update_intercept_btn()
        self.var_res.set(1 if snap["enabled"]["response"] else 0)
        pend = snap["pending"]
        self.pending_by_id = {ff["id"]: ff for ff in pend}
        self.listbox.delete(0, "end")
        self.order = []
        for i, ff in enumerate(pend):
            self.order.append(ff["id"])
            if ff["kind"] == "request":
                txt = f'REQ #{ff["id"]}  {ff["method"]} {ff["scheme"]}://{ff["host"]}{ff["path"]}'
                color = ACCENT
            else:
                txt = f'RES #{ff["id"]}  {ff["status_line"]}'
                color = OK_GREEN
            self.listbox.insert("end", txt[:140])
            self.listbox.itemconfig(i, foreground=color)

        if self.current_id in self.order:
            self.listbox.selection_set(self.order.index(self.current_id))
        elif self.current_id is not None:
            self._clear_editor()

        # --- gaya Burp: auto-muat antrean pertama kalau belum ada yg dibuka ---
        if self.current_id is None and self.order:
            first = self.pending_by_id[self.order[0]]
            self._load_editor(first)
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)

        n = len(pend)
        self.st_count.config(text=f"{n} " + t("held"))
        # tombol Forward berfungsi sebagai "Next": teruskan yang ini -> yg berikut muncul
        self.fwd_btn.config(text=("Forward (Next)" if n > 1 else "Forward"))

        self._update_history()
        self.root.after(600, self._poll)


def sys_is_mac():
    import platform
    return platform.system() == "Darwin"


def _seed_plugins():
    """Saat .exe: salin plugin bawaan ke folder plugins/ di sebelah .exe (sekali)."""
    import shutil
    import paths
    dst = os.path.join(paths.BASE_DIR, "plugins")
    src = os.path.join(paths.RESOURCE_DIR, "plugins")
    try:
        os.makedirs(dst, exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(dst) and os.path.isdir(src):
            for fn in os.listdir(src):
                d = os.path.join(dst, fn)
                if fn.endswith(".py") and not os.path.exists(d):
                    shutil.copy2(os.path.join(src, fn), d)
    except Exception:
        pass


def main():
    _seed_plugins()
    ca_mod.generate_ca()
    plugins.load_all()
    cfg = config.get()
    server = proxy.ProxyServer()
    try:
        server.start(cfg["listen_host"], cfg["listen_port"])
    except OSError as e:
        print("Gagal start proxy:", e)
    root = tk.Tk()
    try:
        root.state("zoomed")            # maximize (Windows/macOS)
    except tk.TclError:
        try:
            root.attributes("-zoomed", True)   # Linux
        except tk.TclError:
            pass
    App(root, server)
    root.mainloop()


if __name__ == "__main__":
    main()
