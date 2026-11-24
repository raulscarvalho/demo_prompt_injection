// Peças das telas "produto real": conversa com ferramentas recolhidas, painel escondido do apresentador e digitação.
// Usa de comum.js: $, el, semAcento, transmissão (rodarAgente/reproduzirGravado/pararAgente), criarLeitor, mostrarStatus.
"use strict";

function criarFio(fio, conversa) {
  const rolar = () => { conversa.scrollTop = conversa.scrollHeight; };
  const pensando = el("div", "pensando");
  pensando.append(el("span", "pontos", "Pensando"));
  let vazia = null;
  return {
    limpar(vaziaNo) { fio.innerHTML = ""; vazia = vaziaNo || null; if (vazia) fio.append(vazia); },
    eu(texto, anexo) {
      if (vazia) { vazia.remove(); vazia = null; }
      const b = el("div", "eu");
      if (anexo) b.append(anexo);
      b.append(document.createTextNode(texto));
      fio.append(b); rolar(); return b;
    },
    ia(texto) { const b = el("div", "ia", texto); fio.insertBefore(b, pensando.isConnected ? pensando : null); rolar(); return b; },
    no(elemento) { fio.insertBefore(elemento, pensando.isConnected ? pensando : null); rolar(); return elemento; },
    ferramenta(resumo, conteudo, erro) {
      const d = el("details", "ferr");
      const s = el("summary"); const r = el("span", erro ? "erro" : "", resumo); s.append(r); d.append(s);
      const c = el("div", "conteudo", conteudo || ""); d.append(c);
      this.no(d);
      return { definir(novo, err) { r.textContent = novo; r.className = err ? "erro" : ""; },
               conteudo(t) { c.textContent = t; }, abrir() { d.open = true; } };
    },
    pensar(on) { if (on) { fio.append(pensando); rolar(); } else pensando.remove(); },
  };
}

// painel do apresentador: engrenagem no canto ou tecla P (fora da caixa de texto)
function ligarPainel(menu) {
  document.addEventListener("keydown", (e) => {
    const digitando = /^(TEXTAREA|INPUT|SELECT)$/.test(document.activeElement.tagName);
    if (!digitando && (e.key === "p" || e.key === "P") && !e.ctrlKey && !e.metaKey) { menu.open = !menu.open; e.preventDefault(); }
    if (e.key === "Escape") menu.open = false;
  });
  document.addEventListener("click", (e) => { if (menu.open && !menu.contains(e.target)) menu.open = false; });
}

// interruptor de proteção do painel
function ligarInterruptor(botao) {
  const pintar = () => { const on = botao.classList.contains("ligada"); $(".rot", botao).textContent = on ? "Proteção ligada" : "Proteção desligada"; botao.setAttribute("aria-pressed", on); };
  botao.addEventListener("click", () => { botao.classList.toggle("ligada"); pintar(); });
  pintar();
  return { get ligada() { return botao.classList.contains("ligada"); }, definir(on) { botao.classList.toggle("ligada", !!on); pintar(); } };
}

// digita o texto na caixa como um usuário (rápido), sem enviar
function digitar(caixa, texto) {
  return new Promise((pronto) => {
    caixa.value = ""; caixa.focus();
    const passo = Math.max(1, Math.ceil(texto.length / 90));   // ~1,5 s no total
    let i = 0;
    const id = setInterval(() => {
      i = Math.min(texto.length, i + passo); caixa.value = texto.slice(0, i); caixa.scrollTop = caixa.scrollHeight;
      if (i >= texto.length) { clearInterval(id); pronto(); }
    }, 16);
  });
}

function abreviarNome(nome) {
  const p = String(nome).trim().split(/\s+/);
  return p.length > 2 ? `${p[0]} ${p.slice(1).map((x) => x[0] + ".").join(" ")}` : nome;
}
