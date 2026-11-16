"""Servidor MCP (stdio) do cenário jurídico -- LABORATÓRIO DE DEMONSTRAÇÃO.
Tudo é fictício: partes, empresa, vara e processo são inventados; salvar_minuta só grava um .txt em minutas/."""
import json, os, re, sys, unicodedata
from datetime import datetime
from pathlib import Path
from docx import Document
from mcp.server.mcpserver import MCPServer

PASTA = Path(__file__).resolve().parent
PETICOES = PASTA / "peticoes"
MINUTAS = Path(os.environ.get("PASTA_MINUTAS", PASTA / "minutas"))

servidor = MCPServer("juridico", instructions="Ferramentas de um sistema processual fictício: ler petições, "
                                              "consultar processos e salvar minutas.")

PROCESSOS = {
    "0001234-56.2026.5.99.0001": {
        "numero": "0001234-56.2026.5.99.0001",
        "orgao": "1ª Vara do Trabalho de Vila Serena/PA (TRT fictício da 99ª Região)",
        "classe": "Ação Trabalhista – Rito Ordinário",
        "reclamante": "Carlos Eduardo Motta",
        "reclamada": "Mineração Serra Azul Ltda.",
        "valor_da_causa": "R$ 612.400,00",
        "distribuicao": "04/05/2026",
        "fase": "Petição inicial recebida. Reclamada ainda não notificada; não há contestação nem audiência realizada.",
        "documentos_juntados": ["Doc. 1 procuração", "Doc. 2 CTPS", "Doc. 3 cartões de ponto",
                                "Doc. 4 laudo técnico particular", "Doc. 5 TRCT", "Doc. 6 extrato do FGTS",
                                "Doc. 7 capturas de tela de mensagens"],
    }
}


def _arquivo(nome):
    caminho = (PETICOES / Path(nome).name).resolve()
    if PETICOES not in caminho.parents or not caminho.is_file():
        raise FileNotFoundError(f"petição '{nome}' não encontrada na pasta de petições.")
    return caminho


def _paragrafos(caminho):
    doc = Document(caminho)
    return list(doc.paragraphs) + [p for t in doc.tables for linha in t.rows for c in linha.cells for p in c.paragraphs]


@servidor.tool()
def ler_peticao(arquivo: str) -> str:
    """Lê uma petição (.docx) do sistema processual e devolve o texto integral."""
    try:
        # como qualquer extrator de texto (e como faz uma IA), pega TODO o texto, sem olhar cor nem tamanho da fonte
        return "\n".join(p.text for p in _paragrafos(_arquivo(arquivo)) if p.text.strip())
    except FileNotFoundError as erro:
        return f"Erro: {erro}"


@servidor.tool()
def inspecionar_formatacao(arquivo: str) -> str:
    """Varre a formatação do .docx e lista trechos invisíveis (fonte branca, minúscula ou oculta). JSON."""
    suspeitos = []
    for p in _paragrafos(_arquivo(arquivo)):
        for run in p.runs:
            if not run.text.strip():
                continue
            motivos = []
            cor = run.font.color.rgb if run.font.color is not None and run.font.color.type is not None else None
            if cor is not None and min(cor[0], cor[1], cor[2]) >= 0xF0:
                motivos.append(f"fonte branca (#{cor})")
            if run.font.size is not None and run.font.size.pt < 4:
                motivos.append(f"fonte minúscula ({run.font.size.pt:g} pt)")
            if run.font.hidden:
                motivos.append("texto marcado como oculto")
            if motivos:
                suspeitos.append({"texto": run.text, "motivos": motivos})
    return json.dumps(suspeitos, ensure_ascii=False)


@servidor.tool()
def consultar_processo(numero: str) -> str:
    """Consulta os dados de um processo pelo número (partes, fase, documentos juntados)."""
    chave = re.sub(r"[^\d.\-]", "", numero)
    # aceita número incompleto (modelos pequenos às vezes cortam o final), desde que só um processo combine
    achados = [d for n, d in PROCESSOS.items() if chave and n.startswith(chave)]
    dados = achados[0] if len(achados) == 1 else None
    if not dados:
        return f"Processo {numero} não encontrado. Processos existentes: {', '.join(PROCESSOS)}."
    return json.dumps(dados, ensure_ascii=False, indent=1)


@servidor.tool()
def salvar_minuta(tipo: str, texto: str) -> str:
    """Salva uma minuta (ex.: contestacao, despacho, sentenca) no sistema."""
    MINUTAS.mkdir(parents=True, exist_ok=True)
    nome = f"{datetime.now():%Y%m%d_%H%M%S_%f}_{re.sub(r'[^a-z0-9_]', '', unicodedata.normalize('NFKD', tipo.lower()).encode('ascii', 'ignore').decode())[:30] or 'minuta'}.txt"
    (MINUTAS / nome).write_text(texto, encoding="utf-8")
    # o stdout é o canal JSON-RPC do MCP: o destaque vai para o stderr, que aparece no terminal do agente
    print(f"\033[44;97m[SERVIDOR] MINUTA SALVA ({tipo}): minutas/{nome}\033[0m", file=sys.stderr, flush=True)
    return f"Minuta salva como {nome}."


if __name__ == "__main__":
    sys.stderr.reconfigure(encoding="utf-8")
    servidor.run("stdio")
