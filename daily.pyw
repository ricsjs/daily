"""Daily — agenda e lista de tarefas leve, com widget na área de trabalho.

Sem dependências externas (só a biblioteca padrão do Python).
Os dados ficam em dados.txt (JSON legível), na mesma pasta deste arquivo.

Uso:
    pythonw daily.pyw            abre o widget e a janela principal
    pythonw daily.pyw --startup  abre só o widget (usado ao ligar o PC)
"""

import ctypes
import datetime as dt
import json
import os
import queue
import re
import shutil
import socket
import sys
import threading
import uuid
import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog

try:
    import winreg
except ImportError:  # fora do Windows
    winreg = None

APP_NOME = "Daily"
EMPACOTADO = getattr(sys, "frozen", False)  # rodando como .exe (PyInstaller)


def _pasta_dados():
    """Ao lado do script/.exe; se a pasta não aceitar escrita, usa %APPDATA%\\Daily."""
    base = os.path.dirname(sys.executable if EMPACOTADO else os.path.abspath(__file__))
    if os.access(base, os.W_OK):
        return base
    alt = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NOME)
    os.makedirs(alt, exist_ok=True)
    return alt


APP_DIR = _pasta_dados()
ARQUIVO_DADOS = os.path.join(APP_DIR, "dados.txt")
PORTA = int(os.environ.get("DAILY_PORTA", 47613))  # garante uma única instância
CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"

# Sob pythonw não existe console: erros vão para erros.log
class _LogPreguicoso:
    """Só cria o erros.log quando algo é escrito de fato."""

    def __init__(self, caminho):
        self.caminho = caminho

    def write(self, txt):
        try:
            with open(self.caminho, "a", encoding="utf-8") as f:
                f.write(txt)
        except OSError:
            pass
        return len(txt)

    def flush(self):
        pass


if sys.stderr is None:
    sys.stderr = _LogPreguicoso(os.path.join(APP_DIR, "erros.log"))

FONTE = "Segoe UI"
COR = {
    "bg": "#f1f5fb",
    "card": "#ffffff",
    "borda": "#dfe7f3",
    "primaria": "#2563eb",
    "primaria_hover": "#1d4ed8",
    "clara": "#eaf1fe",
    "clara_hover": "#dbe7fd",
    "selecao": "#eef4ff",
    "texto": "#0f172a",
    "suave": "#64748b",
    "fraco": "#94a3b8",
    "perigo": "#dc2626",
    "fora_mes": "#f8fafc",
    "seg": "#e3ebf8",
    "hover": "#f1f5f9",
    "sucesso": "#10b981",
}
PALETA = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
          "#ec4899", "#14b8a6", "#6366f1", "#84cc16", "#f97316"]
CATEGORIAS_PADRAO = [
    {"nome": "Trabalho", "cor": "#3b82f6"},
    {"nome": "Estudo", "cor": "#8b5cf6"},
    {"nome": "Pessoal", "cor": "#10b981"},
    {"nome": "Saúde", "cor": "#f59e0b"},
]

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun",
                "jul", "ago", "set", "out", "nov", "dez"]
DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
               "Sexta-feira", "Sábado", "Domingo"]
DIAS_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
CAB_CALENDARIO = ["D", "S", "T", "Q", "Q", "S", "S"]  # começa no domingo

ESCALA = 1.0


def S(n):
    """Converte pixels de projeto (96 dpi) para a escala real da tela."""
    return int(round(n * ESCALA))


# ---------------------------------------------------------------- utilidades

def hoje():
    return dt.date.today()


def data_curta(d):
    return f"{d.day:02d} {MESES_CURTOS[d.month - 1]}"


def data_extensa(d):
    return f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1].lower()}"


def data_rotulo(d):
    delta = (d - hoje()).days
    if delta == 0:
        return "Hoje"
    if delta == 1:
        return "Amanhã"
    if delta == -1:
        return "Ontem"
    s = f"{DIAS_CURTOS[d.weekday()]}, {data_curta(d)}"
    if d.year != hoje().year:
        s += f" {d.year}"
    return s


def ler_data_br(txt):
    txt = txt.strip()
    if not txt:
        return ""
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2}|\d{4}))?", txt)
    if not m:
        raise ValueError
    ano = m[3]
    ano = hoje().year if ano is None else (2000 + int(ano) if len(ano) == 2 else int(ano))
    return dt.date(ano, int(m[2]), int(m[1])).isoformat()


def ler_hora(txt):
    txt = txt.strip()
    if not txt:
        return ""
    m = re.fullmatch(r"(\d{1,2})(?:[:h.]?(\d{2}))?", txt)
    if not m:
        raise ValueError
    h, mi = int(m[1]), int(m[2] or 0)
    if h > 23 or mi > 59:
        raise ValueError
    return f"{h:02d}:{mi:02d}"


def misturar(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def encurtar(txt, n):
    return txt if len(txt) <= n else txt[:max(1, n - 1)].rstrip() + "…"


def chave_ordem(t):
    return (t.get("data") or "9999-99-99", t.get("hora") or "99:99", t["titulo"].lower())


def ligar_clique(widget, funcao, evento="<Button-1>"):
    """Liga o evento ao widget e a todos os descendentes."""
    widget.bind(evento, funcao)
    for filho in widget.winfo_children():
        ligar_clique(filho, funcao, evento)


# ------------------------------------------------------- iniciar com o Windows

def comando_autostart():
    if EMPACOTADO:
        return f'"{sys.executable}" --startup'
    exe = sys.executable
    pasta, nome = os.path.split(exe)
    if nome.lower() == "python.exe":
        w = os.path.join(pasta, "pythonw.exe")
        if os.path.exists(w):
            exe = w
    return f'"{exe}" "{os.path.abspath(__file__)}" --startup'


def autostart_ativo():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN) as k:
            winreg.QueryValueEx(k, APP_NOME)
            return True
    except OSError:
        return False


def definir_autostart(ativar):
    if winreg is None:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
        if ativar:
            winreg.SetValueEx(k, APP_NOME, 0, winreg.REG_SZ, comando_autostart())
        else:
            try:
                winreg.DeleteValue(k, APP_NOME)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------- dados (txt)

