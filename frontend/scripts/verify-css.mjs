// Verify built CSS is free of wide-gamut color functions that Chrome < 111
// cannot parse (oklch / oklab / lab / color-mix). Run after `npm run build`:
//   npm run verify:css
//
// Tailwind v4 emits some color-mix() declarations inside
//   @supports (color: color-mix(in lab, red, red)) { ... }
// with an unconditional hex fallback right before the block. Chrome 85 skips
// those guarded blocks and uses the fallback, so they are counted but do not
// fail the check. Any UNguarded occurrence fails.
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distAssets = path.join(__dirname, '..', 'dist', 'assets');

const FORBIDDEN = [
  { needle: 'oklch(', allowGuarded: false },
  { needle: 'oklab(', allowGuarded: false },
  { needle: 'lab(', allowGuarded: false, notPrecededBy: ['oklab'] },
];
const GUARDED_RE = /@supports \(color:color-mix\([^)]*\)\)\{/g;

function findGuardRegions(css) {
  const regions = [];
  let m;
  GUARDED_RE.lastIndex = 0;
  while ((m = GUARDED_RE.exec(css))) {
    let depth = 1;
    let i = m.index + m[0].length;
    while (i < css.length && depth > 0) {
      if (css[i] === '{') depth++;
      else if (css[i] === '}') depth--;
      i++;
    }
    regions.push([m.index, i]);
    GUARDED_RE.lastIndex = i;
  }
  return regions;
}

if (!fs.existsSync(distAssets)) {
  console.error('[verify:css] dist/assets not found — run `npm run build` first.');
  process.exit(1);
}

const cssFiles = fs.readdirSync(distAssets).filter((f) => f.endsWith('.css'));

if (cssFiles.length === 0) {
  console.error('[verify:css] no .css files in dist/assets.');
  process.exit(1);
}

let failures = 0;
let totalGuarded = 0;

for (const file of cssFiles) {
  const css = fs.readFileSync(path.join(distAssets, file), 'utf8');
  const guards = findGuardRegions(css);
  const inGuard = (pos) => guards.some(([a, b]) => pos >= a && pos < b);

  const check = (needle, { allowGuarded, notPrecededBy = [] }) => {
    let idx = css.indexOf(needle);
    let hits = 0;
    let guardedHits = 0;
    while (idx !== -1) {
      if (notPrecededBy.some((pre) => css.slice(Math.max(0, idx - pre.length), idx) === pre)) {
        idx = css.indexOf(needle, idx + needle.length);
        continue;
      }
      if (allowGuarded && inGuard(idx)) {
        guardedHits++;
      } else {
        hits++;
        if (failures + hits <= 20) {
          const ctx = css.slice(Math.max(0, idx - 20), idx + 80).replace(/\s+/g, ' ');
          console.error(`[verify:css] FAIL ${file}: unguarded "${needle}"\n  ...${ctx}...`);
        }
      }
      idx = css.indexOf(needle, idx + needle.length);
    }
    return { hits, guardedHits };
  };

  for (const fn of FORBIDDEN) {
    const { hits } = check(fn.needle, { allowGuarded: fn.allowGuarded, notPrecededBy: fn.notPrecededBy });
    failures += hits;
  }
  // color-mix: allowed only inside @supports guards (Chrome 85 uses hex fallback)
  const { hits, guardedHits } = check('color-mix(', { allowGuarded: true });
  failures += hits;
  totalGuarded += guardedHits;
}

if (failures > 0) {
  console.error(`[verify:css] ${failures} unguarded wide-gamut color function(s) found.`);
  process.exit(1);
}

console.log(
  `[verify:css] OK — ${cssFiles.length} css file(s) checked. ` +
  `No unguarded oklch/oklab/lab/color-mix. ${totalGuarded} color-mix occurrence(s) inside @supports guards (Chrome 85 uses hex fallbacks).`,
);
