// Espera o servidor Python do módulo subir e abre a interface do Piphin LLM (servida por ele).
const $ = (s) => document.querySelector(s);
const MSG = {
  python: ["Python não encontrado", "O Piphin LLM precisa do Python 3.9 ou mais novo. Instale em python.org marcando \"Add python.exe to PATH\" e tente de novo."],
  timeout: ["O servidor não respondeu", "Veja o log em %APPDATA%\\Piphin Hub\\module-data\\llm-local\\server.log e tente de novo."],
  crashed: ["O servidor parou várias vezes", "Veja o log em %APPDATA%\\Piphin Hub\\module-data\\llm-local\\server.log e tente de novo."],
};

async function poll() {
  const r = await piphin.invoke("status").catch(() => null);
  const s = r && r.ok ? r.data : null;
  if (s && s.ready) return location.replace(s.base + "/");
  if (s && MSG[s.error]) {
    $("#title").textContent = MSG[s.error][0];
    $("#text").textContent = MSG[s.error][1];
    $("#spin").hidden = true;
    $("#retry").hidden = false;
    return;
  }
  setTimeout(poll, 400);
}

$("#retry").onclick = async () => {
  $("#retry").hidden = true;
  $("#spin").hidden = false;
  $("#title").textContent = "Iniciando o Piphin LLM...";
  $("#text").textContent = "Ligando o servidor local.";
  await piphin.invoke("retry");
  poll();
};
piphin.on("open-url", (url) => window.open(url));
poll();
