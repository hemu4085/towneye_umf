#!/usr/bin/env node
/** Copy demo address index into frontend/public for Vercel CDN (no API proxy). */
import { copyFileSync, existsSync, mkdirSync, statSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = join(root, 'demo-data/gold/arlington-ma/address-index.json');
const destDir = join(root, 'frontend/public/address-index');
const dest = join(destDir, 'arlington-ma.json');

if (!existsSync(src)) {
  console.warn(`WARN: skip address-index copy — missing ${src}`);
  process.exit(0);
}

mkdirSync(destDir, { recursive: true });
copyFileSync(src, dest);
console.log(`OK: ${dest} (${statSync(dest).size} bytes)`);
