"""Interface web LOCAL e OFFLINE das demos de prompt injection -- LABORATÓRIO DE DEMONSTRAÇÃO.
Só biblioteca padrão do Python (+ python-docx, que o projeto já usa). Não muda os agentes: cada pedido roda o mesmo
comando de linha de comando (agente_juridico.py / agente_clinico.py) e a saída é transmitida, linha a linha, ao navegador.
Uso:  .venv\\Scripts\\python.exe interface\\app.py   (abre http://localhost:8000)"""
import json, os, re, subprocess, sys, threading, time, unicodedata, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import email_real   # só para mostrar na tela se o e-mail está simulado ou real
ESTATICO = Path(__file__).resolve().parent / "static"
JURIDICO = RAIZ / "cenario_juridico"
MEDICO = RAIZ / "cenario_medico"
SAIDAS = RAIZ / "roteiro_saidas"
PORTA = int(os.environ.get("PORTA", "8000"))
OLLAMA = "http://127.0.0.1:11434"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
MODELOS = {"qwen2.5:7b", "qwen2.5:3b"}
PETICOES = {"peticao_limpa.docx", "peticao_injetada.docx", "peticao_injetada_juizo.docx"}
TIPOS = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png"}

ocupado = threading.Lock()   # uma conversa por vez: a GPU é uma só
processo_atual = None


def sem_acento(texto):
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def comando(pedido):
    """Monta a MESMA linha de comando da demo no terminal, a partir das escolhas da tela."""
    modelo = pedido.get("modelo") if pedido.get("modelo") in MODELOS else "qwen2.5:7b"
    if pedido.get("cenario") == "medico":
        args = [sys.executable, "-u", str(MEDICO / "agente_clinico.py"), "--modelo", modelo,
                "--usuario", "medico" if pedido.get("usuario") == "medico" else "recepcao"]
        if pedido.get("protegido"):
            args.append("--protegido")
        texto = str(pedido.get("pedido") or "").strip()
        if texto:
            args.append(texto[:2000])
        return args, MEDICO
    papel = "juizo" if pedido.get("papel") == "juizo" else "defesa"
    peticao = pedido.get("peticao") if pedido.get("peticao") in PETICOES else "peticao_limpa.docx"
    args = [sys.executable, "-u", str(JURIDICO / "agente_juridico.py"), "--papel", papel, "--peticao", peticao,
            "--modelo", modelo]
    if pedido.get("usuario") in ("assessor", "juiz", "advogado"):
        args += ["--usuario", pedido["usuario"]]
    if pedido.get("protegido"):
        args.append("--protegido")
    return args, JURIDICO


def peticao_em_json(nome):
    """Parágrafos da petição com cada trecho marcado: visível ou oculto (mesma regra do guardrail do servidor)."""
    from docx import Document
    doc = Document(JURIDICO / "peticoes" / nome)
    paragrafos = []
    for p in doc.paragraphs:
        trechos = []
        for run in p.runs:
            if not run.text:
                continue
            motivos = []
            cor = run.font.color.rgb if run.font.color is not None and run.font.color.type is not None else None
            if cor is not None and min(cor[0], cor[1], cor[2]) >= 0xF0:
                motivos.append(f"fonte branca (#{cor})")
            if run.font.size is not None and run.font.size.pt < 4:
                motivos.append(f"fonte minúscula ({run.font.size.pt:g} pt)")
            if run.font.hidden:
                motivos.append("texto marcado como oculto")
            trechos.append({"texto": run.text, "negrito": bool(run.bold), "oculto": bool(motivos), "motivos": motivos})
        centro = p.alignment is not None and int(p.alignment) == 1
        paragrafos.append({"trechos": trechos, "centro": centro})
    return {"arquivo": nome, "paragrafos": paragrafos}


def estado_clinica():
    agenda = json.loads((MEDICO / "dados" / "agenda.json").read_text(encoding="utf-8"))
    nomes = {sem_acento(c["paciente"]): c["paciente"] for dia in ("hoje", "amanha") for c in agenda[dia]}
    pacientes = [nomes.get(p.stem.replace("_", " "), p.stem.replace("_", " ").title())
                 for p in sorted((MEDICO / "dados" / "prontuarios").glob("*.txt"))]
    return {"hoje": agenda["hoje"], "amanha": agenda["amanha"], "pacientes": pacientes}


def gravados():
    return sorted(p.name for p in SAIDAS.glob("*.txt") if p.name != "tempos.txt")


