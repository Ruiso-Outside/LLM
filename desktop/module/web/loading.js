// Espera o servidor Python do módulo subir e abre a interface do Piphin LLM (servida por ele).
const $ = (s) => document.querySelector(s);
const MSG = {
  python: ["Python não encontrado", "O Arasaka Mikoshi precisa do Python 3.9 ou mais novo. Instale em python.org marcando \"Add python.exe to PATH\" e tente de novo."],
  timeout: ["O servidor não respondeu", "Veja o log em %APPDATA%\\Arasaka Central\\module-data\\llm-local\\server.log e tente de novo."],
  home: ["Pasta dos modelos indisponível", "A pasta %HOME% está num disco que não está conectado ou montado. Conecte o disco e clique em Tentar de novo, ou escolha outra pasta."],
  crashed: ["O servidor parou várias vezes", "Veja o log em %APPDATA%\\Arasaka Central\\module-data\\llm-local\\server.log e tente de novo."],
};

async function poll() {
  const r = await piphin.invoke("status").catch(() => null);
  const s = r && r.ok ? r.data : null;
  if (s && s.ready) return location.replace(s.base + "/");
  if (s && MSG[s.error]) {
    $("#title").textContent = MSG[s.error][0];
    $("#text").textContent = MSG[s.error][1].replace("%HOME%", s.home || "");
    $("#spin").hidden = true;
    $("#retry").hidden = false;
    $("#home").hidden = s.error !== "home";
    return;
  }
  setTimeout(poll, 400);
}

$("#retry").onclick = async () => {
  $("#retry").hidden = true;
  $("#home").hidden = true;
  $("#spin").hidden = false;
  $("#title").textContent = "Iniciando o Arasaka Mikoshi...";
  $("#text").textContent = "Ligando o servidor local.";
  await piphin.invoke("retry");
  poll();
};
// outra pasta para os modelos (a pasta indisponível continua guardada; dá para voltar a ela depois)
$("#home").onclick = async () => {
  const r = await piphin.invoke("choose-home").catch(() => null);
  if (r && r.ok && r.data) { $("#retry").hidden = true; $("#home").hidden = true; $("#spin").hidden = false; poll(); }
};
piphin.on("open-url", (url) => window.open(url));
poll();