class Store:
    def __init__(self, caminho):
        self.caminho = caminho
        self.ouvintes = []
        self._mtime = None
        self.dados = {"categorias": [dict(c) for c in CATEGORIAS_PADRAO],
                      "tarefas": [], "config": {}}
        if os.path.exists(caminho):
            if not self._ler():
                try:
                    shutil.copy(caminho, caminho + ".corrompido")
                except OSError:
                    pass
                self.salvar(notificar=False)
        else:
            self.salvar(notificar=False)

    def _ler(self):
        try:
            with open(self.caminho, encoding="utf-8") as f:
                d = json.load(f)
            for k in ("categorias", "tarefas", "config"):
                if k in d:
                    self.dados[k] = d[k]
            self._mtime = os.path.getmtime(self.caminho)
            return True
        except (OSError, ValueError, TypeError):
            return False

    @property
    def tarefas(self):
        return self.dados["tarefas"]

    @property
    def categorias(self):
        return self.dados["categorias"]

    @property
    def config(self):
        return self.dados["config"]

    def salvar(self, notificar=True):
        tmp = self.caminho + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.dados, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.caminho)
        self._mtime = os.path.getmtime(self.caminho)
        if notificar:
            self.notificar()

    def notificar(self):
        for fn in list(self.ouvintes):
            try:
                fn()
            except tk.TclError:
                pass

    def verificar_externo(self):
        """Recarrega se o dados.txt foi editado fora do app."""
        try:
            m = os.path.getmtime(self.caminho)
        except OSError:
            return
        if m != self._mtime:
            self._mtime = m
            if self._ler():
                self.notificar()

    # tarefas
    def obter(self, tid):
        return next((t for t in self.tarefas if t["id"] == tid), None)

    def nova(self, **campos):
        t = {"id": uuid.uuid4().hex[:12], "titulo": "", "data": "", "hora": "",
             "categoria": "", "nota": "", "status": "aberta",
             "criada": dt.datetime.now().isoformat(timespec="seconds")}
        t.update(campos)
        self.tarefas.append(t)
        self.salvar()
        return t

    def atualizar(self, tid, **campos):
        t = self.obter(tid)
        if t:
            t.update(campos)
            self.salvar()

    def remover(self, tid):
        self.dados["tarefas"] = [t for t in self.tarefas if t["id"] != tid]
        self.salvar()

    def alternar(self, tid):
        t = self.obter(tid)
        if t:
            self.atualizar(tid, status="concluida" if t["status"] == "aberta" else "aberta")

    def alternar_cancelada(self, tid):
        t = self.obter(tid)
        if t:
            self.atualizar(tid, status="aberta" if t["status"] == "cancelada" else "cancelada")

    def por_data(self):
        idx = {}
        for t in sorted(self.tarefas, key=chave_ordem):
            if t.get("data"):
                idx.setdefault(t["data"], []).append(t)
        return idx

    # categorias
    def cor(self, nome):
        for c in self.categorias:
            if c["nome"] == nome:
                return c["cor"]
        return COR["fraco"]

    def renomear_categoria(self, antigo, novo):
        for c in self.categorias:
            if c["nome"] == antigo:
                c["nome"] = novo
        for t in self.tarefas:
            if t.get("categoria") == antigo:
                t["categoria"] = novo
        self.salvar()


# ------------------------------------------------------------- componentes UI

class Botao(tk.Label):
    """Botão plano feito com Label (fica bem mais bonito que o tk.Button)."""

    def __init__(self, master, texto, comando=None, bg=None, fg="white", hover=None,
                 fonte=(FONTE, 10, "bold"), padx=14, pady=6, **kw):
        bg = bg or COR["primaria"]
        if hover is None and bg == COR["primaria"]:
            hover = COR["primaria_hover"]
        super().__init__(master, text=texto, font=fonte, padx=S(padx), pady=S(pady),
                         cursor="hand2", **kw)
        self.comando = comando
        self.cores(bg, fg, hover)
        self.bind("<Enter>", lambda e: self.configure(bg=self._hover))
        self.bind("<Leave>", lambda e: self.configure(bg=self._bg))
        self.bind("<ButtonRelease-1>", self._clique)

    def cores(self, bg, fg, hover=None):
        self._bg, self._hover = bg, hover or bg
        self.configure(bg=bg, fg=fg)

    def _clique(self, e):
        if self.comando and 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height():
            self.comando()


def chip(master, texto, cor, ativo, comando, fonte=(FONTE, 9, "bold")):
    b = Botao(master, texto, comando,
              bg=cor if ativo else COR["card"], fg="white" if ativo else cor,
              hover=cor if ativo else misturar(cor, "#ffffff", 0.88),
              fonte=fonte, padx=12, pady=3)
    b.configure(highlightthickness=1, highlightbackground=cor)
    return b


class Check(tk.Canvas):
    """Círculo de marcar/desmarcar."""

    def __init__(self, master, status, cor, comando, tam=22, bg=None):
        s = S(tam)
        bg = bg or COR["card"]
        super().__init__(master, width=s, height=s, bg=bg, highlightthickness=0, cursor="hand2")
        p = S(2)
        if status == "concluida":
            self.create_oval(p, p, s - p, s - p, fill=cor, outline=cor)
            self.create_line(s * .28, s * .52, s * .44, s * .68, s * .73, s * .36,
                             fill="white", width=max(2, S(2)), capstyle="round", joinstyle="round")
        elif status == "cancelada":
            self.create_oval(p, p, s - p, s - p, fill="#cbd5e1", outline="#cbd5e1")
            self.create_line(s * .32, s * .5, s * .68, s * .5, fill="white", width=max(2, S(2)))
        else:
            self.create_oval(p, p, s - p, s - p, outline=cor, width=max(2, S(2)), fill=bg)
        self.bind("<Button-1>", lambda e: comando())


class Entrada(tk.Entry):
    """Entry com texto de dica (placeholder)."""

    def __init__(self, master, dica="", **kw):
        kw.setdefault("font", (FONTE, 11))
        super().__init__(master, relief="flat", bg=COR["card"], fg=COR["texto"],
                         highlightthickness=1, highlightbackground=COR["borda"],
                         highlightcolor=COR["primaria"], insertbackground=COR["texto"], **kw)
        self.dica = dica
        self._com_dica = False
        self.bind("<FocusIn>", lambda e: self._tirar_dica())
        self.bind("<FocusOut>", lambda e: self._por_dica())
        self._por_dica()

    def _por_dica(self):
        if not self.get() and self.dica:
            self.insert(0, self.dica)
            self.configure(fg=COR["fraco"])
            self._com_dica = True

    def _tirar_dica(self):
        if self._com_dica:
            self.delete(0, "end")
            self.configure(fg=COR["texto"])
            self._com_dica = False

    def valor(self):
        return "" if self._com_dica else self.get()

    def definir(self, v):
        self._tirar_dica()
        self.delete(0, "end")
        self.insert(0, v)
        if not v and self.focus_get() is not self:
            self._por_dica()


class ScrollFrame(tk.Frame):
    def __init__(self, master, bg):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=S(16))
        self.barra = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.interior = tk.Frame(self.canvas, bg=bg)
        self._janela = self.canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self.canvas.configure(yscrollcommand=self.barra.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self._barra_visivel = False
        self.interior.bind("<Configure>", self._ajustar)
        self.canvas.bind("<Configure>", self._redimensionar)

    def _redimensionar(self, e):
        self.canvas.itemconfigure(self._janela, width=e.width)
        self._ajustar()

    def _ajustar(self, _e=None):
        alt = self.interior.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), alt))
        precisa = alt > self.canvas.winfo_height() > 1
        if precisa != self._barra_visivel:
            self._barra_visivel = precisa
            if precisa:
                self.barra.pack(side="right", fill="y", before=self.canvas)
            else:
                self.barra.pack_forget()
                self.canvas.yview_moveto(0)

    def rolar(self, e):
        if self._barra_visivel:
            passos = -3 if e.delta > 0 else 3
            self.canvas.yview_scroll(passos, "units")

    def limpar(self):
        for w in self.interior.winfo_children():
            w.destroy()

    def topo(self):
        self.canvas.yview_moveto(0)


def criar_icone(root):
    n = 32
    img = tk.PhotoImage(master=root, width=n, height=n)
    azul, escuro = COR["primaria"], "#1e40af"
    img.put(azul, to=(2, 5, 30, 30))
    img.put(escuro, to=(2, 5, 30, 12))
    img.put(escuro, to=(8, 1, 11, 8))
    img.put(escuro, to=(21, 1, 24, 8))
    img.put("#ffffff", to=(6, 14, 26, 27))
    for i in range(5):  # traço descendente do ✓
        img.put(azul, to=(9 + i, 19 + i, 12 + i, 21 + i))
    for i in range(9):  # traço ascendente do ✓
        img.put(azul, to=(13 + i, 23 - i, 16 + i, 25 - i))
    return img


# ------------------------------------------------------------- cartão tarefa

