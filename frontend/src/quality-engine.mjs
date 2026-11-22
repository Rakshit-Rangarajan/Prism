/**
 * PRISM local-only CSV profile engine.
 * No network, no file storage and no mutations to the input.
 */
export function parseCSV(input, maxRows=20000, maxColumns=200) {
 if (typeof input !== 'string') throw new Error('CSV input must be text');
 const text=input.replace(/^\uFEFF/,'');
 const rows=[];let row=[],field='',inQuotes=false;
 for(let i=0;i<text.length;i++){
  const ch=text[i];
  if(inQuotes){
   if(ch==='"'&&text[i+1]==='"'){field+='"';i++}
   else if(ch==='"'){inQuotes=false}
   else{field+=ch}
  }else if(ch==='"'){
   if(field!=='')throw new Error('Unexpected quote in CSV value');
   inQuotes=true;
  }else if(ch===','){row.push(field);field='';if(row.length>maxColumns)throw new Error('Too many columns')}
  else if(ch==='\r'||ch==='\n'){
   if(ch==='\r'&&text[i+1]==='\n')i++;
   row.push(field);field='';
   if(row.length>maxColumns)throw new Error('Too many columns');
   rows.push(row);row=[];
   if(rows.length>maxRows+1)throw new Error('CSV exceeds the '+maxRows+'-row preview limit');
  }else{field+=ch}
 }
 if(inQuotes)throw new Error('Unterminated quoted CSV field');
 if(field!==''||row.length){row.push(field);rows.push(row)}
 if(rows.length>maxRows+1)throw new Error('CSV exceeds the '+maxRows+'-row preview limit');
 if(!rows.length)throw new Error('The CSV is empty');
 const headers=rows.shift().map((h,i)=>h.trim()||'Column '+(i+1));
 if(headers.length>maxColumns)throw new Error('Too many columns');
 const seen=new Set();headers.forEach(h=>{const key=h.toLowerCase();if(seen.has(key))throw new Error('Duplicate column name: '+h);seen.add(key)});
 if(rows.some(row=>row.length!==headers.length))throw new Error('Inconsistent row width. Verify separators and quoted values.');
 return {headers,rows};
}
function detectType(values){
 const filled=values.filter(v=>v.trim()!=='');
 if(!filled.length)return 'empty';
 if(filled.every(v=>/^(true|false)$/i.test(v.trim())))return 'boolean';
 if(filled.every(v=>/^-?\d+$/.test(v.trim())))return 'integer';
 if(filled.every(v=>/^-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(v.trim())))return 'decimal';
 if(filled.every(v=>/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(v.trim())))return 'date / timestamp';
 return 'text';
}
export function profileCSV(parsed){
 const {headers,rows}=parsed;
 const duplicateKeys=new Set(),duplicateIndexes=[];
 rows.forEach((row,index)=>{const key=JSON.stringify(row);if(duplicateKeys.has(key))duplicateIndexes.push(index);else duplicateKeys.add(key)});
 const columns=headers.map((name,index)=>{
  const vals=rows.map(r=>r[index]);const nonempty=vals.filter(v=>v.trim()!=='');
  return {name,index,type:detectType(vals),missing:rows.length-nonempty.length,unique:new Set(nonempty).size,examples:[...new Set(nonempty)].slice(0,3)};
 });
 const missingCells=columns.reduce((n,c)=>n+c.missing,0);
 const distinctRows=rows.length-duplicateIndexes.length;
 return {rows:rows.length,columns:headers.length,missingCells,duplicateRows:duplicateIndexes.length,distinctRows,fields:columns,duplicateIndexes,warning:'Client-side syntactic profiling only: no source-system or business-rule validation.'};
}
export function cleanCSV(parsed,options={}){
 const {trim=true,dropExactDuplicates=true,normalizeEmpty=false}=options;
 const seen=new Set(),out=[];let removed=0,changed=0;
 for(const row of parsed.rows){
  const clean=row.map(value=>{
   const trimmed=trim?value.trim():value;
   const result=normalizeEmpty&&/^(N\/A|NULL|NONE)$/i.test(trimmed)?'':trimmed;
   if(result!==value)changed++;
   return result;
  });
  const key=JSON.stringify(clean);
  if(dropExactDuplicates&&seen.has(key)){removed++;continue}
  seen.add(key);out.push(clean);
 }
 return {headers:[...parsed.headers],rows:out,removed,changed};
}
function safeExportCell(value){
 const s=String(value??'');
 // Formula injection is possible in CSV opened by spreadsheet software.
 const safe=/^[\s]*[=+@\-\t\r]/.test(s)?"'"+s:s;
 return '"'+safe.replace(/"/g,'""')+'"';
}
export function serializeCSV(parsed){
 return [parsed.headers,...parsed.rows].map(r=>r.map(safeExportCell).join(',')).join('\r\n')+'\r\n';
}