def ollama(caminho, corpo=None, tempo=5):
    pedido = urllib.request.Request(OLLAMA + caminho, json.dumps(corpo).encode() if corpo else None,
                                    {"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=tempo) as resposta:
        return json.load(resposta)


class Tratador(BaseHTTPRequestHandler):
    def log_message(self, formato, *args):   # silencia o log de cada requisição
        pass

    def responder(self, codigo, corpo, tipo="application/json; charset=utf-8"):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def corpo_json(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(tamanho) or b"{}") if tamanho else {}

    def linha(self, objeto):
        self.wfile.write((json.dumps(objeto, ensure_ascii=False) + "\n").encode())
        self.wfile.flush()

    def iniciar_fluxo(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        url = urlparse(self.path)
        rota, consulta = url.path, parse_qs(url.query)
        paginas = {"/": "index.html", "/clinica": "clinica.html", "/juridico": "juridico.html"}
        try:
            if rota in paginas or rota.startswith("/static/"):
                nome = paginas.get(rota) or rota[len("/static/"):]
                arquivo = (ESTATICO / nome).resolve()
                if ESTATICO not in arquivo.parents or not arquivo.is_file():
                    return self.responder(404, {"erro": "não encontrado"})
                return self.responder(200, arquivo.read_bytes(), TIPOS.get(arquivo.suffix, "application/octet-stream"))
            if rota == "/api/clinica":
                return self.responder(200, estado_clinica())
            if rota == "/api/peticao":
                nome = (consulta.get("arquivo") or [""])[0]
                if nome not in PETICOES:
                    return self.responder(404, {"erro": "petição desconhecida"})
                return self.responder(200, peticao_em_json(nome))
            if rota == "/api/email":
                return self.responder(200, email_real.estado())
            if rota == "/api/gravados":
                return self.responder(200, gravados())
            if rota == "/api/status":
                try:
                    disponiveis = [m["name"] for m in ollama("/api/tags")["models"]]
                    carregados = [m["name"] for m in ollama("/api/ps")["models"]]
                    return self.responder(200, {"ollama": True, "modelos": disponiveis, "carregados": carregados})
                except Exception as erro:
                    return self.responder(200, {"ollama": False, "erro": str(erro)})
            if rota == "/api/gravado":
                nome = Path((consulta.get("arquivo") or [""])[0]).name
                if nome not in gravados():
                    return self.responder(404, {"erro": "saída gravada desconhecida"})
                self.iniciar_fluxo()
                inicio = time.time()
                for texto in (SAIDAS / nome).read_text(encoding="utf-8").splitlines():
                    self.linha({"l": texto})
                    time.sleep(0.25 if texto.startswith(("[tool]", "[SERVIDOR]", " ALERTA", " VAZAMENTO")) else 0.03)
                return self.linha({"fim": True, "codigo": 0, "segundos": round(time.time() - inicio), "gravado": True})
            self.responder(404, {"erro": "não encontrado"})
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    # ---------------------------------------------------------------- POST
    def do_POST(self):
        global processo_atual
        rota = urlparse(self.path).path
        if rota == "/api/esquentar":
            modelo = self.corpo_json().get("modelo")
            modelo = modelo if modelo in MODELOS else "qwen2.5:7b"
            try:
                ollama("/api/generate", {"model": modelo, "prompt": "diga ok", "stream": False, "keep_alive": "60m"}, 300)
                return self.responder(200, {"ok": True})
            except Exception as erro:
                return self.responder(200, {"ok": False, "erro": str(erro)})
        if rota == "/api/reiniciar":
            cenario = self.corpo_json().get("cenario")
            apagados = 0
            if cenario == "medico":
                for nome in ("caixa_de_saida.txt",):
                    if (MEDICO / nome).exists():
                        (MEDICO / nome).unlink()
                        apagados += 1
            else:
                for minuta in (JURIDICO / "minutas").glob("*.txt"):
                    minuta.unlink()
                    apagados += 1
            return self.responder(200, {"ok": True, "apagados": apagados})
        if rota == "/api/parar":
            if processo_atual and processo_atual.poll() is None:
                processo_atual.kill()
            return self.responder(200, {"ok": True})
        if rota != "/api/rodar":
            return self.responder(404, {"erro": "não encontrado"})
        if not ocupado.acquire(blocking=False):
            return self.responder(409, {"erro": "Já há uma conversa rodando. Espere terminar ou clique em Parar."})
        try:
            args, pasta = comando(self.corpo_json())
            ambiente = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            inicio = time.time()
            processo_atual = subprocess.Popen(args, cwd=pasta, env=ambiente, stdout=subprocess.PIPE,
                                              stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            self.iniciar_fluxo()
            try:
                for bruto in processo_atual.stdout:
                    self.linha({"l": ANSI.sub("", bruto.decode("utf-8", "replace").rstrip("\r\n"))})
                codigo = processo_atual.wait()
                self.linha({"fim": True, "codigo": codigo, "segundos": round(time.time() - inicio)})
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                processo_atual.kill()   # o navegador fechou ou clicou em Parar
        finally:
            processo_atual = None
            ocupado.release()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Tratador)
    endereco = f"http://localhost:{PORTA}"
    print(f"Interface das demos em {endereco}  (Ctrl+C para sair)")
    if "--sem-navegador" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(endereco)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
