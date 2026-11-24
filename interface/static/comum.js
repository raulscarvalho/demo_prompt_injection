// Código comum às telas: transmissão da saída do agente, leitura das linhas, cronômetro e painel "Bastidores da IA".
"use strict";

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const el = (tag, classe, texto) => {
  const n = document.createElement(tag);
  if (classe) n.className = classe;
  if (texto !== undefined) n.textContent = texto;
  return n;
};
const semAcento = (t) => String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// ---------------------------------------------------------------- transmissão
let controlador = null;

async function transmitir(url, opcoes, aoLinha) {
  controlador = new AbortController();
  const resposta = await fetch(url, { ...opcoes, signal: controlador.signal });
  if (!resposta.ok) {
    let msg = resposta.statusText;
    try { msg = (await resposta.json()).erro || msg; } catch (e) { /* sem corpo */ }
    throw new Error(msg);
  }
  const leitor = resposta.body.getReader();
  const decodificador = new TextDecoder("utf-8");
  let resto = "";
  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    resto += decodificador.decode(value, { stream: true });
    let i;
    while ((i = resto.indexOf("\n")) >= 0) {
      const linha = resto.slice(0, i);
      resto = resto.slice(i + 1);
      if (linha.trim()) aoLinha(JSON.parse(linha));
    }
  }
}

function rodarAgente(pedido, aoLinha) {
  return transmitir("/api/rodar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(pedido) }, aoLinha);
}
function reproduzirGravado(arquivo, aoLinha) {
  return transmitir("/api/gravado?arquivo=" + encodeURIComponent(arquivo), {}, aoLinha);
}
async function pararAgente() {
  try { await fetch("/api/parar", { method: "POST" }); } catch (e) { /* ignora */ }
  if (controlador) controlador.abort();
}
async function postar(url, corpo) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo || {}) });
  return r.json();
}

// ---------------------------------------------------------------- leitura da saída do agente
// Transforma as linhas do terminal (as mesmas da demo por linha de comando) em eventos para a tela.
function criarLeitor(ao) {
  let bloco = null, ultimaFerramenta = null, caixa = null;
  const emitir = (tipo, dados) => ao(tipo, dados);
  return function (l) {
    if (caixa) {
      if (l.startsWith("│")) { caixa.linhas.push(l.replace(/^│ ?/, "")); return; }
      if (l.startsWith("└")) { emitir("caixa", caixa); caixa = null; return; }
    }
    let m;
    if (l.startsWith("[agente] ")) { bloco = null; emitir("info", { texto: l.slice(9) }); }
    else if ((m = l.match(/^\[(chat|usuário)\] ([\s\S]*)$/))) { bloco = null; emitir("pedido", { texto: m[2] }); }
    else if ((m = l.match(/^\[tool\] (\w+)\(([\s\S]*)\)$/))) {
      ultimaFerramenta = { nome: m[1], argsTexto: m[2], args: lerJson(m[2]), retorno: "" };
      bloco = ultimaFerramenta;
      emitir("ferramenta", ultimaFerramenta);
    }
    else if (l.startsWith("  ↳ ")) {
      if (ultimaFerramenta) {
        ultimaFerramenta.retorno = l.slice(4);
        bloco = ultimaFerramenta;
        emitir("retorno", ultimaFerramenta);
      }
    }
    else if (l.startsWith("[SERVIDOR] ")) {
      bloco = { tipo: "servidor", texto: l.slice(11), corpo: [], ferramenta: ultimaFerramenta };
      emitir("servidor", bloco);
    }
    else if (l.startsWith("┌─ ")) { bloco = null; caixa = { titulo: l.slice(3).replace(/\s*─+\s*$/, "").trim(), linhas: [] }; }
    else if (l.startsWith(" ALERTA:")) {
      bloco = { tipo: "alerta", texto: l.trim().replace(/^ALERTA:\s*/, "").replace(/:\s*$/, ""), corpo: [] };
      emitir("alerta", bloco);
    }
    else if (l.startsWith(" VAZAMENTO:")) { bloco = null; emitir("vazamento", { texto: l.trim().replace(/^VAZAMENTO:\s*/, "") }); }
    else if (l.startsWith("[defesa] ")) { bloco = null; emitir("defesa", { texto: l.slice(9) }); }
    else if (/^\s/.test(l) && l.trim() && bloco) {
      if (bloco === ultimaFerramenta) { bloco.retorno += "\n" + l.trim(); emitir("retorno", bloco); }
      else { bloco.corpo.push(l.trim().replace(/^"|"$/g, "")); emitir(bloco.tipo + "+", bloco); }
    }
    else if (l.trim()) { emitir("outro", { texto: l }); }
  };
}
function lerJson(texto) {
  try { return JSON.parse(texto); } catch (e) {
    const r = {};
    for (const m of texto.matchAll(/"(\w+)":\s*"((?:[^"\\]|\\.)*)/g)) r[m[1]] = m[2].replace(/\\n/g, "\n").replace(/\\"/g, '"');
    return r;
  }
}

