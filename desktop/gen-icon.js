// Gera icon.png (256px) e icon-tray.png (32px) sem dependencias.
const fs = require("fs");
const zlib = require("zlib");

function crc32(buf) {
  let c, crc = 0xffffffff;
  for (let n = 0; n < buf.length; n++) {
    c = (crc ^ buf[n]) & 0xff;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}

// Forma em um espaco 32x32 (igual ao favicon do app)
function inRoundRect(x, y, rx, ry, w, h, r) {
  const cx = Math.min(Math.max(x, rx + r), rx + w - r), cy = Math.min(Math.max(y, ry + r), ry + h - r);
  return (x - cx) ** 2 + (y - cy) ** 2 <= r * r && x >= rx && x <= rx + w && y >= ry && y <= ry + h;
}
function sample(x, y) {
  if (!inRoundRect(x, y, 0, 0, 32, 32, 8)) return null;
  const white = (x - 11) ** 2 + (y - 14) ** 2 <= 9 || (x - 21) ** 2 + (y - 14) ** 2 <= 9 || inRoundRect(x, y, 9, 21, 14, 3, 1.5);
  if (white) return [255, 255, 255];
  const t = (x + y) / 64; // gradiente diagonal roxo -> azul
  return [124 + (79 - 124) * t, 108 + (195 - 108) * t, 242 + (247 - 242) * t];
}

function render(size) {
  const ss = 4, raw = Buffer.alloc(size * (size * 4 + 1));
  for (let py = 0; py < size; py++) {
    raw[py * (size * 4 + 1)] = 0;
    for (let px = 0; px < size; px++) {
      let r = 0, g = 0, b = 0, a = 0;
      for (let sy = 0; sy < ss; sy++) for (let sx = 0; sx < ss; sx++) {
        const c = sample(((px + (sx + 0.5) / ss) / size) * 32, ((py + (sy + 0.5) / ss) / size) * 32);
        if (c) { r += c[0]; g += c[1]; b += c[2]; a++; }
      }
      const o = py * (size * 4 + 1) + 1 + px * 4;
      if (a) { raw[o] = r / a; raw[o + 1] = g / a; raw[o + 2] = b / a; }
      raw[o + 3] = (a / (ss * ss)) * 255;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4); ihdr[8] = 8; ihdr[9] = 6;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}

fs.writeFileSync(__dirname + "/icon.png", render(256));
fs.writeFileSync(__dirname + "/icon-tray.png", render(32));
console.log("icones gerados");
