#!/usr/bin/env node
/* Publish the Ask Thakur site (site/) into the rkmdk website as /kathamrita/,
   wrapped in the main site's header and footer.

   USAGE:  node sync_to_rkmdk.js [path-to-rkmdk]     (default: ../rkmdk)
   Then in rkmdk:  node build.js   (not needed for kathamrita, but harmless)

   - The app's CSS is scoped under #kath so it cannot clash with the site's styles.
   - The app's dark mode is dropped (the main site is light only).
   - header.html / footer.html come from rkmdk; their relative links get "../".
*/
'use strict';
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, 'site');
const RKM = path.resolve(process.argv[2] || path.join(__dirname, '..', 'rkmdk'));
const OUT = path.join(RKM, 'kathamrita');
const read = f => fs.readFileSync(f, 'utf8');

/* ---- CSS scoping ---- */
function splitTop(css) {            // -> [{sel, body}] for top-level rules
  const rules = []; let i = 0;
  while (i < css.length) {
    const open = css.indexOf('{', i);
    if (open < 0) break;
    let depth = 1, j = open + 1;
    while (j < css.length && depth) { if (css[j] === '{') depth++; else if (css[j] === '}') depth--; j++; }
    rules.push({ sel: css.slice(i, open).trim(), body: css.slice(open + 1, j - 1) });
    i = j;
  }
  return rules;
}
function scopeSel(sel) {
  return sel.split(',').map(s => {
    s = s.trim();
    if (s === ':root' || s === 'body') return '#kath';
    if (s === 'html') return null;
    if (s.startsWith('html[')) return s.replace(/^(html\[[^\]]*\])\s*/, '$1 #kath ');
    return '#kath ' + s;
  }).filter(Boolean).join(',');
}
function scope(css) {
  return splitTop(css).map(r => {
    if (/data-theme/.test(r.sel) || /prefers-color-scheme/.test(r.sel)) return '';   // drop dark mode
    if (r.sel.startsWith('@media')) return r.sel + '{' + scope(r.body) + '}';
    const sel = scopeSel(r.sel);
    return sel ? sel + '{' + r.body + '}' : '';
  }).join('\n');
}

/* ---- header / footer: make relative links work from /kathamrita/ ---- */
function up(html) {
  return html.replace(/\b(href|src)="(?!https?:|\/|#|mailto:|tel:|data:|javascript:)([^"]*)"/g, '$1="../$2"');
}

const app = read(path.join(SRC, 'index.html'));
const styleM = app.match(/<style>([\s\S]*?)<\/style>/);
const bodyM = app.match(/<body>([\s\S]*)<\/body>/);
if (!styleM || !bodyM) throw new Error('unexpected site/index.html structure');

