'use strict';
/* Interface language for both windows.

   Pages stay written in English; this translates what is shown. Each
   locales/<code>.js file registers a dictionary keyed by the English text
   (exact text, or a pattern with {0}, {1}… for values such as times and
   file names). Text nodes and the title, placeholder, aria-label and alt
   attributes are translated on load and whenever the app changes them, so
   status messages, lists and dialogs follow the chosen language. Anything
   without a translation stays in English. Canvas drawings (the timeline)
   and file names are left as they are. */
(function(){
 const KEY='autosync-ui-language';
 const LANGUAGES=[
  ['en','English'],['ar','العربية'],['de','Deutsch'],['fr','Français'],['ja','日本語'],['ko','한국어'],
  ['es','Español'],['fa','فارسی'],['zh','中文（普通话）'],['hi','हिन्दी'],['pt','Português']];
 const RTL=new Set(['ar','fa']);
 const ATTRS=['title','placeholder','aria-label','alt'];
 const dicts=(globalThis.AUTOSYNC_LOCALES=globalThis.AUTOSYNC_LOCALES||{});
 let lang='en',exact=new Map(),patterns=[];
 const original=new WeakMap();    // node -> English text / {attr: English}
 const shown=new WeakMap();       // node -> text we last wrote (to ignore our own changes)
 const attrOriginal=new WeakMap(),attrShown=new WeakMap();
 const read=()=>{try{return localStorage.getItem(KEY)||'en';}catch{return 'en';}};

 function compile(dict){
  exact=new Map();patterns=[];
  for(const [en,tr] of Object.entries(dict||{})){
   if(!tr)continue;
   if(/\{\d\}/.test(en)){
    const parts=en.split(/(\{\d\})/);
    const order=[];
    const re=parts.map(p=>{const m=/^\{(\d)\}$/.exec(p);if(m){order.push(Number(m[1]));return '(.+?)';}return p.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}).join('');
    patterns.push({re:new RegExp('^'+re+'$'),order,tr,fixed:en.replace(/\{\d\}/g,'').length});
   }else exact.set(en,tr);
  }
  // Most specific first: "… fade in {2} ms, fade out {3} ms." before "… fade in {2} ms."
  patterns.sort((a,b)=>b.fixed-a.fixed);
 }
 function translate(text,depth=0){
  if(lang==='en'||typeof text!=='string'||text.length>1000)return text;  // logs and long text: not UI labels
  const core=text.trim();
  if(!core)return text;
  const lead=text.slice(0,text.length-text.trimStart().length),trail=text.slice(text.trimEnd().length);
  let out=exact.get(core);
  if(out===undefined)for(const p of patterns){
   const m=p.re.exec(core);
   // A value that is itself a known string (an error inside "… failed: {0}") is translated too.
   if(m){out=p.tr.replace(/\{(\d)\}/g,(_,i)=>{const v=m[1+p.order.indexOf(Number(i))]??'';return depth<2?translate(v,depth+1):v;});break;}
  }
  return out===undefined?text:lead+out+trail;
 }
 function textNode(node){
  const parent=node.parentElement;
  if(!parent||parent.closest('script,style,textarea,[data-no-translate],pre'))return;
  const now=node.nodeValue;
  if(shown.get(node)===now)return;           // our own translation
  original.set(node,now);
  const tr=translate(now);
  if(tr!==now){shown.set(node,tr);node.nodeValue=tr;}else shown.delete(node);
 }
 function element(el){
  if(el.closest('[data-no-translate]'))return;
  let orig=attrOriginal.get(el),last=attrShown.get(el);
  for(const a of ATTRS){
   if(!el.hasAttribute(a))continue;
   const now=el.getAttribute(a);
   if(last?.[a]===now)continue;
   orig=orig||{};last=last||{};orig[a]=now;
   const tr=translate(now);
   if(tr!==now){last[a]=tr;el.setAttribute(a,tr);}else delete last[a];
  }
  if(orig){attrOriginal.set(el,orig);attrShown.set(el,last);}
 }
 function walk(root){
  if(root.nodeType===3){textNode(root);return;}
  if(root.nodeType!==1&&root.nodeType!==9&&root.nodeType!==11)return;
  if(root.nodeType===1)element(root);
  const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT|NodeFilter.SHOW_ELEMENT);
  for(let n=w.nextNode();n;n=w.nextNode())n.nodeType===3?textNode(n):element(n);
 }
 // Back to English before switching language (or to English).
 function restore(root){
  const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT|NodeFilter.SHOW_ELEMENT);
  for(let n=w.nextNode();n;n=w.nextNode()){
   if(n.nodeType===3){if(shown.get(n)===n.nodeValue&&original.has(n))n.nodeValue=original.get(n);shown.delete(n);}
   else{const o=attrOriginal.get(n),l=attrShown.get(n);if(o&&l)for(const a of Object.keys(l))if(n.getAttribute(a)===l[a])n.setAttribute(a,o[a]);attrShown.delete(n);}
  }
 }
 let observer=null;
 function observe(){
  if(observer)return;
  observer=new MutationObserver(list=>{
   if(lang==='en')return;
   for(const m of list){
    if(m.type==='characterData')textNode(m.target);
    else if(m.type==='attributes')element(m.target);
    else for(const n of m.addedNodes)walk(n);
   }
  });
  observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:ATTRS});
 }
 function direction(){
  document.documentElement.lang=lang==='zh'?'zh-CN':lang;
  document.documentElement.dir=RTL.has(lang)?'rtl':'ltr';
 }
 function load(code){
  return new Promise(resolve=>{
   if(code==='en'||dicts[code])return resolve();
   const s=document.createElement('script');s.src='locales/'+code+'.js';
   s.onload=s.onerror=()=>resolve();document.head.append(s);
  });
 }
 async function set(code,save=true){
  if(!LANGUAGES.some(([c])=>c===code))code='en';
  await load(code);
  if(document.body)restore(document.body);
  lang=code;compile(dicts[code]);direction();
  if(save)try{localStorage.setItem(KEY,code);}catch{}
  if(document.body&&lang!=='en')walk(document.body);
  observe();
  for(const sel of document.querySelectorAll('select[data-ui-language]')){
  sel.value=lang;const t=translate('Interface language');sel.title=t;sel.setAttribute('aria-label',t);   // the picker itself is never auto-translated
 }
 }
 /** A language picker (native names, never translated). */
 function picker(){
  const sel=document.createElement('select');
  sel.dataset.uiLanguage='';sel.dataset.noTranslate='';sel.className='ui-language';
  sel.title='Interface language';sel.setAttribute('aria-label','Interface language');
  for(const [code,name] of LANGUAGES)sel.add(new Option(name,code));
  sel.value=lang;sel.onchange=()=>set(sel.value);
  return sel;
 }
 // Keep windows in step: another window changing the language applies here too.
 window.addEventListener('storage',e=>{if(e.key===KEY&&e.newValue&&e.newValue!==lang)set(e.newValue,false);});
 globalThis.I18N={t:translate,set,picker,get lang(){return lang;},languages:LANGUAGES};
 const start=()=>set(read(),false);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