class CartaoTarefa(tk.Frame):
    def __init__(self, master, app, t, mostrar_data=True):
        card = COR["card"]
        super().__init__(master, bg=card, highlightthickness=1, highlightbackground=COR["borda"],
                         padx=S(12), pady=S(8))
        store = app.store
        cor = store.cor(t.get("categoria", ""))
        feito = t["status"] != "aberta"

        Check(self, t["status"], cor, lambda: store.alternar(t["id"]), bg=card) \
            .pack(side="left", anchor="n", padx=(0, S(10)), pady=(S(2), 0))

        acoes = tk.Frame(self, bg=card)
        acoes.pack(side="right", anchor="n")
        Botao(acoes, "⊘", lambda: store.alternar_cancelada(t["id"]), bg=card, fg=COR["fraco"],
              hover=COR["hover"], fonte=(FONTE, 12), padx=6, pady=0).pack(side="left")
        Botao(acoes, "✕", lambda: self._excluir(app, t), bg=card, fg=COR["fraco"],
              hover="#fef2f2", fonte=(FONTE, 11), padx=6, pady=0).pack(side="left")

        meio = tk.Frame(self, bg=card)
        meio.pack(side="left", fill="x", expand=True)
        titulo = tk.Label(meio, text=t["titulo"], bg=card, anchor="w", justify="left",
                          font=(FONTE, 11, "bold overstrike" if feito else "bold"),
                          fg=COR["suave"] if feito else COR["texto"])
        titulo.pack(fill="x")

        meta = tk.Frame(meio, bg=card)
        meta.pack(fill="x")
        partes = []
        if mostrar_data and t.get("data"):
            partes.append(data_curta(dt.date.fromisoformat(t["data"])))
        if t.get("hora"):
            partes.append(t["hora"])
        if partes:
            tk.Label(meta, text="   ".join(partes), bg=card, fg=COR["suave"],
                     font=(FONTE, 9)).pack(side="left")
        if t.get("categoria"):
            tk.Label(meta, text=f"● {t['categoria']}", bg=card, fg=cor,
                     font=(FONTE, 9, "bold")).pack(side="left", padx=(S(8) if partes else 0, 0))
        if t["status"] == "cancelada":
            tk.Label(meta, text="cancelada", bg=card, fg=COR["fraco"],
                     font=(FONTE, 9, "italic")).pack(side="left", padx=(S(8), 0))
        rotulos = [titulo]
        if t.get("nota"):
            nota = tk.Label(meio, text=t["nota"], bg=card, fg=COR["suave"], font=(FONTE, 9),
                            anchor="w", justify="left")
            nota.pack(fill="x")
            rotulos.append(nota)

        def ajustar(e):
            for r in rotulos:
                r.configure(wraplength=max(50, e.width - 4))
        meio.bind("<Configure>", ajustar)
        ligar_clique(meio, lambda e: app.editar(t))
        for w in [meio] + rotulos:
            w.configure(cursor="hand2")

    def _excluir(self, app, t):
        if messagebox.askyesno("Excluir tarefa", f'Excluir "{t["titulo"]}"?',
                               parent=self.winfo_toplevel()):
            app.store.remover(t["id"])


# ---------------------------------------------------------------- vista agenda

