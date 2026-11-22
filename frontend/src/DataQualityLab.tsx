import React,{useMemo,useRef,useState} from 'react';
import {AlertTriangle,CheckCircle2,Download,FileSpreadsheet,Info,Search,ShieldCheck,Sparkles,UploadCloud,X} from 'lucide-react';
import {parseCSV,profileCSV,cleanCSV,serializeCSV} from './quality-engine.mjs';

type Data={headers:string[];rows:string[][]};
type Field={name:string;index:number;type:string;missing:number;unique:number;examples:string[]};
type Report={rows:number;columns:number;missingCells:number;duplicateRows:number;distinctRows:number;fields:Field[];warning:string};
type CleanResult=Data&{removed:number;changed:number};
const sizeLimit=5*1024*1024;
function downloadText(filename:string,text:string){const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));try{const a=document.createElement('a');a.href=url;a.download=filename;a.click()}finally{setTimeout(()=>URL.revokeObjectURL(url),1000)}}
export function DataQualityLab(){
 const fileInput=useRef<HTMLInputElement>(null);
 const [data,setData]=useState<Data|null>(null),[name,setName]=useState(''),[report,setReport]=useState<Report|null>(null),[error,setError]=useState('');
 const [trim,setTrim]=useState(true),[removeDuplicates,setRemoveDuplicates]=useState(true),[normalizeEmpty,setNormalizeEmpty]=useState(false),[query,setQuery]=useState(''),[preview,setPreview]=useState(false);
 const cleaned=useMemo<CleanResult|null>(()=>data?cleanCSV(data,{trim,dropExactDuplicates:removeDuplicates,normalizeEmpty}):null,[data,trim,removeDuplicates,normalizeEmpty]);
 const shown=preview&&cleaned?cleaned:data;
 const filtered=report?.fields.filter(f=>f.name.toLowerCase().includes(query.toLowerCase()))||[];
 async function load(file?:File){
  if(!file)return;
  setError('');setData(null);setReport(null);setPreview(false);
  if(file.size>sizeLimit){setError('This local preview accepts CSV files up to 5 MB. Use a streaming ingestion worker for larger files.');return}
  if(!/\.csv$/i.test(file.name)){setError('Choose a .csv file. Other formats require a dedicated parser.');return}
  try{const text=await file.text();const parsed=parseCSV(text);setData(parsed);setReport(profileCSV(parsed));setName(file.name)}
  catch(e){setError(e instanceof Error?e.message:String(e))}
 }
 const reset=()=>{setData(null);setReport(null);setName('');setError('');setPreview(false);if(fileInput.current)fileInput.current.value=''};
 return <div className="quality-lab">
  <section className="studio-hero"><div><span className="studio-tag"><Sparkles size={15}/> DATA QUALITY WORKBENCH</span><h2>Understand your data before migrating it.</h2><p>Profile and clean a local CSV in your browser. Inspect completeness, duplicates and inferred field types without sending its contents to the server.</p></div><div className="studio-number"><strong>0</strong><span>FILES UPLOADED<br/>TO SERVER</span></div></section>
  <div className="studio-notice quality-privacy"><ShieldCheck size={18}/><span><strong>Privacy by design:</strong> processing happens in this tab. No CSV rows are sent to PRISM APIs, AI providers or Render. This is a syntactic profiling demo, not validation of business semantics.</span></div>
  {!data?<section className="quality-drop" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();load(e.dataTransfer.files?.[0])}}>
    <div className="quality-drop-icon"><UploadCloud size={30}/></div><h2>Drop a CSV to begin</h2><p>Or select one from your device. Maximum 5 MB and 20,000 records, including quoted-field support.</p>
    <input ref={fileInput} aria-label="Select CSV file" type="file" accept=".csv,text/csv" onChange={e=>load(e.target.files?.[0])}/>
    <button className="primary" onClick={()=>fileInput.current?.click()}><FileSpreadsheet size={18}/> Choose CSV file</button>
    <small>Designed for sanitized test files. Never upload real enterprise data without authorization.</small>
   </section>:<>
   <div className="quality-filebar"><div><FileSpreadsheet size={20}/><span><strong>{name}</strong><small>Local-only workspace · {report?.rows.toLocaleString()} records analyzed</small></span></div><button onClick={reset}><X size={15}/> Clear file</button></div>
   <div className="metrics quality-metrics">{[['ROWS',report?.rows],['COLUMNS',report?.columns],['MISSING CELLS',report?.missingCells],['EXACT DUPLICATES',report?.duplicateRows]].map(([label,value])=><div className="metric" key={String(label)}><span className="quality-metric-label">{label}</span><strong>{Number(value).toLocaleString()}</strong></div>)}</div>
   <div className="two-col quality-columns">
    <section className="panel"><div className="panel-heading"><div><h2>Field profiling</h2><p>Inferred data types and quality indicators</p></div><div className="search"><Search size={15}/><input aria-label="Search fields" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Find column"/></div></div><div className="table-wrap"><table><thead><tr><th>FIELD</th><th>TYPE</th><th>MISSING</th><th>UNIQUE</th></tr></thead><tbody>{filtered.map(f=><tr key={f.index}><td><b>{f.name}</b><small title={f.examples.join(' | ')}>{f.examples.join(', ').slice(0,55)||'No values'}</small></td><td>{f.type}</td><td>{f.missing? <span className="quality-warning"><AlertTriangle size={13}/>{f.missing}</span>:<span className="quality-ok"><CheckCircle2 size={13}/>0</span>}</td><td>{f.unique}</td></tr>)}</tbody></table></div></section>
    <section className="panel"><div className="panel-heading"><div><h2>Cleaning pipeline</h2><p>Non-destructive, transparent transformations</p></div></div>
     <div className="quality-options"><label><input type="checkbox" checked={trim} onChange={e=>setTrim(e.target.checked)}/><span><b>Trim whitespace</b><small>Remove leading/trailing spaces in values</small></span></label><label><input type="checkbox" checked={removeDuplicates} onChange={e=>setRemoveDuplicates(e.target.checked)}/><span><b>Drop exact duplicate rows</b><small>After other selected cleaning rules</small></span></label><label><input type="checkbox" checked={normalizeEmpty} onChange={e=>setNormalizeEmpty(e.target.checked)}/><span><b>Normalize missing markers</b><small>Convert NULL / NONE / N/A to blank</small></span></label></div>
     <div className="quality-impact"><span><b>{cleaned?.removed||0}</b> rows removed</span><span><b>{cleaned?.changed||0}</b> values changed</span><span><b>{cleaned?.rows.length||0}</b> output rows</span></div>
     <div className="quality-actions"><button className="ghost-button" onClick={()=>setPreview(v=>!v)}>{preview?'Show original':'Preview cleaned'}</button><button className="primary" onClick={()=>cleaned&&downloadText(name.replace(/\.csv$/i,'')+'-cleaned.csv',serializeCSV(cleaned))}><Download size={16}/> Download cleaned CSV</button></div>
     <p className="fine"><Info size={13}/> Export escapes spreadsheet formulas to reduce CSV formula-injection risk. Review transformations before use.</p>
    </section>
   </div>
   <section className="panel"><div className="panel-heading"><div><h2>{preview?'Cleaned':'Original'} data preview</h2><p>First 20 rows only. Original file never changes.</p></div><span className="pill quiet">{shown?.rows.length} rows</span></div><div className="table-wrap"><table><thead><tr>{shown?.headers.map((h,i)=><th key={i}>{h}</th>)}</tr></thead><tbody>{shown?.rows.slice(0,20).map((r,i)=><tr key={i}>{r.map((v,j)=><td key={j}>{v||<span className="quality-null">—</span>}</td>)}</tr>)}</tbody></table></div></section>
  </>}
  {error&&<div className="error" role="alert">{error}<button onClick={()=>setError('')}>Dismiss</button></div>}
  <div className="studio-footer"><Info size={16}/><span>Limitations: single-file CSV inspection only; numeric inference may misclassify identifier columns, and exact-row duplication does not imply business duplication. Target-aware validation, reference integrity, PII detection and server-side scale-out are separate milestones.</span></div>
 </div>
}
