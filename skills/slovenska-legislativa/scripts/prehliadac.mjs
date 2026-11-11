// Cita stranky, ktore obycajne stiahnutie ani skryty prehliadac neprecitaju (Slov-Lex eLegislativa je
// vo vnorenom ramci, NR SR ma ochranu proti robotom). Otvori bezne okno Edge mimo obrazovky s cistym
// docasnym profilom (ziadne prihlasenia, ziadne tvoje data), stranku nacita, pripadne vyhlada alebo
// klikne, vypise text aj z vnorenych ramcov a okno zavrie.
//
//   node prehliadac.mjs <url>                      text stranky
//   node prehliadac.mjs <url> --hladaj "kratom"    napise text do prveho vyhladavacieho pola a potvrdi
//   node prehliadac.mjs <url> --klik "Text odkazu" klikne na odkaz alebo tlacidlo s tymto textom
//   node prehliadac.mjs <url> --find slovo         z vystupu len riadky so slovom a okolie
//   node prehliadac.mjs <url> --links              prida zoznam odkazov
//   node prehliadac.mjs <url> --wait 9000          cakanie po kazdom kroku v ms (predvolene 7000)
//
// POVOLENE SU LEN STRANKY STATU A LEGISLATIVY (zoznam ALLOW). Ina adresa sa odmietne.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const ALLOW = [/(^|\.)slov-lex\.sk$/, /(^|\.)nrsr\.sk$/, /(^|\.)gov\.sk$/, /(^|\.)prezident\.sk$/, /(^|\.)ustavnysud\.sk$/, /(^|\.)eur-lex\.europa\.eu$/];
const argv = process.argv.slice(2);
const url = argv[0];
const opt = k => { const i = argv.indexOf(k); return i > 0 ? argv[i + 1] : null; };
const flag = k => argv.includes(k);
if (!url) { console.error('Pouzitie: node prehliadac.mjs <url> [--hladaj text] [--klik text] [--find slovo] [--links] [--wait ms]'); process.exit(2); }
let host = '';
try { host = new URL(url).hostname.toLowerCase(); } catch { console.error('Zla adresa.'); process.exit(2); }
if (!ALLOW.some(r => r.test(host))) { console.error(`Adresa ${host} nie je na zozname povolenych stranok statu a legislativy. Tento nastroj je len na ne.`); process.exit(3); }

// Chrome prvy: Edge s cistym profilom na slov-lex.sk casto vyprsi (ERR_TIMED_OUT), Chrome nie.
const EXE = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(existsSync);
if (!EXE) { console.error('Nenasiel som Edge ani Chrome.'); process.exit(2); }
const WAIT = +(opt('--wait') || 7000), PORT = 9700 + Math.floor(Math.random() * 250);
const profile = mkdtempSync(join(tmpdir(), 'legis-'));
const child = spawn(EXE, ['--window-position=-2600,-2600', '--window-size=1400,1000', '--no-first-run', '--no-default-browser-check',
  '--disable-extensions', '--lang=sk-SK', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const done = code => { try { child.kill(); } catch {} setTimeout(() => { try { rmSync(profile, { recursive: true, force: true }); } catch {} process.exit(code); }, 400); };
setTimeout(() => { console.error('Vyprsal cas (120 s).'); done(4); }, 120000);

let target;
for (let i = 0; i < 80 && !target; i++) { try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find(x => x.type === 'page'); } catch {} if (!target) await sleep(150); }
if (!target) { console.error('Prehliadac sa nespustil.'); done(4); }
const ws = new WebSocket(target.webSocketDebuggerUrl); await new Promise(r => (ws.onopen = r));
let id = 0; const pend = new Map();
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
const send = (method, params = {}) => new Promise(res => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async x => (await send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true })).result?.result?.value;

// pomocne funkcie v stranke: vsetky dokumenty (hlavny + vnorene ramce z rovnakej domeny)
const LIB = `const docs = () => { const out = [document]; for (const f of document.querySelectorAll('iframe')) { try { if (f.contentDocument && f.contentDocument.body) out.push(f.contentDocument); } catch (e) {} } return out; };
const vis = e => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };`;

await send('Page.enable'); await send('Runtime.enable');
await send('Page.navigate', { url }); await sleep(WAIT);