class VistaAgenda(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=COR["bg"])
        self.app = app
        h = hoje()
        self.ano, self.mes, self.sel = h.year, h.month, h
        self._agendado = None

        topo = tk.Frame(self, bg=COR["bg"])
        topo.pack(fill="x", padx=S(24), pady=(S(16), S(10)))
        nav = dict(bg=COR["card"], fg=COR["texto"], hover=COR["clara"], fonte=(FONTE, 13, "bold"),
                   padx=10, pady=0)
        Botao(topo, "‹", lambda: self._mudar_mes(-1), **nav).pack(side="left")
        Botao(topo, "›", lambda: self._mudar_mes(1), **nav).pack(side="left", padx=(S(4), S(12)))
        self.l_mes = tk.Label(topo, bg=COR["bg"], fg=COR["texto"], font=(FONTE, 18, "bold"))
        self.l_mes.pack(side="left")
        Botao(topo, "Hoje", self._ir_hoje, bg=COR["clara"], fg=COR["primaria"],
              hover=COR["clara_hover"], fonte=(FONTE, 9, "bold"), padx=12, pady=3) \
            .pack(side="left", padx=S(14))
        self.legenda = tk.Frame(topo, bg=COR["bg"])
        self.legenda.pack(side="right")

        corpo = tk.Frame(self, bg=COR["bg"])
        corpo.pack(fill="both", expand=True, padx=S(24), pady=(0, S(20)))

        self.painel = tk.Frame(corpo, bg=COR["card"], width=S(310),
                               highlightthickness=1, highlightbackground=COR["borda"])
        self.painel.pack(side="right", fill="y", padx=(S(16), 0))
        self.painel.pack_propagate(False)

        self.grade = tk.Frame(corpo, bg=COR["borda"], highlightthickness=1,
                              highlightbackground=COR["borda"])
        self.grade.pack(side="left", fill="both", expand=True)
        for c, nome in enumerate(CAB_CALENDARIO):
            tk.Label(self.grade, text=nome, bg=COR["fora_mes"], fg=COR["suave"],
                     font=(FONTE, 9, "bold"), pady=S(6)) \
                .grid(row=0, column=c, sticky="nsew", padx=(0 if c == 0 else 1, 0))
            self.grade.columnconfigure(c, weight=1, uniform="col")
        self.celulas = []
        for r in range(6):
            self.grade.rowconfigure(r + 1, weight=1, uniform="lin")
            for c in range(7):
                i = r * 7 + c
                cel = tk.Frame(self.grade, bg=COR["card"], width=S(90), height=S(80), cursor="hand2")
                cel.grid(row=r + 1, column=c, sticky="nsew", padx=(0 if c == 0 else 1, 0), pady=(1, 0))
                cel.pack_propagate(False)
                num = tk.Label(cel, bg=COR["card"], font=(FONTE, 10), padx=S(5))
                num.pack(anchor="n", pady=(S(4), S(2)))
                chips = tk.Frame(cel, bg=COR["card"])
                chips.pack(fill="both", expand=True, padx=S(4))
                for w in (cel, num, chips):
                    w.bind("<Button-1>", lambda e, i=i: self._clicar(i))
                    w.bind("<Double-Button-1>", lambda e, i=i: self._novo(i))
                self.celulas.append({"frame": cel, "num": num, "chips": chips, "data": None})
        self.grade.bind("<Configure>", lambda e: self._agendar())

    def _agendar(self):
        if self._agendado:
            self.after_cancel(self._agendado)
        self._agendado = self.after(80, self._render_celulas)

    def _mudar_mes(self, delta):
        m = self.mes - 1 + delta
        self.ano, self.mes = self.ano + m // 12, m % 12 + 1
        self.atualizar()

    def _ir_hoje(self):
        h = hoje()
        self.ano, self.mes, self.sel = h.year, h.month, h
        self.atualizar()

    def _clicar(self, i):
        d = self.celulas[i]["data"]
        self.ano, self.mes, self.sel = d.year, d.month, d
        self.atualizar()

    def _novo(self, i):
        self.app.nova_tarefa(self.celulas[i]["data"])

    def atualizar(self):
        self.l_mes.configure(text=f"{MESES[self.mes - 1]} {self.ano}")
        for w in self.legenda.winfo_children():
            w.destroy()
        for c in self.app.store.categorias:
            tk.Label(self.legenda, text=f"● {c['nome']}", bg=COR["bg"], fg=c["cor"],
                     font=(FONTE, 9, "bold")).pack(side="left", padx=(S(10), 0))
        self._render_celulas()
        self._render_painel()

    def _render_celulas(self):
        self._agendado = None
        store = self.app.store
        idx = store.por_data()
        primeiro = dt.date(self.ano, self.mes, 1)
        inicio = primeiro - dt.timedelta(days=(primeiro.weekday() + 1) % 7)
        h = hoje()
        larg = self.celulas[0]["frame"].winfo_width()
        alt = self.celulas[0]["frame"].winfo_height()
        max_chars = max(3, int((larg - S(16)) / S(6.5))) if larg > 20 else 12
        max_chips = max(1, (alt - S(28)) // S(21)) if alt > 20 else 3

        for i, cel in enumerate(self.celulas):
            d = inicio + dt.timedelta(days=i)
            cel["data"] = d
            no_mes = d.month == self.mes
            bg = COR["selecao"] if d == self.sel else (COR["card"] if no_mes else COR["fora_mes"])
            cel["frame"].configure(bg=bg)
            cel["chips"].configure(bg=bg)
            if d == h:
                cel["num"].configure(text=d.day, bg=COR["primaria"], fg="white",
                                     font=(FONTE, 10, "bold"))
            else:
                cel["num"].configure(text=d.day, bg=bg, font=(FONTE, 10),
                                     fg=COR["texto"] if no_mes else COR["fraco"])
            for w in cel["chips"].winfo_children():
                w.destroy()
            ts = idx.get(d.isoformat(), [])
            mostrar = ts if len(ts) <= max_chips else ts[:max_chips - 1]
            for t in mostrar:
                cor = store.cor(t.get("categoria", ""))
                if t["status"] == "concluida":
                    cbg, cfg, fonte = misturar(cor, "#ffffff", .6), misturar(cor, "#000000", .35), (FONTE, 8, "overstrike")
                elif t["status"] == "cancelada":
                    cbg, cfg, fonte = "#e2e8f0", COR["fraco"], (FONTE, 8, "overstrike")
                else:
                    cbg, cfg, fonte = cor, "white", (FONTE, 8, "bold")
                lb = tk.Label(cel["chips"], text=encurtar(t["titulo"], max_chars), bg=cbg, fg=cfg,
                              font=fonte, anchor="w", padx=S(4), cursor="hand2")
                lb.pack(fill="x", pady=(0, S(2)))
                lb.bind("<Button-1>", lambda e, t=t: self.app.editar(t))
            resto = len(ts) - len(mostrar)
            if resto:
                mais = tk.Label(cel["chips"], text=f"+{resto}", bg=bg, fg=COR["suave"],
                                font=(FONTE, 8, "bold"), anchor="w")
                mais.pack(fill="x")
                mais.bind("<Button-1>", lambda e, i=i: self._clicar(i))

    def _render_painel(self):
        p = self.painel
        for w in p.winfo_children():
            w.destroy()
        card = COR["card"]
        ts = self.app.store.por_data().get(self.sel.isoformat(), [])
        tk.Label(p, text=data_extensa(self.sel), bg=card, fg=COR["texto"], font=(FONTE, 13, "bold"),
                 anchor="w", justify="left", wraplength=S(270)) \
            .pack(fill="x", padx=S(16), pady=(S(16), 0))
        feitas = sum(t["status"] == "concluida" for t in ts)
        resumo = "Nenhuma tarefa" if not ts else \
            f"{len(ts)} tarefa{'s' if len(ts) > 1 else ''} · {feitas} concluída{'s' if feitas != 1 else ''}"
        tk.Label(p, text=resumo, bg=card, fg=COR["suave"], font=(FONTE, 9), anchor="w") \
            .pack(fill="x", padx=S(16))
        Botao(p, "+  Adicionar tarefa", lambda: self.app.nova_tarefa(self.sel)) \
            .pack(fill="x", padx=S(16), pady=(S(12), S(10)))
        lista = ScrollFrame(p, card)
        lista.pack(fill="both", expand=True, padx=(S(12), S(4)), pady=(0, S(12)))
        if not ts:
            tk.Label(lista.interior, text="Clique duas vezes em um dia\npara adicionar rapidamente.",
                     bg=card, fg=COR["fraco"], font=(FONTE, 9), justify="center") \
                .pack(pady=S(30))
        for t in ts:
            CartaoTarefa(lista.interior, self.app, t, mostrar_data=False) \
                .pack(fill="x", pady=S(3), padx=(0, S(4)))


# --------------------------------------------------------------- vista tarefas

class VistaTarefas(tk.Frame):
    FILTROS = [("todas", "Todas"), ("aberta", "Em aberto"),
               ("concluida", "Concluídas"), ("cancelada", "Canceladas")]

    def __init__(self, master, app):
        super().__init__(master, bg=COR["bg"])
        self.app = app
        self.filtro = "aberta"
        self.categoria = None
        self._agendado = None

        self.busca = Entrada(self, dica="Buscar tarefa…", font=(FONTE, 11))
        self.busca.pack(fill="x", padx=S(24), pady=(S(18), S(10)), ipady=S(7))
        self.busca.bind("<KeyRelease>", lambda e: self._agendar())

        seg = tk.Frame(self, bg=COR["seg"])
        seg.pack(fill="x", padx=S(24))
        self.botoes_filtro = {}
        for chave, _nome in self.FILTROS:
            b = Botao(seg, "", lambda c=chave: self._set_filtro(c), fonte=(FONTE, 9, "bold"), pady=4)
            b.pack(side="left", expand=True, fill="x", padx=S(3), pady=S(3))
            self.botoes_filtro[chave] = b

        self.f_cats = tk.Frame(self, bg=COR["bg"])
        self.f_cats.pack(fill="x", padx=S(24), pady=S(10))

        self.lista = ScrollFrame(self, COR["bg"])
        self.lista.pack(fill="both", expand=True, padx=(S(24), S(8)), pady=(0, S(12)))

    def _agendar(self):
        if self._agendado:
            self.after_cancel(self._agendado)
        self._agendado = self.after(200, lambda: self.atualizar(topo=True))

    def _set_filtro(self, chave):
        self.filtro = chave
        self.atualizar(topo=True)

    def _set_categoria(self, nome):
        self.categoria = nome
        self.atualizar(topo=True)

    def atualizar(self, topo=False):
        self._agendado = None
        store = self.app.store
        todas = store.tarefas
        cont = {"todas": len(todas)}
        for t in todas:
            cont[t["status"]] = cont.get(t["status"], 0) + 1
        for chave, nome in self.FILTROS:
            ativo = chave == self.filtro
            self.botoes_filtro[chave].configure(text=f"{nome}\n{cont.get(chave, 0)}")
            self.botoes_filtro[chave].cores(COR["card"] if ativo else COR["seg"],
                                            COR["primaria"] if ativo else COR["suave"],
                                            COR["card"] if ativo else "#d6e1f3")

        for w in self.f_cats.winfo_children():
            w.destroy()
        nomes = [c["nome"] for c in store.categorias]
        if self.categoria not in nomes:
            self.categoria = None
        chip(self.f_cats, "Todas as categorias", COR["primaria"], self.categoria is None,
             lambda: self._set_categoria(None)).pack(side="left", padx=(0, S(6)))
        for c in store.categorias:
            chip(self.f_cats, c["nome"], c["cor"], self.categoria == c["nome"],
                 lambda n=c["nome"]: self._set_categoria(n)).pack(side="left", padx=(0, S(6)))

        termo = self.busca.valor().strip().casefold()
        ts = [t for t in todas
              if (self.filtro == "todas" or t["status"] == self.filtro)
              and (self.categoria is None or t.get("categoria") == self.categoria)
              and (not termo or termo in t["titulo"].casefold() or termo in t.get("nota", "").casefold())]
        ts.sort(key=chave_ordem, reverse=self.filtro in ("concluida", "cancelada"))

        self.lista.limpar()
        if not ts:
            tk.Label(self.lista.interior, text="Nenhuma tarefa por aqui.", bg=COR["bg"],
                     fg=COR["fraco"], font=(FONTE, 11)).pack(pady=S(40))
        grupo_atual = object()
        h = hoje().isoformat()
        for t in ts:
            grupo = t.get("data") or ""
            if grupo != grupo_atual:
                grupo_atual = grupo
                if grupo:
                    texto = data_rotulo(dt.date.fromisoformat(grupo))
                    atrasado = grupo < h and t["status"] == "aberta"
                    cor = COR["perigo"] if atrasado else (COR["primaria"] if grupo == h else COR["suave"])
                else:
                    texto, cor = "Sem data", COR["suave"]
                tk.Label(self.lista.interior, text=texto.upper(), bg=COR["bg"], fg=cor,
                         font=(FONTE, 9, "bold"), anchor="w") \
                    .pack(fill="x", pady=(S(12), S(4)))
            CartaoTarefa(self.lista.interior, self.app, t, mostrar_data=False) \
                .pack(fill="x", pady=S(3), padx=(0, S(8)))
        if topo:
            self.lista.topo()


# -------------------------------------------------------------------- diálogos

def posicionar(janela, master):
    janela.update_idletasks()
    w, h = janela.winfo_reqwidth(), janela.winfo_reqheight()
    if master is not None and master.winfo_viewable():
        x = master.winfo_rootx() + (master.winfo_width() - w) // 2
        y = master.winfo_rooty() + (master.winfo_height() - h) // 3
    else:
        x = (janela.winfo_screenwidth() - w) // 2
        y = (janela.winfo_screenheight() - h) // 3
    janela.geometry(f"+{max(0, x)}+{max(0, y)}")


def trazer_para_frente(janela):
    janela.deiconify()
    janela.lift()
    janela.attributes("-topmost", True)
    janela.after(250, lambda: janela.winfo_exists() and janela.attributes("-topmost", False))
    janela.focus_force()


class DialogoTarefa(tk.Toplevel):
    STATUS = [("aberta", "Em aberto", COR["primaria"]),
              ("concluida", "Concluída", COR["sucesso"]),
              ("cancelada", "Cancelada", COR["fraco"])]

    def __init__(self, app, tarefa=None, data=None):
        janela = app.janela if app.janela is not None and app.janela.winfo_exists() else None
        super().__init__(janela or app.root)
        self.app, self.t = app, tarefa
        self.title("Editar tarefa" if tarefa else "Nova tarefa")
        self.configure(bg=COR["card"])
        self.resizable(False, False)
        if janela is not None and janela.winfo_viewable():
            self.transient(janela)

        card = COR["card"]
        c = tk.Frame(self, bg=card, padx=S(24), pady=S(18))
        c.pack(fill="both", expand=True)
        tk.Label(c, text="Editar tarefa" if tarefa else "Nova tarefa", bg=card, fg=COR["texto"],
                 font=(FONTE, 15, "bold"), anchor="w").pack(fill="x")

        self._rotulo(c, "TÍTULO")
        self.e_titulo = Entrada(c, "O que precisa ser feito?", width=44)
        self.e_titulo.pack(fill="x", ipady=S(5))

        linha = tk.Frame(c, bg=card)
        linha.pack(fill="x")
        col1 = tk.Frame(linha, bg=card)
        col1.pack(side="left", fill="x", expand=True)
        self._rotulo(col1, "DATA")
        f = tk.Frame(col1, bg=card)
        f.pack(fill="x")
        self.e_data = Entrada(f, "dd/mm/aaaa", width=11)
        self.e_data.pack(side="left", ipady=S(5))
        for nome, v in (("Hoje", 0), ("Amanhã", 1), ("Sem data", None)):
            Botao(f, nome, lambda v=v: self._por_data(v), bg=COR["clara"], fg=COR["primaria"],
                  hover=COR["clara_hover"], fonte=(FONTE, 9, "bold"), padx=8, pady=3) \
                .pack(side="left", padx=(S(6), 0))
        col2 = tk.Frame(linha, bg=card)
        col2.pack(side="left", padx=(S(16), 0))
        self._rotulo(col2, "HORA")
        self.e_hora = Entrada(col2, "hh:mm", width=7)
        self.e_hora.pack(ipady=S(5))

        self._rotulo(c, "CATEGORIA")
        self.f_cat = tk.Frame(c, bg=card)
        self.f_cat.pack(fill="x")

        self._rotulo(c, "OBSERVAÇÃO")
        self.t_nota = tk.Text(c, height=3, width=44, font=(FONTE, 10), relief="flat", wrap="word",
                              highlightthickness=1, highlightbackground=COR["borda"],
                              highlightcolor=COR["primaria"], padx=S(6), pady=S(4), fg=COR["texto"])
        self.t_nota.pack(fill="x")

        self.f_status = None
        if tarefa:
            self._rotulo(c, "STATUS")
            self.f_status = tk.Frame(c, bg=card)
            self.f_status.pack(fill="x")

        self.l_erro = tk.Label(c, text="", bg=card, fg=COR["perigo"], font=(FONTE, 9), anchor="w")
        self.l_erro.pack(fill="x", pady=(S(8), 0))

        rod = tk.Frame(c, bg=card)
        rod.pack(fill="x", pady=(S(6), 0))
        Botao(rod, "Salvar", self.salvar).pack(side="right")
        Botao(rod, "Cancelar", self.destroy, bg=card, fg=COR["suave"], hover=COR["hover"]) \
            .pack(side="right", padx=(0, S(8)))
        if tarefa:
            Botao(rod, "Excluir", self.excluir, bg=card, fg=COR["perigo"], hover="#fef2f2") \
                .pack(side="left")

        cats = [x["nome"] for x in app.store.categorias]
        if tarefa:
            self.e_titulo.definir(tarefa["titulo"])
            if tarefa.get("data"):
                self.e_data.definir(dt.date.fromisoformat(tarefa["data"]).strftime("%d/%m/%Y"))
            self.e_hora.definir(tarefa.get("hora", ""))
            self.t_nota.insert("1.0", tarefa.get("nota", ""))
            self.cat = tarefa.get("categoria", "")
            self.status = tarefa["status"]
        else:
            self.e_data.definir((data or hoje()).strftime("%d/%m/%Y"))
            self.cat = cats[0] if cats else ""
            self.status = "aberta"
        self._montar_chips()

        for e in (self.e_titulo, self.e_data, self.e_hora):
            e.bind("<Return>", lambda ev: self.salvar())
        self.bind("<Escape>", lambda e: self.destroy())
        posicionar(self, janela)
        trazer_para_frente(self)
        self.e_titulo.focus_set()
        self.grab_set()

    def _rotulo(self, master, texto):
        tk.Label(master, text=texto, bg=COR["card"], fg=COR["suave"], font=(FONTE, 8, "bold"),
                 anchor="w").pack(fill="x", pady=(S(12), S(4)))

    def _por_data(self, dias):
        self.e_data.definir("" if dias is None else
                            (hoje() + dt.timedelta(days=dias)).strftime("%d/%m/%Y"))

    def _montar_chips(self):
        for w in self.f_cat.winfo_children():
            w.destroy()
        opcoes = [(x["nome"], x["cor"]) for x in self.app.store.categorias] + [("", COR["fraco"])]
        if self.cat and self.cat not in [n for n, _ in opcoes]:
            opcoes.insert(0, (self.cat, COR["fraco"]))
        for nome, cor in opcoes:
            chip(self.f_cat, nome or "Sem categoria", cor, self.cat == nome,
                 lambda n=nome: self._set("cat", n)).pack(side="left", padx=(0, S(6)), pady=S(2))
        if self.f_status is not None:
            for w in self.f_status.winfo_children():
                w.destroy()
            for chave, nome, cor in self.STATUS:
                chip(self.f_status, nome, cor, self.status == chave,
                     lambda k=chave: self._set("status", k)).pack(side="left", padx=(0, S(6)))

    def _set(self, campo, valor):
        setattr(self, campo, valor)
        self._montar_chips()

    def salvar(self):
        titulo = self.e_titulo.valor().strip()
        if not titulo:
            self.l_erro.configure(text="Informe um título.")
            return
        try:
            data = ler_data_br(self.e_data.valor())
        except ValueError:
            self.l_erro.configure(text="Data inválida — use dd/mm/aaaa.")
            return
        try:
            hora = ler_hora(self.e_hora.valor())
        except ValueError:
            self.l_erro.configure(text="Hora inválida — use hh:mm.")
            return
        campos = dict(titulo=titulo, data=data, hora=hora, categoria=self.cat,
                      nota=self.t_nota.get("1.0", "end").strip())
        self.destroy()
        if self.t:
            self.app.store.atualizar(self.t["id"], status=self.status, **campos)
        else:
            self.app.store.nova(**campos)

    def excluir(self):
        if messagebox.askyesno("Excluir tarefa", f'Excluir "{self.t["titulo"]}"?', parent=self):
            self.destroy()
            self.app.store.remover(self.t["id"])


class DialogoCategorias(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.janela)
        self.app = app
        self.title("Categorias")
        self.configure(bg=COR["card"])
        self.resizable(False, False)
        self.transient(app.janela)
        card = COR["card"]
        c = tk.Frame(self, bg=card, padx=S(24), pady=S(18))
        c.pack(fill="both", expand=True)
        tk.Label(c, text="Categorias", bg=card, fg=COR["texto"], font=(FONTE, 15, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(c, text="Clique na cor para trocar · ✎ renomeia · ✕ remove", bg=card,
                 fg=COR["suave"], font=(FONTE, 9), anchor="w").pack(fill="x", pady=(0, S(10)))
        self.lista = tk.Frame(c, bg=card)
        self.lista.pack(fill="x")

        novo = tk.Frame(c, bg=card)
        novo.pack(fill="x", pady=(S(14), 0))
        self.cor_nova = PALETA[len(app.store.categorias) % len(PALETA)]
        self.amostra = tk.Label(novo, text="", width=3, bg=self.cor_nova, cursor="hand2")
        self.amostra.pack(side="left", fill="y", padx=(0, S(8)))
        self.amostra.bind("<Button-1>", lambda e: self._escolher_cor_nova())
        self.e_nome = Entrada(novo, "Nova categoria", width=22)
        self.e_nome.pack(side="left", ipady=S(4), fill="x", expand=True)
        self.e_nome.bind("<Return>", lambda e: self._adicionar())
        Botao(novo, "Adicionar", self._adicionar, pady=4).pack(side="left", padx=(S(8), 0))

        self.montar()
        self.bind("<Escape>", lambda e: self.destroy())
        posicionar(self, app.janela)
        self.grab_set()

    def montar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        card = COR["card"]
        for cat in self.app.store.categorias:
            linha = tk.Frame(self.lista, bg=card)
            linha.pack(fill="x", pady=S(3))
            amostra = tk.Label(linha, text="", width=3, bg=cat["cor"], cursor="hand2")
            amostra.pack(side="left", fill="y", padx=(0, S(10)))
            amostra.bind("<Button-1>", lambda e, cat=cat: self._trocar_cor(cat))
            qtd = sum(t.get("categoria") == cat["nome"] for t in self.app.store.tarefas)
            tk.Label(linha, text=cat["nome"], bg=card, fg=COR["texto"], font=(FONTE, 11),
                     anchor="w").pack(side="left")
            tk.Label(linha, text=f"  {qtd} tarefa{'s' if qtd != 1 else ''}", bg=card,
                     fg=COR["fraco"], font=(FONTE, 9)).pack(side="left")
            Botao(linha, "✕", lambda cat=cat: self._remover(cat), bg=card, fg=COR["fraco"],
                  hover="#fef2f2", fonte=(FONTE, 10), padx=6, pady=0).pack(side="right")
            Botao(linha, "✎", lambda cat=cat: self._renomear(cat), bg=card, fg=COR["fraco"],
                  hover=COR["hover"], fonte=(FONTE, 10), padx=6, pady=0).pack(side="right")

    def _trocar_cor(self, cat):
        cor = colorchooser.askcolor(cat["cor"], parent=self, title="Cor da categoria")[1]
        if cor:
            cat["cor"] = cor
            self.app.store.salvar()
            self.montar()

    def _escolher_cor_nova(self):
        cor = colorchooser.askcolor(self.cor_nova, parent=self, title="Cor da categoria")[1]
        if cor:
            self.cor_nova = cor
            self.amostra.configure(bg=cor)

    def _existe(self, nome):
        return any(c["nome"].casefold() == nome.casefold() for c in self.app.store.categorias)

    def _adicionar(self):
        nome = self.e_nome.valor().strip()
        if not nome or self._existe(nome):
            return
        self.app.store.categorias.append({"nome": nome, "cor": self.cor_nova})
        self.app.store.salvar()
        self.e_nome.definir("")
        self.cor_nova = PALETA[len(self.app.store.categorias) % len(PALETA)]
        self.amostra.configure(bg=self.cor_nova)
        self.montar()

    def _renomear(self, cat):
        novo = simpledialog.askstring("Renomear", "Novo nome:", initialvalue=cat["nome"], parent=self)
        novo = (novo or "").strip()
        if novo and novo != cat["nome"] and not self._existe(novo):
            self.app.store.renomear_categoria(cat["nome"], novo)
            self.montar()

    def _remover(self, cat):
        if messagebox.askyesno("Remover categoria",
                               f'Remover "{cat["nome"]}"?\nAs tarefas continuam, só ficam sem cor.',
                               parent=self):
            self.app.store.categorias.remove(cat)
            self.app.store.salvar()
            self.montar()


# ----------------------------------------------------------- janela principal

class JanelaPrincipal(tk.Toplevel):
    def __init__(self, app, vista="agenda"):
        super().__init__(app.root)
        self.app = app
        self.title(APP_NOME)
        self.configure(bg=COR["bg"])
        self.geometry(f"{S(1150)}x{S(760)}")
        self.minsize(S(900), S(580))

        card = COR["card"]
        barra = tk.Frame(self, bg=card)
        barra.pack(fill="x")
        tk.Label(barra, text="Daily", bg=card, fg=COR["primaria"], font=(FONTE, 18, "bold")) \
            .pack(side="left", padx=(S(24), S(20)), pady=S(10))
        self.nav = {}
        for chave, nome in (("agenda", "Agenda"), ("tarefas", "Tarefas")):
            b = Botao(barra, nome, lambda k=chave: self.mostrar(k), fonte=(FONTE, 10, "bold"))
            b.pack(side="left", padx=(0, S(6)))
            self.nav[chave] = b
        Botao(barra, "+  Nova tarefa", self.nova_tarefa).pack(side="right", padx=(S(8), S(24)))
        Botao(barra, "Categorias", lambda: DialogoCategorias(app), bg=COR["clara"],
              fg=COR["primaria"], hover=COR["clara_hover"]).pack(side="right")
        tk.Frame(self, bg=COR["borda"], height=1).pack(fill="x")

        area = tk.Frame(self, bg=COR["bg"])
        area.pack(fill="both", expand=True)
        self.vistas = {"agenda": VistaAgenda(area, app), "tarefas": VistaTarefas(area, app)}
        self.atual = None
        self.mostrar(vista)

        app.store.ouvintes.append(self.atualizar)
        self.protocol("WM_DELETE_WINDOW", self.fechar)
        self.bind("<Control-n>", lambda e: self.nova_tarefa())
        self.bind("<Control-f>", lambda e: self._buscar())

    def mostrar(self, chave):
        if self.atual:
            self.vistas[self.atual].pack_forget()
        self.atual = chave
        self.vistas[chave].pack(fill="both", expand=True)
        self.vistas[chave].atualizar()
        for k, b in self.nav.items():
            ativo = k == chave
            b.cores(COR["clara"] if ativo else COR["card"],
                    COR["primaria"] if ativo else COR["suave"],
                    COR["clara"] if ativo else COR["hover"])

    def _buscar(self):
        self.mostrar("tarefas")
        self.vistas["tarefas"].busca.focus_set()

    def nova_tarefa(self):
        data = self.vistas["agenda"].sel if self.atual == "agenda" else hoje()
        self.app.nova_tarefa(data)

    def atualizar(self):
        self.vistas[self.atual].atualizar()

    def fechar(self):
        if self.atualizar in self.app.store.ouvintes:
            self.app.store.ouvintes.remove(self.atualizar)
        self.destroy()
        self.app.janela = None


# --------------------------------------------------------- widget da área de trabalho

class Widget(tk.Toplevel):
    LARGURA = 310
    MAX_HOJE = 12
    MAX_ATRASADAS = 5

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        cfg = app.store.config
        self.overrideredirect(True)
        self.configure(bg=COR["primaria"])
        try:
            self.attributes("-alpha", 0.985)
        except tk.TclError:
            pass
        self.var_topo = tk.BooleanVar(self, value=cfg.get("widget_topo", False))
        self.var_auto = tk.BooleanVar(self, value=autostart_ativo())
        self.attributes("-topmost", self.var_topo.get())

        card = COR["card"]
        self.caixa = tk.Frame(self, bg=card)
        self.caixa.pack(fill="both", expand=True, padx=1, pady=1)

        self.cab = tk.Frame(self.caixa, bg=COR["primaria"], cursor="fleur")
        self.cab.pack(fill="x")
        textos = tk.Frame(self.cab, bg=COR["primaria"])
        textos.pack(side="left", padx=S(14), pady=S(10))
        self.l_titulo = tk.Label(textos, text="Hoje", bg=COR["primaria"], fg="white",
                                 font=(FONTE, 14, "bold"), anchor="w")
        self.l_titulo.pack(fill="x")
        self.l_data = tk.Label(textos, bg=COR["primaria"], fg="#dbeafe", font=(FONTE, 9), anchor="w")
        self.l_data.pack(fill="x")
        botoes = dict(bg=COR["primaria"], fg="white", hover=COR["primaria_hover"], padx=8, pady=2)
        Botao(self.cab, "↗", app.abrir, fonte=(FONTE, 12, "bold"), **botoes) \
            .pack(side="right", padx=(0, S(8)))
        Botao(self.cab, "+", lambda: app.nova_tarefa(hoje()), fonte=(FONTE, 14, "bold"), **botoes) \
            .pack(side="right")
        for w in (self.cab, textos, self.l_titulo, self.l_data):
            w.bind("<ButtonPress-1>", self._iniciar_arrasto)
            w.bind("<B1-Motion>", self._arrastar)
            w.bind("<ButtonRelease-1>", self._fim_arrasto)

        self.corpo = tk.Frame(self.caixa, bg=card)
        self.corpo.pack(fill="x", pady=(S(8), S(4)))
        self.rodape = tk.Frame(self.caixa, bg=card)
        self.rodape.pack(fill="x", padx=S(14), pady=(0, S(10)))

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Abrir Daily", command=app.abrir)
        self.menu.add_command(label="Nova tarefa para hoje", command=lambda: app.nova_tarefa(hoje()))
        self.menu.add_separator()
        self.menu.add_checkbutton(label="Manter sempre visível", variable=self.var_topo,
                                  command=self._alternar_topo)
        self.menu.add_checkbutton(label="Iniciar com o Windows", variable=self.var_auto,
                                  command=self._alternar_auto)
        self.menu.add_separator()
        self.menu.add_command(label="Sair do Daily", command=app.sair)

        self._x, self._y = self._posicao_inicial()
        self._dia = None
        self.atualizar()
        self.bind("<Button-3>", self._menu)  # vale para todos os filhos (bindtag da toplevel)
        self.bind("<Leave>", lambda e: self.after(150, self._ao_sair))
        self.after(600, self._para_o_fundo)
        self.after(5000, self._tique)

    # posição / arrasto
    def _posicao_inicial(self):
        pos = self.app.store.config.get("widget_pos")
        try:
            u = ctypes.windll.user32
            vx, vy, vw, vh = (u.GetSystemMetrics(i) for i in (76, 77, 78, 79))
        except Exception:
            vx, vy, vw, vh = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        if pos and vx - 50 <= pos[0] <= vx + vw - 60 and vy <= pos[1] <= vy + vh - 60:
            return int(pos[0]), int(pos[1])
        return self.winfo_screenwidth() - S(self.LARGURA) - S(24), S(40)

    def _iniciar_arrasto(self, e):
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _arrastar(self, e):
        self._x, self._y = e.x_root - self._dx, e.y_root - self._dy
        self.geometry(f"+{self._x}+{self._y}")

    def _fim_arrasto(self, _e):
        self.app.store.config["widget_pos"] = [self._x, self._y]
        self.app.store.salvar(notificar=False)

    # comportamento "de área de trabalho"
    def _hwnd(self):
        return ctypes.windll.user32.GetParent(self.winfo_id())

    def _para_o_fundo(self):
        if self.var_topo.get():
            return
        try:  # HWND_BOTTOM, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
            ctypes.windll.user32.SetWindowPos(self._hwnd(), 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass

    def _ao_sair(self):
        if not self.winfo_exists():
            return
        x, y = self.winfo_pointerxy()
        dentro = (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                  and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())
        if not dentro:
            self._para_o_fundo()

    def _alternar_topo(self):
        self.attributes("-topmost", self.var_topo.get())
        self.app.store.config["widget_topo"] = self.var_topo.get()
        self.app.store.salvar(notificar=False)
        self._para_o_fundo()

    def _alternar_auto(self):
        try:
            definir_autostart(self.var_auto.get())
        except OSError as e:
            messagebox.showerror(APP_NOME, f"Não foi possível alterar a inicialização:\n{e}")
        self.var_auto.set(autostart_ativo())

    def _menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _tique(self):
        self.app.store.verificar_externo()
        if hoje() != self._dia:
            self.atualizar()
            if self.app.janela is not None:
                self.app.janela.atualizar()
        self.after(5000, self._tique)

    # conteúdo
    def atualizar(self):
        h = hoje()
        self._dia = h
        self.l_data.configure(text=data_extensa(h).lower())
        store = self.app.store
        card = COR["card"]
        for w in self.corpo.winfo_children() + self.rodape.winfo_children():
            w.destroy()

        hiso = h.isoformat()
        ts = sorted((t for t in store.tarefas if t.get("data") == hiso and t["status"] != "cancelada"),
                    key=lambda t: (t["status"] != "aberta", t.get("hora") or "99:99", t["titulo"].lower()))
        atrasadas = sorted((t for t in store.tarefas
                            if t["status"] == "aberta" and t.get("data") and t["data"] < hiso),
                           key=chave_ordem)

        if not ts:
            tk.Label(self.corpo, text="Nada agendado para hoje.", bg=card, fg=COR["fraco"],
                     font=(FONTE, 10), anchor="w").pack(fill="x", padx=S(14), pady=S(6))
        for t in ts[:self.MAX_HOJE]:
            self._linha(t)
        if len(ts) > self.MAX_HOJE:
            self._mais(len(ts) - self.MAX_HOJE, "tarefas")

        if atrasadas:
            l = tk.Label(self.corpo, text=f"ATRASADAS · {len(atrasadas)}", bg=card, fg=COR["perigo"],
                         font=(FONTE, 8, "bold"), anchor="w", cursor="hand2")
            l.pack(fill="x", padx=S(14), pady=(S(10), S(2)))
            l.bind("<Button-1>", lambda e: self.app.abrir("tarefas"))
            for t in atrasadas[:self.MAX_ATRASADAS]:
                self._linha(t, com_data=True)
            if len(atrasadas) > self.MAX_ATRASADAS:
                self._mais(len(atrasadas) - self.MAX_ATRASADAS, "tarefas")

        if ts:
            feitas = sum(t["status"] == "concluida" for t in ts)
            tk.Label(self.rodape, text=f"{feitas} de {len(ts)} concluída{'s' if len(ts) > 1 else ''}",
                     bg=card, fg=COR["suave"], font=(FONTE, 8), anchor="w").pack(fill="x", pady=(S(6), S(3)))
            larg = S(self.LARGURA) - S(30)
            barra = tk.Canvas(self.rodape, width=larg, height=S(5), bg=COR["seg"], highlightthickness=0)
            barra.pack(fill="x")
            if feitas:
                barra.create_rectangle(0, 0, larg * feitas / len(ts), S(5), fill=COR["primaria"], width=0)

        self.update_idletasks()
        self.geometry(f"{S(self.LARGURA)}x{self.caixa.winfo_reqheight() + 2}+{self._x}+{self._y}")

    def _mais(self, n, vista):
        l = tk.Label(self.corpo, text=f"+{n} mais…", bg=COR["card"], fg=COR["primaria"],
                     font=(FONTE, 9, "bold"), anchor="w", cursor="hand2")
        l.pack(fill="x", padx=S(14), pady=(S(2), 0))
        l.bind("<Button-1>", lambda e: self.app.abrir(vista))

    def _linha(self, t, com_data=False):
        card = COR["card"]
        store = self.app.store
        cor = store.cor(t.get("categoria", ""))
        feito = t["status"] != "aberta"
        linha = tk.Frame(self.corpo, bg=card)
        linha.pack(fill="x", padx=S(14), pady=S(3))
        Check(linha, t["status"], cor, lambda: store.alternar(t["id"]), tam=18, bg=card) \
            .pack(side="left", anchor="n", pady=(S(2), 0))
        txt = tk.Frame(linha, bg=card, cursor="hand2")
        txt.pack(side="left", fill="x", expand=True, padx=(S(8), 0))
        tk.Label(txt, text=t["titulo"], bg=card, anchor="w", justify="left",
                 wraplength=S(self.LARGURA - 70),
                 font=(FONTE, 10, "overstrike" if feito else "normal"),
                 fg=COR["fraco"] if feito else COR["texto"]).pack(fill="x")
        partes = []
        if com_data:
            partes.append(data_curta(dt.date.fromisoformat(t["data"])))
        if t.get("hora"):
            partes.append(t["hora"])
        if partes or t.get("categoria"):
            meta = tk.Frame(txt, bg=card)
            meta.pack(fill="x")
            if partes:
                tk.Label(meta, text="  ".join(partes), bg=card, font=(FONTE, 8),
                         fg=COR["perigo"] if com_data else COR["suave"]).pack(side="left")
            if t.get("categoria"):
                tk.Label(meta, text=f"● {t['categoria']}", bg=card, fg=cor,
                         font=(FONTE, 8)).pack(side="left", padx=(S(6) if partes else 0, 0))
        ligar_clique(txt, lambda e: self.app.editar(t))


# ------------------------------------------------------------------------- app

class App:
    def __init__(self, servidor, abrir_janela):
        global ESCALA
        self.servidor = servidor
        self.root = tk.Tk()
        self.root.withdraw()
        ESCALA = max(1.0, self.root.winfo_fpixels("1i") / 96)
        self.icone = criar_icone(self.root)
        self.root.iconphoto(True, self.icone)
        self.root.bind_all("<MouseWheel>", self._rodar_mouse)

        self.store = Store(ARQUIVO_DADOS)
        self.janela = None
        self._configurar_autostart()

        self.widget = Widget(self)
        self.store.ouvintes.append(self.widget.atualizar)

        self.fila = queue.Queue()
        threading.Thread(target=self._escutar, daemon=True).start()
        self.root.after(300, self._ler_fila)
        if abrir_janela:
            self.abrir()

    def _configurar_autostart(self):
        cfg = self.store.config
        try:
            if not cfg.get("autostart_configurado"):
                definir_autostart(True)  # primeira execução: liga sozinho
                cfg["autostart_configurado"] = True
                self.store.salvar(notificar=False)
            elif autostart_ativo():
                definir_autostart(True)  # atualiza o caminho caso a pasta tenha mudado
        except OSError:
            pass

    def _rodar_mouse(self, e):
        try:
            w = self.root.winfo_containing(e.x_root, e.y_root)
        except (KeyError, tk.TclError):
            return
        while w is not None:
            if isinstance(w, ScrollFrame):
                w.rolar(e)
                return
            w = w.master

    def _escutar(self):
        while True:
            try:
                conn, _ = self.servidor.accept()
            except OSError:
                return
            with conn:
                try:
                    self.fila.put(conn.recv(64).decode(errors="ignore").strip())
                except OSError:
                    pass

    def _ler_fila(self):
        try:
            while True:
                if self.fila.get_nowait() == "abrir":
                    self.abrir()
        except queue.Empty:
            pass
        self.root.after(300, self._ler_fila)

    def abrir(self, vista=None):
        if self.janela is not None and self.janela.winfo_exists():
            if vista:
                self.janela.mostrar(vista)
        else:
            self.janela = JanelaPrincipal(self, vista or "agenda")
        trazer_para_frente(self.janela)

    def nova_tarefa(self, data=None):
        DialogoTarefa(self, data=data)

    def editar(self, t):
        DialogoTarefa(self, tarefa=t)

    def sair(self):
        try:
            self.servidor.close()
        except OSError:
            pass
        self.root.destroy()

    def rodar(self):
        self.root.mainloop()


def iniciar_servidor():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        s.bind(("127.0.0.1", PORTA))
        s.listen(5)
        return s
    except OSError:
        s.close()
        return None


def main():
    ao_ligar = "--startup" in sys.argv
    servidor = iniciar_servidor()
    if servidor is None:
        # já está rodando: pede para a instância aberta mostrar a janela
        if not ao_ligar:
            try:
                with socket.create_connection(("127.0.0.1", PORTA), timeout=2) as c:
                    c.sendall(b"abrir")
            except OSError:
                pass
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App(servidor, abrir_janela=not ao_ligar).rodar()


if __name__ == "__main__":
    main()