// ---------------------------------------------------------------- cronômetro
function criarCronometro(faixa) {
  let id = null, inicio = 0;
  const relogio = $(".relogio", faixa), rotulo = $(".rotulo", faixa);
  return {
    iniciar(texto) {
      inicio = Date.now(); rotulo.textContent = texto || "IA pensando...";
      faixa.classList.add("ativo");
      const passo = () => { const s = Math.floor((Date.now() - inicio) / 1000); relogio.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
      passo(); id = setInterval(passo, 250);
    },
    etapa(texto) { rotulo.textContent = texto; },
    parar() { clearInterval(id); faixa.classList.remove("ativo"); return Math.round((Date.now() - inicio) / 1000); },
  };
}

// ---------------------------------------------------------------- painel "Bastidores da IA" (compacto: uma linha por passo, clique abre o detalhe)
const ICONES = {
  consultar_agenda: "📅", ler_prontuario: "📂", enviar_mensagem: "✉️",
  ler_peticao: "📄", consultar_processo: "🔎", salvar_minuta: "💾", inspecionar_formatacao: "🔬",
};
function resumoArgs(f) {
  const a = f.args || {};
  return Object.values(a).map((v) => String(v).replace(/\s+/g, " ")).join(" · ") || f.argsTexto;
}
function criarBastidores(raiz) {
  const passos = new Map();
  const vazio = () => { raiz.innerHTML = ""; raiz.append(el("div", "vazio", "Cada ferramenta que a IA chamar aparece aqui.")); };
  vazio();
  const rolar = () => { raiz.scrollTop = raiz.scrollHeight; };
  function linha(icone, principal, secundario, selo, classe) {
    const v = $(".vazio", raiz); if (v) v.remove();
    const d = el("details", "passo " + (classe || ""));
    const s = el("summary");
    const l1 = el("span", "linha1");
    if (principal) l1.append(principal);
    if (secundario) l1.append(el("span", "args", " " + secundario));
    s.append(el("span", "icone", icone), l1, el("span", "selo", selo || ""));
    d.append(s, el("div", "detalhe"));
    raiz.append(d); rolar();
    return d;
  }
  const definir = (d, classe, selo) => { d.className = "passo " + classe; $(".selo", d).textContent = selo; };
  return {
    limpar() { passos.clear(); vazio(); },
    ferramenta(f) {
      const d = linha(ICONES[f.nome] || "🛠️", el("span", "nome", f.nome), resumoArgs(f), "");
      $(".detalhe", d).textContent = JSON.stringify(f.args, null, 1);
      passos.set(f, d);
    },
    retorno(f) {
      const d = passos.get(f); if (!d) return;
      $(".detalhe", d).textContent = JSON.stringify(f.args, null, 1) + "\n\n↳ " + f.retorno;
      if (/^(ACESSO NEGADO|BLOQUEADO)/.test(f.retorno)) definir(d, "bom", "barrado");
      else if (/já chamou esta ferramenta/.test(f.retorno)) definir(d, "aviso", "repetida");
    },
    servidor(b, classe, icone, titulo, selo) {
      const d = linha(icone || "🖥️", el("b", "", titulo || "Servidor"), "", selo || "servidor", classe);
      $(".detalhe", d).textContent = b.texto;
      passos.set(b, d);
    },
    marcar(f, classe, selo, extra) {   // a resposta do servidor marca a própria linha da ferramenta
      const d = passos.get(f); if (!d) return false;
      definir(d, classe, selo);
      if (extra) $(".detalhe", d).textContent += "\n\n[servidor] " + extra;
      return true;
    },
    corpo(b) { const d = passos.get(b); if (d) $(".detalhe", d).textContent = b.texto + "\n\n" + b.corpo.join("\n"); },
    nota(texto, classe, icone, selo) { const d = linha(icone || "·", texto, "", selo || "", classe); $(".detalhe", d).remove(); },
  };
}
function ligarRecolher(botao, cartao, grade) {
  botao.addEventListener("click", () => {
    const fechado = cartao.classList.toggle("recolhido");
    grade.classList.toggle("sem-bastidores", fechado);
    botao.textContent = fechado ? "‹" : "›";
    botao.title = fechado ? "Mostrar os bastidores da IA" : "Recolher os bastidores da IA";
  });
}

// ---------------------------------------------------------------- controles comuns
function ligarProtecao(botao, aoMudar) {
  const pintar = () => {
    const on = botao.classList.contains("ligada");
    $(".rot", botao).textContent = on ? "Proteção ligada" : "Proteção desligada";
    botao.setAttribute("aria-pressed", on);
  };
  botao.addEventListener("click", () => { botao.classList.toggle("ligada"); pintar(); aoMudar && aoMudar(botao.classList.contains("ligada")); });
  pintar();
  return {
    get ligada() { return botao.classList.contains("ligada"); },
    definir(on) { botao.classList.toggle("ligada", !!on); pintar(); },
  };
}

async function mostrarStatus(alvo, seletorModelo) {
  try {
    const s = await (await fetch("/api/status")).json();
    if (!s.ollama) { alvo.textContent = "Ollama fechado: abra o Ollama pelo menu Iniciar"; return; }
    const m = seletorModelo.value;
    alvo.textContent = s.carregados.includes(m) ? `● ${m} pronto` : `○ ${m} não carregado`;
  } catch (e) { alvo.textContent = "Interface fora do ar: suba a interface de novo"; }
}

async function mostrarEmail(alvo) {
  try {
    const e = await (await fetch("/api/email")).json();
    if (e.modo === "real") {
      alvo.textContent = "E-mail: REAL";
      alvo.title = "config_email.env preenchido: endereços reais recebem de verdade (fictícios continuam simulados). Permitidos: "
        + (Array.isArray(e.permitidos) ? e.permitidos.join(", ") : e.permitidos);
      alvo.classList.add("real");
    } else { alvo.textContent = "E-mail: simulado"; alvo.title = "Nada é enviado de verdade."; }
  } catch (err) { alvo.textContent = ""; }
}

async function preencherGravados(select, prefixos) {
  try {
    const lista = await (await fetch("/api/gravados")).json();
    for (const nome of lista.filter((n) => prefixos.some((p) => n.startsWith(p)))) {
      const o = el("option", "", nome.replace(/\.txt$/, "")); o.value = nome; select.append(o);
    }
  } catch (e) { /* sem gravados */ }
}