const css = scope(styleM[1].replace(/\/\*[\s\S]*?\*\//g, '')) +
  '\n#kath{padding-top:84px;min-height:60vh}\n' +
  '#kath .wrap{padding-bottom:56px}\n' +
  // the site's own .tag badge style would otherwise leak onto the subtitle
  '#kath .tag{display:block;background:none;padding:0;border-radius:0;font-size:inherit;font-weight:inherit;letter-spacing:normal;text-transform:none;margin:4px 0 0}\n' +
  // amrita-manthan medallion beside the title (image lives in rkmdk/kathamrita/img, not synced from site/)
  '#kath header.top.with-icon{display:grid;grid-template-columns:auto 1fr;column-gap:14px;align-items:center}\n' +
  '#kath header.top.with-icon .kh__icon{grid-row:1/3;width:60px;height:60px;border-radius:50%;box-shadow:0 2px 10px rgba(44,24,16,.25)}\n' +
  '#kath header.top.with-icon .brand{grid-column:2}\n' +
  '#kath header.top.with-icon .tag{grid-column:2}\n' +
  // ---- laptop / desktop layout (mobile is untouched) ----
  `@media (min-width:900px){
#kath .wrap{max-width:760px}
#kath.kh-on{padding-top:68px}
#kath.kh-on .wrap{max-width:1040px;position:relative}
#kath.kh-on .bar{position:absolute;top:22px;right:0;z-index:2;padding:0}
#kath .kh{position:relative;overflow:hidden;margin-inline:calc(50% - 50vw);padding:60px calc(50vw - 50%) 68px;
  background:radial-gradient(circle at 12% 0%,rgba(232,114,42,.38),transparent 55%),radial-gradient(circle at 92% 100%,rgba(212,168,84,.2),transparent 50%),linear-gradient(135deg,#2C1810,#4A3728)}
#kath .kh__in{max-width:760px;margin:0 auto}
#kath header.top.with-icon{column-gap:22px}
#kath header.top.with-icon .kh__icon{width:96px;height:96px;box-shadow:0 4px 18px rgba(0,0,0,.35)}
#kath .kh .brand{color:#fff;font-size:48px;line-height:1.15}
#kath .kh .tag{color:var(--hl);font-size:19px;margin-top:10px}
#kath .kh form.ask{margin-top:28px;display:grid;grid-template-columns:1fr auto;gap:12px 20px;align-items:center}
#kath .kh form.ask textarea{grid-column:1/-1;min-height:100px;font-size:17px;border:0;box-shadow:0 10px 34px rgba(0,0,0,.28)}
#kath .kh .ask-hint{color:rgba(245,237,224,.82)}
#kath .kh form.ask button{align-self:center;padding:11px 28px;font-size:16px}
#kath nav.tabs{margin-top:30px;font-size:16px}
#kath h2.group{font-size:14px;color:var(--accent);margin:40px 0 0}
#kath ul.problems{grid-template-columns:repeat(3,1fr);gap:16px;margin-top:14px}
#kath ul.problems a{padding:18px 20px;transition:transform .2s,box-shadow .2s,border-color .2s}
#kath ul.problems a:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(44,24,16,.1)}
#kath ul.problems .t{font-size:22px}
#kath ul.problems .s{font-size:14px;margin-top:4px}
}\n`;

const at = bodyM[1].indexOf("<script>");
if (at < 0) throw new Error("no <script> in site/index.html body");
const markup = '<div id="kath">' + bodyM[1].slice(0, at).trim() + '</div>';
const scripts = bodyM[1].slice(at).trim();

const header = up(read(path.join(RKM, 'header.html')).trim());
const footer = up(read(path.join(RKM, 'footer.html')).trim());

const html = `<!doctype html>
<html lang="bn" class="no-js"><head><script>document.documentElement.className='js'</script>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Ask Thakur - Ramakrishna Math, Dakshineshwar</title>
<meta name="description" content="What Sri Ramakrishna said about life's problems, in the words of the Kathamrita (ঠাকুরের কথা).">
<link rel="icon" type="image/png" href="../logo.webp">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Tiro+Bangla&family=Noto+Sans+Bengali:wght@400;500;600;700&family=DM+Sans:wght@300;400;500;600;700&family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;0,700;1,300;1,400;1,500&display=swap">
<link rel="stylesheet" href="../css/styles.css">
<style>
${css}
</style>
</head><body>
<div id="site-header">
${header}
</div>
${markup}
<div id="site-footer">
${footer}
</div>
<script src="../js/icons.js"></script>
<script src="../js/common.js"></script>
${scripts}
<script>
/* Desktop hero: wrap the title + ask box of the home view in a full-width band (styled only at >=900px) */
(function(){
  var kath=document.getElementById('kath'), view=document.getElementById('view');
  function sync(){
    var top=view.querySelector(':scope > header.top'), form=top&&top.nextElementSibling;
    if(top&&form&&form.matches('form.ask')){
      var hero=document.createElement('section'), inner=document.createElement('div');
      hero.className='kh'; inner.className='kh__in';
      var ic=document.createElement('img'); ic.className='kh__icon'; ic.src='img/amrita-192.png'; ic.alt=''; ic.width=96; ic.height=96;
      top.classList.add('with-icon'); top.insertBefore(ic,top.firstChild);
      view.insertBefore(hero,top); inner.appendChild(top); inner.appendChild(form); hero.appendChild(inner);
    }
    kath.classList.toggle('kh-on',!!view.querySelector(':scope > .kh'));
  }
  new MutationObserver(sync).observe(view,{childList:true});
  sync();
})();
</script>
</body></html>
`;

fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, 'index.html'), html);
fs.cpSync(path.join(SRC, 'data'), path.join(OUT, 'data'), { recursive: true, force: true });
console.log('wrote', path.join(OUT, 'index.html'), '+ data/');
