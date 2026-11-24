import React,{useState} from 'react';
import {AlertTriangle,CheckCircle2,Database,RefreshCcw,ShieldCheck} from 'lucide-react';

type Scenario={index:number;name:string;source:Record<string,unknown>};
type Outcome={scenario:string;status:string;errors?:string[];reused_lessons?:string[]};
type Lesson={signature:string;suggestion:string;approved:boolean;occurrences:number};
type Summary={scenario_count:number;validated_only:number;migrated_this_run:number;rejected_this_run:number;target_total_records:number;reconciliation_passed:boolean;error_signatures:Record<string,number>;approved_rule_reuse:Record<string,number>;lessons:Lesson[]};
type Run={synthetic:boolean;mode:string;results:Outcome[];reconciliation:Summary};
async function api<T>(path:string,options?:RequestInit):Promise<T>{
 const res=await fetch('/api/demo/erp/'+path,options);
 if(!res.ok)throw Error((await res.text()).slice(0,180));
 return res.json() as Promise<T>;
}
export function ErpLearningDemo(){
 const [scenarios,setScenarios]=useState<Scenario[]>([]);
 const [run,setRun]=useState<Run|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [message,setMessage]=useState('');
 async function runStep(apply:boolean){
  setBusy(true);setError('');setMessage('');
  try{
   const [dataset,result]=await Promise.all([
    api<{scenarios:Scenario[]}>('scenarios'),
    api<Run>('run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({apply})})
   ]);
   setScenarios(dataset.scenarios);setRun(result);
   setMessage(apply?'Local synthetic target updated. Review reconciliation.':'Preview complete; no target records written.');
  }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function approve(){
  if(!window.confirm('Approve the synthetic USD formatting correction for subsequent runs?'))return;
  setBusy(true);setError('');
  try{
   await api('lessons/approve',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({signature:'amount:legacy_format',confirmation:'APPROVE SYNTHETIC RULE'})});
   setMessage('Correction approved and remembered. Replay to observe the difference.');
   setRun(null);
  }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function resetDemo(){
  if(!window.confirm('Reset ONLY the synthetic ERP demo data and learned approvals? This cannot be undone.'))return;
  setBusy(true);setError('');
  try{
   await api('reset',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({confirmation:'RESET SYNTHETIC DEMO'})});
   setRun(null);setScenarios([]);
   setMessage('Synthetic demo reset. Start with Preview 20 records.');
  }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 function exportReport(){
  if(!run)return;
  const b=new Blob([JSON.stringify(run,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(b),a=document.createElement('a');
  a.href=url;a.download='prism-synthetic-erp-reconciliation.json';a.click();URL.revokeObjectURL(url);
 }
 const summary=run?.reconciliation;
 return <div>
  <div className="notice"><ShieldCheck size={20}/><div><b>Learning migration · synthetic ERP demonstration</b>
   <p>Twenty intentionally flawed customer records. Corrections are recorded and only reused after explicit approval. This does not connect to SAP or train an AI model.</p></div></div>
  <section className="panel">
   <div className="panel-heading"><div><h2>Run the migration</h2><p>1. Preview errors → 2. Approve a safe rule → 3. Replay → 4. Inspect target and evidence</p></div></div>
   <div style={{display:'flex',flexWrap:'wrap',gap:12,padding:'0 0 16px'}}>
    <button disabled={busy} className="small-button" onClick={()=>runStep(false)}>Preview 20 records</button>
    <button disabled={busy||!run?.reconciliation.lessons.some(x=>x.signature==='amount:legacy_format'&&!x.approved)} className="small-button" onClick={approve}><ShieldCheck size={16}/> Approve learned rule</button>
    <button disabled={busy} className="small-button" onClick={()=>runStep(true)}><Database size={16}/> Execute local migration</button>
    <button disabled={!run} className="small-button" onClick={exportReport}>Export reconciliation JSON</button>
    <button disabled={busy} className="small-button" onClick={resetDemo}>Restart synthetic demo</button>
   </div>
   {busy&&<p role="status"><RefreshCcw size={15}/> Processing synthetic records…</p>}
   {error&&<p role="alert" className="error">{error}</p>}
   {message&&<p role="status">{message}</p>}
  </section>
  {summary&&<><div className="metrics">
   <div className="panel"><small>SCENARIOS</small><h2>{summary.scenario_count}</h2></div>
   <div className="panel"><small>THIS RUN — MIGRATED</small><h2>{summary.migrated_this_run}</h2></div>
   <div className="panel"><small>REJECTED</small><h2>{summary.rejected_this_run}</h2></div>
   <div className="panel"><small>TARGET RECORDS</small><h2>{summary.target_total_records}</h2></div>
  </div>
  <section className="panel"><div className="panel-heading"><div><h2>Migration evidence</h2><p>{run?.mode==='preview'?'Validation only — target unchanged':'Synthetic SQLite target'} · {summary.reconciliation_passed?'Run-level count reconciliation passed':'Reconciliation warning'}</p></div>{summary.reconciliation_passed?<CheckCircle2 size={20}/>:<AlertTriangle size={20}/>}</div>
  <div className="table-wrap"><table><thead><tr><th>SCENARIO</th><th>OUTCOME</th><th>ERRORS</th><th>REUSED APPROVED FIX</th></tr></thead>
   <tbody>{run?.results.map((item,i)=><tr key={i}><td>{item.scenario}</td><td>{item.status}</td><td>{(item.errors||[]).join(', ')||'—'}</td><td>{(item.reused_lessons||[]).join(', ')||'—'}</td></tr>)}</tbody></table></div>
  </section>
  <section className="panel"><div className="panel-heading"><div><h2>Remembered lessons</h2><p>Approval controls reuse. Observations alone are never automatically applied.</p></div></div>
   <div className="table-wrap"><table><thead><tr><th>ERROR SIGNATURE</th><th>OBSERVATIONS</th><th>STATUS</th><th>REMEDIATION</th></tr></thead><tbody>{summary.lessons.map(l=><tr key={l.signature}><td>{l.signature}</td><td>{l.occurrences}</td><td>{l.approved?'Approved':'Review required'}</td><td>{l.suggestion}</td></tr>)}</tbody></table></div>
  </section></>}
  {scenarios.length>0&&<section className="panel"><div className="panel-heading"><div><h2>Source records</h2><p>20 generated synthetic inputs, independent of any production ERP</p></div></div><div className="table-wrap"><table><thead><tr><th>SCENARIO</th><th>LEGACY INPUT</th></tr></thead><tbody>{scenarios.map(s=><tr key={s.index}><td>{s.name}</td><td><code>{JSON.stringify(s.source)}</code></td></tr>)}</tbody></table></div></section>}
 </div>;
}
