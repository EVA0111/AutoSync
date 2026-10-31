'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const pkg=require('../package.json');
const repo=path.resolve(__dirname,'../..');

test('desktop, editor and metadata all identify AutoSync v1.2.5',()=>{
 assert.equal(pkg.version,'1.2.5');
 const main=fs.readFileSync(path.join(__dirname,'main.cjs'),'utf8');
 const ui=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
 const editor=fs.readFileSync(path.join(__dirname,'alignment-editor.html'),'utf8');
 assert.match(main,/AutoSync v\$\{require\('\.\.\/package\.json'\)\.version\}/);
 assert.match(ui,/<title>AutoSync v1\.2\.0<\/title>/);
 assert.match(ui,/<small>v1\.2\.0<\/small>/);
 assert.match(editor,/AutoSync v1\.2\.0 · Preview & Edit/);
});

test('Windows portable output and release note filenames use v1.2.5',()=>{
 const builder=fs.readFileSync(path.join(repo,'build/windows/build-portable.ps1'),'utf8');
 const notes=fs.readFileSync(path.join(repo,'AutoSync/RELEASE_NOTES.md'),'utf8');
 assert.match(builder,/AutoSync-v\{0\}-Windows-Portable\.zip/);
 assert.match(builder,/AutoSync-v\{0\}-Windows-Portable/);
 assert.match(notes,/AutoSync-v1\.2\.0-Windows-Portable\.zip/);
});
