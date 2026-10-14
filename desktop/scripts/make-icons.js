// Gera os ícones do app a partir de uma imagem (PNG/JPG/WebP), recortada em círculo:
//   icon.png (256), icon-tray.png (32), icon.ico (16-256) e ../app/web/logo.png (128).
// Uso: npx electron scripts/make-icons.js <imagem>   (usa o próprio Electron para ler WebP; sem dependências)
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const path = require("path");

const src = process.argv.find(a => /\.(png|jpe?g|webp)$/i.test(a));
const DESK = path.join(__dirname, "..");

function ico(pngs) {
  // ICO com entradas PNG (aceito desde o Windows Vista)
  const head = Buffer.alloc(6 + 16 * pngs.length);
  head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(pngs.length, 4);
  let off = head.length;
  pngs.forEach(({ size, buf }, i) => {
    const e = 6 + i * 16;
    head.writeUInt8(size >= 256 ? 0 : size, e); head.writeUInt8(size >= 256 ? 0 : size, e + 1);
    head.writeUInt16LE(1, e + 4); head.writeUInt16LE(32, e + 6);
    head.writeUInt32LE(buf.length, e + 8); head.writeUInt32LE(off, e + 12);
    off += buf.length;
  });
  return Buffer.concat([head, ...pngs.map(p => p.buf)]);
}

app.whenReady().then(async () => {
  if (!src || !fs.existsSync(src)) { console.error("informe a imagem de origem"); app.exit(1); return; }
  const mime = /\.webp$/i.test(src) ? "image/webp" : /\.png$/i.test(src) ? "image/png" : "image/jpeg";
  const url = `data:${mime};base64,` + fs.readFileSync(src).toString("base64");
  const win = new BrowserWindow({ show: false, webPreferences: { offscreen: true } });
  await win.loadURL("about:blank");
  const sizes = [16, 24, 32, 48, 64, 128, 256];
  const out = await win.webContents.executeJavaScript(`(async () => {
    const img = new Image(); img.src = ${JSON.stringify(url)}; await img.decode();
    const res = {};
    for (const s of ${JSON.stringify(sizes)}) {
      const c = document.createElement("canvas"); c.width = c.height = s;
      const g = c.getContext("2d"); g.imageSmoothingQuality = "high";
      // recorte circular um pouco para dentro: tira a névoa branca das bordas da arte
      const side = Math.min(img.width, img.height), crop = side * 0.84;
      const sx = (img.width - crop) / 2, sy = (img.height - crop) / 2 - side * 0.035;
      g.beginPath(); g.arc(s / 2, s / 2, s / 2, 0, Math.PI * 2); g.clip();
      g.drawImage(img, sx, sy, crop, crop, 0, 0, s, s);
      res[s] = c.toDataURL("image/png");
    }
    return res;
  })()`);
  const png = s => Buffer.from(out[s].split(",")[1], "base64");
  fs.writeFileSync(path.join(DESK, "icon.png"), png(256));
  fs.writeFileSync(path.join(DESK, "icon-tray.png"), png(32));
  fs.writeFileSync(path.join(DESK, "icon.ico"), ico(sizes.map(s => ({ size: s, buf: png(s) }))));
  fs.writeFileSync(path.join(DESK, "..", "app", "web", "logo.png"), png(128));
  console.log("ícones gerados:", sizes.join(", "));
  app.exit(0);
});
