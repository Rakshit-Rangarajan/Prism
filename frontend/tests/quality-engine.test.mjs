import test from 'node:test';
import assert from 'node:assert/strict';
import {parseCSV,profileCSV,cleanCSV,serializeCSV} from '../src/quality-engine.mjs';
test('quoted commas, escaped quotes and multiline fields',()=>{
 const p=parseCSV('id,name,notes\r\n1,"Smith, Jr.","a ""quoted"" note"\r\n2,Lee,"multi\nline"');
 assert.equal(p.rows.length,2);assert.equal(p.rows[0][1],'Smith, Jr.');assert.equal(p.rows[1][2],'multi\nline');
});
test('reject duplicate headers and inconsistent rows',()=>{
 assert.throws(()=>parseCSV('a,A\n1,2'),/Duplicate column/);
 assert.throws(()=>parseCSV('a,b\n1'),/Inconsistent row/);
});
test('profile missing and exact duplicates',()=>{
 const p=parseCSV('id,value\n1,\n1,\n2,4');
 const out=profileCSV(p);assert.equal(out.duplicateRows,1);assert.equal(out.missingCells,2);assert.equal(out.fields[0].type,'integer');
});
test('preview clean removes duplicates without changing source',()=>{
 const p=parseCSV('id,value\n1, NULL \n1, NULL \n2,ok');
 const out=cleanCSV(p,{trim:true,normalizeEmpty:true,dropExactDuplicates:true});
 assert.equal(out.rows.length,2);assert.equal(out.rows[0][1],'');assert.equal(p.rows[0][1],' NULL ');
});
test('protect against spreadsheet formula injection on CSV export',()=>{
 const csv=serializeCSV({headers:['name'],rows:[['=2+2'],['+cmd'],['@x'],['-1']]});
 assert.match(csv,/"'=2\+2"/);assert.match(csv,/"'\+cmd"/);assert.match(csv,/"'@x"/);assert.match(csv,/"'-1"/);
});
test('enforce row cap and unterminated fields',()=>{
 assert.throws(()=>parseCSV('a\n1\n2',1),/preview limit/);
 assert.throws(()=>parseCSV('a\n"oops'),/Unterminated/);
});
