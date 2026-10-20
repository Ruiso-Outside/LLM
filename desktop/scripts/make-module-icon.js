// Desenha o ícone do Piphin LLM como módulo do Piphin Hub (mesma família do ícone do Hub):
//   desktop/module/icon.png (256 px), usado pelo make-module.js
// Uso: npx electron scripts/make-module-icon.js   (usa o próprio Electron para desenhar; sem dependências)
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const path = require("path");

const OUT = path.join(__dirname, "..", "module", "icon.png");

app.whenReady().then(async () => {
  const win = new BrowserWindow({ show: false, webPreferences: { offscreen: true } });
  await win.loadURL("about:blank");
  const data = await win.webContents.executeJavaScript(`(() => {
    const s = 256, c = document.createElement("canvas"); c.width = c.height = s;
    const g = c.getContext("2d");
    // fundo: quadrado arredondado escuro com um brilho ciano no canto
    g.beginPath(); g.roundRect(8, 8, 240, 240, 56);
    const bg = g.createLinearGradient(0, 0, s, s); bg.addColorStop(0, "#0b2a35"); bg.addColorStop(.55, "#0d1222"); bg.addColorStop(1, "#0b0a12");
    g.fillStyle = bg; g.fill();
    g.save(); g.clip();
    const glow = g.createRadialGradient(70, 60, 0, 70, 60, 170); glow.addColorStop(0, "rgba(34,211,238,.28)"); glow.addColorStop(1, "rgba(34,211,238,0)");
    g.fillStyle = glow; g.fillRect(0, 0, s, s);
    const glow2 = g.createRadialGradient(210, 220, 0, 210, 220, 150); glow2.addColorStop(0, "rgba(168,85,247,.25)"); glow2.addColorStop(1, "rgba(168,85,247,0)");
    g.fillStyle = glow2; g.fillRect(0, 0, s, s);
    g.restore();
    g.lineWidth = 3; g.strokeStyle = "rgba(34,211,238,.5)"; g.beginPath(); g.roundRect(8, 8, 240, 240, 56); g.stroke();

    // balão de conversa com rabicho, contorno em neon (ciano -> violeta)
    const grad = g.createLinearGradient(52, 58, 204, 200); grad.addColorStop(0, "#22d3ee"); grad.addColorStop(1, "#a855f7");
    g.beginPath();
    const x = 50, y = 58, w = 156, h = 118, r = 34;
    g.moveTo(x + r, y); g.lineTo(x + w - r, y); g.quadraticCurveTo(x + w, y, x + w, y + r);
    g.lineTo(x + w, y + h - r); g.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    g.lineTo(x + 92, y + h); g.lineTo(x + 62, y + h + 30); g.lineTo(x + 64, y + h);
    g.lineTo(x + r, y + h); g.quadraticCurveTo(x, y + h, x, y + h - r);
    g.lineTo(x, y + r); g.quadraticCurveTo(x, y, x + r, y); g.closePath();
    const fill = g.createLinearGradient(0, y, 0, y + h); fill.addColorStop(0, "rgba(34,211,238,.16)"); fill.addColorStop(1, "rgba(168,85,247,.10)");
    g.fillStyle = fill; g.fill();
    g.shadowColor = "#22d3ee"; g.shadowBlur = 18; g.lineWidth = 9; g.lineJoin = "round"; g.strokeStyle = grad; g.stroke();
    g.shadowBlur = 0;

    // faísca de IA (estrela de 4 pontas) e uma menor ao lado
    function spark(cx, cy, R, rr, color) {
      g.beginPath();
      for (let i = 0; i < 8; i++) { const a = -Math.PI / 2 + i * Math.PI / 4, d = i % 2 ? rr : R; g.lineTo(cx + Math.cos(a) * d, cy + Math.sin(a) * d); }
      g.closePath(); g.fillStyle = color; g.shadowColor = color; g.shadowBlur = 16; g.fill(); g.shadowBlur = 0;
    }
    spark(112, 116, 34, 9, "#ecfeff");
    spark(158, 92, 14, 4, "#a5f3fc");
    // três pontinhos de "digitando"
    for (const [dx, col] of [[146, "#22d3ee"], [164, "#67e8f9"], [182, "#c084fc"]]) {
      g.beginPath(); g.arc(dx, 142, 6.5, 0, Math.PI * 2); g.fillStyle = col; g.shadowColor = col; g.shadowBlur = 10; g.fill(); g.shadowBlur = 0;
    }
    return c.toDataURL("image/png");
  })()`);
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, Buffer.from(data.split(",")[1], "base64"));
  console.log("ícone:", OUT);
  app.exit(0);
});
