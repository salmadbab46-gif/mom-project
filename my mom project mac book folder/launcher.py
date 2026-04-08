"""
PsychNeuro Research Bot — Launcher
Double-click START HERE.bat to open.
"""
import tkinter as tk
from tkinter import messagebox
import subprocess, sys, os, threading, time, webbrowser, socket, json, urllib.parse

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR  = os.path.join(PROJECT_DIR, "backend")
REQ_FILE     = os.path.join(BACKEND_DIR, "requirements.txt")
DASHBOARD_URL = "http://localhost:8000/app"

server_process = None
is_running = False

def port_free(port=8000):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0


class App(tk.Tk):
    BG      = "#0f1117"
    SURFACE = "#1a1d2e"
    BORDER  = "#2d3252"
    ACCENT  = "#7c6af7"
    TEAL    = "#5eead4"
    TEXT    = "#e2e8f0"
    MUTED   = "#94a3b8"
    DIM     = "#64748b"
    GREEN   = "#22c55e"
    YELLOW  = "#eab308"
    RED     = "#ef4444"

    def __init__(self):
        super().__init__()
        self.title("PsychNeuro Research Bot")
        self.geometry("560x640")
        self.resizable(False, False)
        self.configure(bg=self.BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.subjects = []
        self._build()
        self._install_deps()

    def _build(self):
        # ── HEADER ──────────────────────────────────────────────
        hdr = tk.Frame(self, bg="#1e1b4b", pady=20)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🧠", font=("Segoe UI Emoji", 40),
                 bg="#1e1b4b", fg=self.TEXT).pack()
        tk.Label(hdr, text="PsychNeuro Research Bot",
                 font=("Segoe UI", 16, "bold"),
                 bg="#1e1b4b", fg="#a78bfa").pack(pady=(4,0))
        tk.Label(hdr, text="Free  ·  No account needed  ·  Searches real scientific papers",
                 font=("Segoe UI", 8), bg="#1e1b4b", fg=self.DIM).pack(pady=(3,0))

        # ── BODY ────────────────────────────────────────────────
        body = tk.Frame(self, bg=self.BG, padx=26, pady=18)
        body.pack(fill="both", expand=True)

        # SUBJECT INPUT
        self._label(body, "🔍  What do you want to research?")
        tk.Label(body, text="Type a topic and press Enter  —  you can add multiple topics",
                 font=("Segoe UI", 8), bg=self.BG, fg=self.DIM).pack(anchor="w", pady=(0,6))

        inp_row = tk.Frame(body, bg=self.BG)
        inp_row.pack(fill="x", pady=(0,8))

        self.subj_var = tk.StringVar()
        self.subj_ent = tk.Entry(
            inp_row, textvariable=self.subj_var,
            font=("Segoe UI", 12), bg=self.SURFACE,
            fg=self.TEXT, insertbackground=self.TEXT,
            relief="flat", bd=0
        )
        self.subj_ent.pack(side="left", fill="x", expand=True, ipady=10, ipadx=12)
        self.subj_ent.bind("<Return>", lambda e: self._add())
        self.subj_ent.focus()

        tk.Button(
            inp_row, text="+ Add",
            font=("Segoe UI", 10, "bold"),
            bg=self.ACCENT, fg="white", relief="flat",
            cursor="hand2", padx=14, pady=8,
            command=self._add
        ).pack(side="right", padx=(8,0))

        # TAG DISPLAY
        self.tag_frame = tk.Frame(body, bg=self.BG, height=36)
        self.tag_frame.pack(fill="x", pady=(0,8))
        self._render_tags()

        # QUICK PRESETS
        tk.Label(body, text="Quick add:", font=("Segoe UI", 8),
                 bg=self.BG, fg=self.DIM).pack(anchor="w")
        pf = tk.Frame(body, bg=self.BG)
        pf.pack(fill="x", pady=(4,14))
        presets = [
            "neuroplasticity","memory","anxiety","dopamine",
            "sleep & brain","trauma","mindfulness","depression",
            "consciousness","cognitive bias","ADHD","stress"
        ]
        for i, p in enumerate(presets):
            tk.Button(
                pf, text=p, font=("Segoe UI", 8),
                bg=self.SURFACE, fg=self.TEAL, relief="flat",
                cursor="hand2", padx=7, pady=3,
                command=lambda t=p: self._quick(t)
            ).grid(row=i//4, column=i%4, padx=3, pady=2, sticky="w")

        # STATUS
        self._label(body, "📊  Status")
        self.status_lbl = tk.Label(
            body, text="⏳  Setting up...",
            font=("Segoe UI", 10), bg=self.BG,
            fg=self.YELLOW, wraplength=500, justify="left"
        )
        self.status_lbl.pack(anchor="w", pady=(0,12))

        # START BUTTON
        self.start_btn = tk.Button(
            body,
            text="🚀   START RESEARCH",
            font=("Segoe UI", 14, "bold"),
            bg="#6d28d9", fg="white", relief="flat",
            cursor="hand2", pady=16,
            command=self._start,
            state="disabled"
        )
        self.start_btn.pack(fill="x", pady=(0,8))

        # STOP / OPEN
        bot_row = tk.Frame(body, bg=self.BG)
        bot_row.pack(fill="x", pady=(0,6))

        self.stop_btn = tk.Button(
            bot_row, text="⏹  Stop",
            font=("Segoe UI", 9),
            bg=self.SURFACE, fg=self.MUTED,
            relief="flat", cursor="hand2",
            pady=7, command=self._stop, state="disabled"
        )
        self.stop_btn.pack(side="left", fill="x", expand=True, padx=(0,4))

        self.open_btn = tk.Button(
            bot_row, text="🌐  Open Dashboard",
            font=("Segoe UI", 9),
            bg="#1e3a5f", fg="#38bdf8",
            relief="flat", cursor="hand2",
            pady=7, command=lambda: webbrowser.open(DASHBOARD_URL),
            state="disabled"
        )
        self.open_btn.pack(side="right", fill="x", expand=True, padx=(4,0))

        # SOURCE BADGES
        sf = tk.Frame(body, bg=self.BG)
        sf.pack(pady=(14,0))
        tk.Label(sf, text="Sources: ", font=("Segoe UI",8),
                 bg=self.BG, fg=self.DIM).pack(side="left")
        for src, color in [
            ("Semantic Scholar","#7c6af7"),
            ("PubMed / NIH","#22c55e"),
            ("CrossRef","#f97316")
        ]:
            tk.Label(sf, text=f" {src} ", font=("Segoe UI",8),
                     bg=self.SURFACE, fg=color,
                     padx=5, pady=2).pack(side="left", padx=2)

    def _label(self, parent, text):
        tk.Label(parent, text=text, font=("Segoe UI",9,"bold"),
                 bg=self.BG, fg=self.MUTED).pack(anchor="w", pady=(0,4))

    # ── TAGS ───────────────────────────────────────────────────
    def _add(self):
        v = self.subj_var.get().strip()
        if v and v not in self.subjects:
            self.subjects.append(v)
            self.subj_var.set("")
            self._render_tags()

    def _quick(self, t):
        if t not in self.subjects:
            self.subjects.append(t)
            self._render_tags()

    def _remove(self, t):
        if t in self.subjects:
            self.subjects.remove(t)
            self._render_tags()

    def _render_tags(self):
        for w in self.tag_frame.winfo_children():
            w.destroy()
        if not self.subjects:
            tk.Label(self.tag_frame,
                     text="No topics yet — type one above and press Enter",
                     font=("Segoe UI",8), bg=self.BG, fg=self.DIM).pack(anchor="w")
            return
        row = tk.Frame(self.tag_frame, bg=self.BG)
        row.pack(fill="x")
        for t in self.subjects:
            pill = tk.Frame(row, bg="#2e1d6e", padx=6, pady=3)
            pill.pack(side="left", padx=3, pady=2)
            tk.Label(pill, text=t, font=("Segoe UI",9),
                     bg="#2e1d6e", fg="#a78bfa").pack(side="left")
            tk.Button(pill, text="×", font=("Segoe UI",9,"bold"),
                      bg="#2e1d6e", fg=self.RED, relief="flat",
                      cursor="hand2", padx=2,
                      command=lambda s=t: self._remove(s)).pack(side="right")

    # ── DEPS ───────────────────────────────────────────────────
    def _install_deps(self):
        def run():
            try:
                subprocess.run(
                    [sys.executable,"-m","pip","install","-r",REQ_FILE,"-q"],
                    capture_output=True, timeout=120
                )
            except Exception:
                pass
            self.after(0, self._ready)
        threading.Thread(target=run, daemon=True).start()

    def _ready(self):
        self.status_lbl.config(
            text="✅  Ready!  Add your research topics above then click START RESEARCH",
            fg=self.GREEN
        )
        self.start_btn.config(state="normal")

    # ── START / STOP ────────────────────────────────────────────
    def _start(self):
        global server_process, is_running

        if not self.subjects:
            messagebox.showwarning("No Topics",
                "Please add at least one research topic first.")
            self.subj_ent.focus()
            return

        if not port_free(8000):
            # Already running — just open browser with subjects
            self._open_with_subjects()
            return

        self.start_btn.config(state="disabled", text="⏳  Starting…")
        self.status_lbl.config(text="🔄  Starting research engine…", fg=self.ACCENT)

        def run():
            global server_process, is_running
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            server_process = subprocess.Popen(
                [sys.executable, "main.py"],
                cwd=BACKEND_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags
            )
            is_running = True
            for _ in range(24):          # wait up to 12 s
                time.sleep(0.5)
                if not port_free(8000):
                    break
            self.after(0, self._server_up)

        threading.Thread(target=run, daemon=True).start()

    def _server_up(self):
        self.status_lbl.config(
            text=f"🟢  Running!  Researching: {', '.join(self.subjects)}",
            fg=self.GREEN
        )
        self.start_btn.config(text="🚀   START RESEARCH", state="normal")
        self.stop_btn.config(state="normal")
        self.open_btn.config(state="normal")
        self._open_with_subjects()

    def _open_with_subjects(self):
        param = urllib.parse.quote(json.dumps(self.subjects))
        webbrowser.open(f"{DASHBOARD_URL}?subjects={param}")

    def _stop(self):
        global server_process, is_running
        if server_process:
            server_process.terminate()
            server_process = None
        is_running = False
        self.status_lbl.config(text="⏹  Stopped.", fg=self.MUTED)
        self.start_btn.config(state="normal", text="🚀   START RESEARCH")
        self.stop_btn.config(state="disabled")
        self.open_btn.config(state="disabled")

    def _on_close(self):
        if is_running:
            if messagebox.askyesno("Close", "Stop the bot and close?"):
                self._stop()
                self.destroy()
        else:
            self.destroy()


if __name__ == "__main__":
    App().mainloop()