const q = opt('--hladaj');
if (q) {
  // Hodnotu zapisujeme priamo do pola (funguje aj v okne mimo obrazovky a v aplikaciach typu React),
  // potom formular odosleme: tlacidlom Hladat, cez formular, alebo klavesom Enter.
  const how = await ev(`(() => { ${LIB}
    const label = el => { const d = el.ownerDocument; const l = el.id && d.querySelector('label[for="' + el.id + '"]'); return [el.placeholder, el.name, el.id, el.getAttribute('aria-label'), l && l.innerText, el.closest('label') && el.closest('label').innerText].filter(Boolean).join(' '); };
    let pick = null, any = null;
    for (const d of docs()) for (const el of d.querySelectorAll('input[type=search],input[type=text],input:not([type])')) {
      if (!vis(el) || el.readOnly || el.disabled) continue;
      any = any || el;
      if (!pick && /h[ľl]ad|v[ýy]raz|fulltext|search|text/i.test(label(el))) pick = el;
    }
    const el = pick || any;
    if (!el) return 'ziadne pole';
    const win = el.ownerDocument.defaultView;
    Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, 'value').set.call(el, ${JSON.stringify(q)});
    el.dispatchEvent(new win.Event('input', { bubbles: true })); el.dispatchEvent(new win.Event('change', { bubbles: true }));
    const scope = el.form || el.ownerDocument;
    const btn = [...scope.querySelectorAll('button,input[type=submit],input[type=button],a')].find(b => vis(b) && /h[ľl]ada|vyh[ľl]ada|filtrova|search/i.test((b.innerText || b.value || b.title || '').trim()) && (b.innerText || b.value || '').trim().length < 30);
    if (btn) { btn.click(); return 'pole: ' + label(el).slice(0, 40) + ' | tlacidlo: ' + (btn.innerText || btn.value).trim(); }
    if (el.form) { el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit(); return 'pole: ' + label(el).slice(0, 40) + ' | formular'; }
    for (const type of ['keydown', 'keypress', 'keyup']) el.dispatchEvent(new win.KeyboardEvent(type, { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
    return 'pole: ' + label(el).slice(0, 40) + ' | Enter';
  })()`);
  console.error('[hladanie: ' + how + ']');
  await sleep(WAIT);
}
const k = opt('--klik');
if (k) {
  const ok = await ev(`(() => { ${LIB} const want = ${JSON.stringify(k.toLowerCase())}; for (const d of docs()) { const el = [...d.querySelectorAll('a,button,[role=button],[role=link]')].find(e => vis(e) && (e.innerText || '').trim().toLowerCase().includes(want)); if (el) { el.click(); return true; } } return false; })()`);
  if (!ok) console.error('POZOR: nenasiel som odkaz s textom ' + k);
  await sleep(WAIT);
}

const res = JSON.parse(await ev(`(() => { ${LIB} const ds = docs(); const text = ds.map(d => d.body.innerText).join('\\n'); const links = []; for (const d of ds) for (const a of d.querySelectorAll('a[href]')) { const t = (a.innerText || '').trim().replace(/\\s+/g, ' '); if (t && !/^(javascript|mailto|tel):/.test(a.getAttribute('href'))) links.push(t.slice(0, 110) + ' -> ' + a.href); } return JSON.stringify({ url: location.href, title: document.title, frames: ds.length - 1, text, links: [...new Set(links)] }); })()`) || '{}');
let lines = (res.text || '').split('\n').map(l => l.replace(/\s+/g, ' ').trim()).filter(Boolean);
const bot = /bot detection/i.test(res.title || '') || lines.length < 8;
console.error(`[zdroj: ${res.url} | ${res.title} | vnorene ramce: ${res.frames}${bot ? ' | POZOR: stranka nevydala obsah' : ''}]`);
const f = opt('--find');
if (f) { const rx = new RegExp(f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'); const hit = new Set(); lines.forEach((l, i) => { if (rx.test(l)) for (let j = Math.max(0, i - 2); j <= Math.min(lines.length - 1, i + 3); j++) hit.add(j); }); lines = [...hit].sort((a, b) => a - b).map(i => lines[i]); if (!lines.length) lines = [`(nic so slovom '${f}')`]; }
console.log(lines.join('\n'));
if (flag('--links')) { console.log('\n--- ODKAZY ---'); console.log((f ? res.links.filter(l => new RegExp(f, 'i').test(l)) : res.links).join('\n')); }
ws.close(); done(0);
