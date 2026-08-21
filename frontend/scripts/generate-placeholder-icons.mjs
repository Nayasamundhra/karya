#!/usr/bin/env node
/**
 * Generates placeholder PWA icons with zero external dependencies (a raw PNG
 * encoder over Node's built-in `zlib`), so the manifest has real, valid image
 * files to point at without pulling in an image-processing library for three
 * flat-color squares.
 *
 * These are deliberately plain — a solid brand-colour square with a lighter
 * inset mark — and are NOT final branding. Replace `public/icons/*.png` with
 * real designed assets before a production launch; re-run this script only
 * if you need placeholders again (`node scripts/generate-placeholder-icons.mjs`).
 */
import { deflateSync } from 'node:zlib'
import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const outDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons')
mkdirSync(outDir, { recursive: true })

const BG = [15, 23, 42] // slate-900 — matches manifest.theme_color #0f172a
const MARK = [99, 102, 241] // indigo-500 accent

function crc32(buf) {
  let c
  const table = crc32.table ?? (crc32.table = (() => {
    const t = new Uint32Array(256)
    for (let n = 0; n < 256; n++) {
      c = n
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
      t[n] = c
    }
    return t
  })())
  let crc = 0xffffffff
  for (let i = 0; i < buf.length; i++) crc = table[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const typeBuf = Buffer.from(type, 'ascii')
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length, 0)
  const crcBuf = Buffer.alloc(4)
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0)
  return Buffer.concat([len, typeBuf, data, crcBuf])
}

/** `inset` (0..0.5) is how far the lighter mark sits from each edge; `maskable`
 * keeps the mark well within the safe zone Android applies when it clips to
 * a shape. */
function drawPng(size, { maskable = false } = {}) {
  const rowBytes = 1 + size * 3 // filter byte + RGB per pixel
  const raw = Buffer.alloc(rowBytes * size)
  const inset = maskable ? 0.3 : 0.22
  const lo = Math.round(size * inset)
  const hi = Math.round(size * (1 - inset))

  for (let y = 0; y < size; y++) {
    const rowStart = y * rowBytes
    raw[rowStart] = 0 // filter: none
    for (let x = 0; x < size; x++) {
      const inMark = x >= lo && x < hi && y >= lo && y < hi
      const [r, g, b] = inMark ? MARK : BG
      const px = rowStart + 1 + x * 3
      raw[px] = r
      raw[px + 1] = g
      raw[px + 2] = b
    }
  }

  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 2 // color type: RGB
  ihdr[10] = 0
  ihdr[11] = 0
  ihdr[12] = 0

  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
  return Buffer.concat([
    signature,
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

const targets = [
  { name: 'icon-192.png', size: 192 },
  { name: 'icon-512.png', size: 512 },
  { name: 'icon-maskable-512.png', size: 512, maskable: true },
]

for (const t of targets) {
  writeFileSync(join(outDir, t.name), drawPng(t.size, { maskable: t.maskable }))
  console.log(`wrote public/icons/${t.name}`)
}
