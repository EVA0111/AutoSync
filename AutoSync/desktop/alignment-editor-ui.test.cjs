'use strict';
// Preview & Edit is plain DOM code: every element the script looks up must
// exist in the page, or a control silently stops working.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'alignment-editor.html'),'utf8');
const js=fs.readFileSync(path.join(__dirname,'alignment-editor.js'),'utf8');
const ids=new Set([...html.matchAll(/\sid="([^"]+)"/g)].map(m=>m[1]));

test('every element id used by the editor script exists in the page',()=>{
 const used=new Set([...js.matchAll(/\$\('([a-z0-9-]+)'\)/g)].map(m=>m[1]));
 // Composed ids: source-/target- + wait/frame.
 for(const track of ['source','target'])for(const part of ['wait','frame','time','video'])used.add(track+'-'+part);
 const missing=[...used].filter(id=>!ids.has(id));
 assert.deepEqual(missing,[]);
});

test('page ids are unique',()=>{
 const all=[...html.matchAll(/\sid="([^"]+)"/g)].map(m=>m[1]);
 assert.equal(all.length,new Set(all).size);
});

test('every data-* control the script binds is present',()=>{
 for(const [attr,values] of [['data-tool',['select','razor','slip']],['data-listen',['output','source','target']],
  ['data-view',['side','overlay','difference','wipe']],['data-filter',['all','flagged','open']]])
  for(const v of values)assert.match(html,new RegExp(attr+'="'+v+'"'),attr+'='+v);
});

test('every keyboard shortcut in the help sheet is handled',()=>{
 for(const key of ['j','l','r','p','a','f','s','i','o','q','w','v','c','y','n'])
  assert.match(js,new RegExp('[^a-zA-Z]'+key+':'),'shortcut '+key);
 for(const k of ["'?'","','","'.'","'Home'","'End'","'ArrowLeft'","'ArrowRight'"])assert.ok(js.includes(k),k);
});
