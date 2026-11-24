"""Servidor MCP (stdio) do "assistente de escritório" -- LABORATÓRIO DE DEMONSTRAÇÃO.
Tudo é falso e offline: enviar_email NÃO envia nada, só anota em caixa_de_saida.txt."""
import os, sys
from datetime import datetime
from pathlib import Path
from mcp.server.mcpserver import MCPServer
import email_real   # envio real opcional (config_email.env); sem ele, tudo continua simulado

PASTA = Path(__file__).resolve().parent
DADOS = PASTA / "dados"
AVISO = lambda texto, estilo: print(f"{estilo}{texto}\033[0m", file=sys.stderr, flush=True)
CAIXA = Path(os.environ.get("CAIXA_DE_SAIDA", PASTA / "caixa_de_saida.txt"))

servidor = MCPServer("escritorio", instructions="Ferramentas de escritório: ler arquivos da pasta dados e enviar e-mails.")


@servidor.tool()
def ler_arquivo(nome: str) -> str:
    """Lê um arquivo de texto da pasta de documentos da empresa e devolve o conteúdo."""
    caminho = (DADOS / nome).resolve()
    if DADOS not in caminho.parents or not caminho.is_file():   # bloqueia ../ e caminhos fora de ./dados
        return f"Erro: arquivo '{nome}' não encontrado na pasta de documentos."
    return caminho.read_text(encoding="utf-8")


@servidor.tool()
def enviar_email(para: str, assunto: str, corpo: str) -> str:
    """Envia um e-mail."""
    registro = (f"===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n"
                f"Para: {para}\nAssunto: {assunto}\n{corpo}\n\n")
    with CAIXA.open("a", encoding="utf-8") as arquivo:
        arquivo.write(registro)
    # o stdout é o canal JSON-RPC do MCP: o destaque vai para o stderr, que aparece no terminal do agente
    print(f"\033[41;97m[SERVIDOR] E-MAIL (SIMULADO) PARA {para}: {assunto}\033[0m", file=sys.stderr, flush=True)
    resultado, info = email_real.enviar(para, corpo, assunto)   # só faz algo com config_email.env preenchido
    if resultado == "real":
        AVISO(f"[SERVIDOR] E-MAIL ENVIADO DE VERDADE PARA {info}", "\033[41;97m")
    elif resultado == "falhou":
        AVISO(f"[SERVIDOR] AVISO: o envio real falhou ({info}); ficou só no simulado.", "\033[43;30m")
    elif info != "modo real desligado":
        AVISO(f"[SERVIDOR] E-MAIL REAL NÃO ENVIADO ({info}); ficou só no simulado.", "\033[43;30m")
    return f"E-mail enviado para {para}."


if __name__ == "__main__":
    sys.stderr.reconfigure(encoding="utf-8")
    servidor.run("stdio")
