"""Teste de ponta a ponta da interface + capturas de tela, usando o Chrome/Edge já instalado (modo headless) pelo
protocolo DevTools. Só biblioteca padrão. Precisa da interface no ar (interface\\app.py) e do Ollama.
Uso:  .venv\\Scripts\\python.exe interface\\capturar_telas.py [nome ...]   (sem nomes: roda todas as telas)"""
import base64, json, os, shutil, socket, struct, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

BASE = "http://localhost:8000"
SAIDA = Path(__file__).resolve().parent / "capturas"
PORTA = 9333
NAVEGADORES = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
               r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]

# nome do arquivo: (caminho na interface, espera o agente terminar?, texto a extrair da tela para o relatório)
TELAS = {
    "00_inicio": ("/", False),
    "01_clinica_controle": ("/clinica?p=normal&auto=1", True),
    "02_clinica_ataque": ("/clinica?p=ataque&auto=1", True),
    "03_clinica_ataque_protegido": ("/clinica?p=ataque&protegido=1&auto=1", True),
    "04_clinica_medico_le_prontuario": ("/clinica?p=medico&protegido=1&auto=1", True),
    "05_juridico_peticao_revelada": ("/juridico?peticao=peticao_injetada.docx&revelar=1", False),
    "06_juridico_defesa_limpa": ("/juridico?papel=defesa&peticao=peticao_limpa.docx&auto=1", True),
    "07_juridico_defesa_injetada": ("/juridico?papel=defesa&peticao=peticao_injetada.docx&auto=1", True),
    "08_juridico_juizo_injetada": ("/juridico?papel=juizo&peticao=peticao_injetada_juizo.docx&auto=1", True),
    "09_juridico_defesa_protegido": ("/juridico?papel=defesa&peticao=peticao_injetada.docx&protegido=1&auto=1", True),
    "10_juridico_juizo_protegido": ("/juridico?papel=juizo&peticao=peticao_injetada_juizo.docx&protegido=1&auto=1", True),
    "11_clinica_saida_gravada": ("/clinica?gravado=12_medico_ataque.txt", True),
}
RESUMO_JS = """(() => {
  const t = (s) => [...document.querySelectorAll(s)].map((e) => e.innerText.replace(/\\s+/g, ' ').trim()).filter(Boolean);
  return JSON.stringify({faixas: t('.faixa'), placar: t('#placar span'), caixa: t('.msg .tt'),
    prontuarios: t('.pront .st').filter((s) => !/sigiloso/i.test(s)), ferramentas: t('.passo .nome'),
    resposta: t('.bolha.ia').map((s) => s.slice(0, 160)), fim: t('.chip, .passo .texto').filter((s) => /terminou/.test(s))});
})()"""


class Aba:
    """Cliente WebSocket mínimo (RFC 6455) para o protocolo DevTools."""
    def __init__(self, url_ws):
        resto = url_ws.split("://", 1)[1]
        hostporta, caminho = resto.split("/", 1)
        host, porta = hostporta.split(":")
        self.s = socket.create_connection((host, int(porta)))
        chave = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{caminho} HTTP/1.1\r\nHost: {hostporta}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {chave}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        cab = b""
        while b"\r\n\r\n" not in cab:
            cab += self.s.recv(1)
        if b" 101 " not in cab.split(b"\r\n")[0]:
            raise RuntimeError(cab.decode(errors="replace"))
        self.n = 0

    def _ler(self, n):
        dados = b""
        while len(dados) < n:
            parte = self.s.recv(n - len(dados))
            if not parte:
                raise ConnectionError("conexão fechada")
            dados += parte
        return dados

    def _quadro(self):
        b1, b2 = self._ler(2)
        tam = b2 & 0x7F
        if tam == 126:
            tam = struct.unpack(">H", self._ler(2))[0]
        elif tam == 127:
            tam = struct.unpack(">Q", self._ler(8))[0]
        return b1 & 0x80, self._ler(tam)

    def _mensagem(self):
        fim, dados = self._quadro()
        while not fim:
            fim, mais = self._quadro()
            dados += mais
        return json.loads(dados)

    def chamar(self, metodo, **params):
        self.n += 1
        corpo = json.dumps({"id": self.n, "method": metodo, "params": params}).encode()
        mascara = os.urandom(4)
        cab = bytes([0x81])
        cab += bytes([0x80 | len(corpo)]) if len(corpo) < 126 else bytes([0x80 | 126]) + struct.pack(">H", len(corpo))
        self.s.sendall(cab + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(corpo)))
        while True:
            m = self._mensagem()
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})

    def avaliar(self, expressao):
        return self.chamar("Runtime.evaluate", expression=expressao, returnByValue=True).get("result", {}).get("value")


def main(nomes):
    navegador = next((n for n in NAVEGADORES if Path(n).exists()), None)
    if not navegador:
        sys.exit("Chrome/Edge não encontrado.")
    SAIDA.mkdir(exist_ok=True)
    perfil = tempfile.mkdtemp(prefix="perfil_captura_")
    proc = subprocess.Popen([navegador, "--headless=new", f"--remote-debugging-port={PORTA}", f"--user-data-dir={perfil}",
                             "--hide-scrollbars", "--window-size=1920,1080", "--no-first-run", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                paginas = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/json/list", timeout=2))
                if any(p["type"] == "page" for p in paginas):
                    break
            except OSError:
                pass
            time.sleep(0.3)
        aba = Aba(next(p for p in paginas if p["type"] == "page")["webSocketDebuggerUrl"])
        aba.chamar("Emulation.setDeviceMetricsOverride", width=1920, height=1080, deviceScaleFactor=1, mobile=False)
        relatorio = []
        for nome in nomes:
            caminho, espera = TELAS[nome]
            inicio = time.time()
            aba.chamar("Page.navigate", url=BASE + caminho)
            time.sleep(2.5)
            if espera:
                while aba.avaliar("document.body.dataset.estado") != "pronto" and time.time() - inicio < 600:
                    time.sleep(1)
                time.sleep(1.2)   # deixa as animações terminarem
            png = aba.chamar("Page.captureScreenshot", format="png")["data"]
            (SAIDA / f"{nome}.png").write_bytes(base64.b64decode(png))
            resumo = json.loads(aba.avaliar(RESUMO_JS) or "{}")
            linha = f"{nome}: {time.time() - inicio:.0f}s | " + json.dumps(resumo, ensure_ascii=False)
            print(linha, flush=True)
            relatorio.append(linha)
        (SAIDA / "resultado_teste.txt").write_text("\n".join(relatorio) + "\n", encoding="utf-8")
    finally:
        proc.terminate()
        time.sleep(1)
        shutil.rmtree(perfil, ignore_errors=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main([n for n in sys.argv[1:] if n in TELAS] or list(TELAS))
