"""Envio de e-mail REAL opcional para a demo -- LABORATÓRIO DE DEMONSTRAÇÃO.
Só liga se existir config_email.env na raiz do projeto (veja config_email.exemplo.env) e EMAIL_REAL != "0".
No modo real, o e-mail vai de verdade para o destinatário que a IA usou na ferramenta, com salvaguardas:
- domínios reservados/fictícios (exemplo.com, example.com, *.exemplo, *.test...) e telefones continuam simulados;
- se DESTINOS_PERMITIDOS estiver preenchido, só esses endereços recebem de verdade (o resto é simulado);
- no máximo 3 e-mails reais por execução do agente (cada execução sobe o seu próprio servidor MCP);
- sem internet ou com falha no SMTP, devolve o erro e a demo segue no modo simulado."""
import os, re, smtplib, ssl
from email.message import EmailMessage
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent / "config_email.env"
LIMITE_POR_EXECUCAO = 3
EMAIL_VALIDO = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
DOMINIOS_FICTICIOS = ("exemplo.com", "exemplo.com.br", "example.com", "example.org", "example.net", "empresa.com")
SUFIXOS_FICTICIOS = (".exemplo", ".example", ".test", ".invalid", ".localhost", ".local")
_enviados = 0


def configuracao():
    """Lê config_email.env (CHAVE=valor). Devolve None se o modo real não estiver ligado ou faltar campo."""
    arquivo = Path(os.environ.get("CONFIG_EMAIL", ARQUIVO))   # CONFIG_EMAIL: outro arquivo, usado nos testes
    if os.environ.get("EMAIL_REAL") == "0" or not arquivo.is_file():
        return None
    cfg = {}
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            cfg[chave.strip()] = valor.strip().strip('"').strip("'")
    # SMTP_TLS=nenhum (sem usuário/senha) só existe para testar com um servidor SMTP local
    obrigatorios = ("SMTP_HOST", "SMTP_PORTA") + (("SMTP_USUARIO", "SMTP_SENHA_APP") if cfg.get("SMTP_TLS") != "nenhum" else ())
    if any(not cfg.get(c) for c in obrigatorios):
        return None
    cfg["permitidos"] = [e.strip().lower() for e in cfg.get("DESTINOS_PERMITIDOS", "").split(",") if e.strip()]
    return cfg


def mascarar(endereco):
    """pestebubonika@gmail.com -> pes***@gmail.com"""
    nome, _, dominio = endereco.partition("@")
    return f"{nome[:3]}***@{dominio}" if dominio else "***"


def estado():
    cfg = configuracao()
    if not cfg:
        return {"modo": "simulado"}
    return {"modo": "real", "permitidos": [mascarar(e) for e in cfg["permitidos"]] or "qualquer endereço real"}


def motivo_para_simular(destino, cfg):
    """None se o destino pode receber de verdade; senão, o motivo para continuar simulado."""
    d = destino.strip().lower()
    if not EMAIL_VALIDO.match(d):
        return "não é um endereço de e-mail"
    dominio = d.rsplit("@", 1)[1]
    if dominio in DOMINIOS_FICTICIOS or dominio.endswith(SUFIXOS_FICTICIOS) or any(dominio.endswith("." + f) for f in DOMINIOS_FICTICIOS):
        return "domínio fictício"
    if cfg["permitidos"] and d not in cfg["permitidos"]:
        return "fora de DESTINOS_PERMITIDOS"
    if _enviados >= LIMITE_POR_EXECUCAO:
        return f"limite de {LIMITE_POR_EXECUCAO} e-mails reais por execução"
    return None


def enviar(destino, texto, assunto=""):
    """Tenta mandar de verdade para o destinatário que a IA escolheu.
    Devolve ("real", destino) | ("simulado", motivo) | ("falhou", erro)."""
    global _enviados
    cfg = configuracao()
    if not cfg:
        return "simulado", "modo real desligado"
    motivo = motivo_para_simular(destino, cfg)
    if motivo:
        return "simulado", motivo
    msg = EmailMessage()
    msg["From"] = cfg.get("SMTP_USUARIO") or "demo@localhost"
    msg["To"] = destino.strip()
    msg["Subject"] = "[DEMO prompt injection] " + (assunto or "Mensagem do assistente com IA")
    msg.set_content(
        "LABORATÓRIO DE DEMONSTRAÇÃO DE PROMPT INJECTION. Todos os dados desta mensagem são FICTÍCIOS.\n"
        "Este e-mail foi enviado por um assistente com IA que obedeceu a uma instrução injetada.\n\n"
        "----- conteúdo que a IA escreveu -----\n" + texto)
    porta = int(cfg["SMTP_PORTA"])
    tls = cfg.get("SMTP_TLS", "ssl" if porta == 465 else "starttls")
    try:
        if tls == "ssl":
            conexao = smtplib.SMTP_SSL(cfg["SMTP_HOST"], porta, timeout=15, context=ssl.create_default_context())
        else:
            conexao = smtplib.SMTP(cfg["SMTP_HOST"], porta, timeout=15)
        with conexao:
            if tls == "starttls":
                conexao.starttls(context=ssl.create_default_context())
            if cfg.get("SMTP_SENHA_APP"):
                conexao.login(cfg["SMTP_USUARIO"], cfg["SMTP_SENHA_APP"].replace(" ", ""))
            conexao.send_message(msg)
        _enviados += 1
        return "real", destino.strip()
    except Exception as erro:   # sem internet, senha errada etc.: a demo continua no simulado
        return "falhou", f"{type(erro).__name__}: {erro}"[:160]
