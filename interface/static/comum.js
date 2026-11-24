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
    parar() { clearInterval(id); faixa.classList.remove("ativo"); return Math.round((Date.now() - inicio) / 1000); },
  };
}

// ---------------------------------------------------------------- painel "Bastidores da IA"
const ICONES = {
  consultar_agenda: "📅", ler_prontuario: "📂", enviar_mensagem: "✉️",
  ler_peticao: "📄", consultar_processo: "🔎", salvar_minuta: "💾", inspecionar_formatacao: "🔬",
};
function resumoArgs(f) {
  const a = f.args || {};
  const partes = Object.entries(a).map(([k, v]) => {
    let s = String(v).replace(/\s+/g, " ");
    if (s.length > 140) s = s.slice(0, 140) + "…";
    return `${k}: ${s}`;
  });
  return partes.join("  ·  ") || f.argsTexto;
}
function criarBastidores(raiz) {
  const cartoes = new Map();
  const vazio = () => { raiz.innerHTML = ""; raiz.append(el("div", "vazio", "Aqui aparece, em tempo real, cada ferramenta que a IA chamar e o que o servidor responder.")); };
  vazio();
  const rolar = () => { raiz.scrollTop = raiz.scrollHeight; };
  const tirarVazio = () => { const v = $(".vazio", raiz); if (v) v.remove(); };
  return {
    limpar() { cartoes.clear(); vazio(); },
    ferramenta(f) {
      tirarVazio();
      const c = el("div", "passo");
      const cab = el("div", "cab");
      cab.append(el("span", "icone", ICONES[f.nome] || "🛠️"), el("span", "", "IA chamou"), el("span", "nome", f.nome));
      c.append(cab, el("div", "args", resumoArgs(f)));
      raiz.append(c); cartoes.set(f, c); rolar();
    },
    retorno(f) {
      const c = cartoes.get(f); if (!c) return;
      let r = $(".retorno", c);
      if (!r) { r = el("div", "retorno"); c.append(r); }
      r.textContent = "↳ " + f.retorno;
      if (/^(ACESSO NEGADO|BLOQUEADO)/.test(f.retorno) && !$(".selo-barrado", c)) { c.classList.add("bom"); $(".cab", c).append(el("span", "selo-barrado", "🛡️ barrado pelo servidor")); }
      if (/já chamou esta ferramenta/.test(f.retorno)) c.classList.add("aviso");
      rolar();
    },
    servidor(b, classe, icone, titulo) {
      tirarVazio();
      const c = el("div", "passo servidor " + (classe || ""));
      const cab = el("div", "cab");
      cab.append(el("span", "icone", icone || "🖥️"), el("span", "", titulo || "Servidor MCP"));
      c.append(cab, el("div", "texto", b.texto));
      const corpo = el("div", "corpo"); c.append(corpo);
      raiz.append(c); cartoes.set(b, c); rolar();
    },
    corpo(b) { const c = cartoes.get(b); if (c) { $(".corpo", c).textContent = b.corpo.join("\n"); rolar(); } },
    nota(texto, classe, icone) {
      tirarVazio();
      const c = el("div", "passo " + (classe || ""));
      const cab = el("div", "cab"); cab.append(el("span", "icone", icone || "ℹ️"), el("span", "texto", texto));
      c.append(cab); raiz.append(c); rolar();
    },
  };
}

// ---------------------------------------------------------------- controles comuns
function ligarProtecao(botao, aoMudar) {
  const pintar = () => {
    const on = botao.classList.contains("ligada");
    $(".rot", botao).textContent = on ? "PROTEÇÃO: LIGADA" : "PROTEÇÃO: DESLIGADA";
    $(".bolinha", botao).textContent = on ? "🛡️" : "⚠️";
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
    if (!s.ollama) { alvo.textContent = "⚠ Ollama não respondeu. Abra o Ollama antes da demo."; return; }
    const m = seletorModelo.value;
    alvo.textContent = s.carregados.includes(m) ? `● ${m} carregado na memória` : `○ ${m} ainda não carregado (a 1ª resposta demora mais)`;
  } catch (e) { alvo.textContent = "⚠ servidor da interface fora do ar"; }
}

async function preencherGravados(select, prefixos) {
  try {
    const lista = await (await fetch("/api/gravados")).json();
    for (const nome of lista.filter((n) => prefixos.some((p) => n.startsWith(p)))) {
      const o = el("option", "", nome.replace(/\.txt$/, "")); o.value = nome; select.append(o);
    }
  } catch (e) { /* sem gravados */ }
}
