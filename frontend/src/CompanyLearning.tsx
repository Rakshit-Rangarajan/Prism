import React,{useEffect,useState} from 'react';
import {Brain,CheckCircle2,Database,Download,Plus,RefreshCcw,Search,ShieldCheck} from 'lucide-react';
import {LEARNING_TASKS,compactTask,formatAccuracy,validSlug,summarizeExamples,scoreLabel} from './learning-engine.mjs';

type Company={id:number;name:string;slug:string;description:string;examples:number;approved_examples:number;active_models:number};
type Example={id:number;task:string;state:string;input:Record<string,unknown>;output:Record<string,unknown>;scrubbed_count:number};
type Run={id:number;task:string;method:string;status:string;metrics:Record<string,unknown>;error:string|null;created_at:string};
type Model={id:number;task:string;version:number;state:string;metrics:Record<string,unknown>};
type Source={id:number;kind:string;name:string;metadata_json:string;created_at:string};
type Overview={company:Company;sources:number;examples_by_task:Record<string,{approved:number;draft:number}>;runs:number;active_models:number};
type RagHit={id:number;input:Record<string,unknown>;output:Record<string,unknown>;score:number};
type Prediction={mode:string;prediction:Record<string,unknown>;confidence:number;provenance:Record<string,unknown>;supporting_examples:RagHit[];warning:string};
type Capabilities={tasks:string[];methods:string[];default_method:string;default_method_is_llm:boolean;live_db_sources_enabled:boolean;optional_lora_dependencies:Record<string,boolean>;note:string};

async function api<T>(path:string,options?:RequestInit):Promise<T>{const r=await fetch('/api/company-learning'+path,options);if(!r.ok)throw Error((await r.text()).slice(0,220)||('Request failed '+r.status));return r.json() as Promise<T>}
function post<T>(path:string,body:unknown){return api<T>(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
function download(filename:string,data:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();URL.revokeObjectURL(url)}
function pretty(value:unknown){return JSON.stringify(value)}

export function CompanyLearning(){
 const [companies,setCompanies]=useState<Company[]>([]);const [selected,setSelected]=useState<number|null>(null);
 const [overview,setOverview]=useState<Overview|null>(null);const [examples,setExamples]=useState<Example[]>([]);
 const [runs,setRuns]=useState<Run[]>([]);const [models,setModels]=useState<Model[]>([]);const [sources,setSources]=useState<Source[]>([]);
 const [capabilities,setCapabilities]=useState<Capabilities|null>(null);
 const [name,setName]=useState('');const [slug,setSlug]=useState('');
 const [task,setTask]=useState('schema_mapping');const [taskFilter,setTaskFilter]=useState('all');
 const [method,setMethod]=useState('deterministic');const [epochs,setEpochs]=useState(3);
 const [query,setQuery]=useState('');const [hits,setHits]=useState<RagHit[]>([]);
 const [predictText,setPredictText]=useState('{"source_system":"LEGACY_ERP","source_table":"VEND_MAST","columns":["VEND_ID","VEND_NM"]}');
 const [prediction,setPrediction]=useState<Prediction|null>(null);
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [message,setMessage]=useState('');

 async function refresh(id:number){
  try{
   const [o,e,r,m,s]=await Promise.all([api<Overview>(`/${id}/overview`),api<Example[]>(`/${id}/examples?limit=200`),
    api<Run[]>(`/${id}/runs`),api<Model[]>(`/${id}/models`),api<Source[]>(`/${id}/sources`)]);
   setOverview(o);setExamples(e);setRuns(r);setModels(m);setSources(s);
  }catch(err){setError(String(err))}
 }
 useEffect(()=>{api<Capabilities>('/capabilities').then(setCapabilities).catch(e=>setError(String(e)))},[]);
 useEffect(()=>{api<Company[]>('/companies').then(list=>{setCompanies(list);if(list.length&&selected===null)setSelected(list[0].id)}).catch(e=>setError(String(e)))},[]);
 useEffect(()=>{if(selected!==null)refresh(selected)},[selected]);
 async function act(fn:()=>Promise<void>){setBusy(true);setError('');setMessage('');try{await fn()}catch(err){setError(String(err))}finally{setBusy(false)}}
 const counts=summarizeExamples(examples);const shown=examples.filter(e=>taskFilter==='all'||e.task===taskFilter).slice(0,40);

 async function create(){await act(async()=>{
  if(!validSlug(slug))throw Error('Slug must be 2-49 lowercase letters, digits or hyphens.');
  const created=await post<{id:number}>('/companies',{name,slug,description:'Synthetic QA company'});
  setName('');setSlug('');setCompanies(await api<Company[]>('/companies'));setSelected(created.id);
  setMessage('Company created. Its examples, retrieval index and models are isolated.');
 })}
 async function bootstrap(){if(selected===null)return;await act(async()=>{
  const result=await post<{examples_created:Record<string,number>}>(`/${selected}/bootstrap`,{});
  await refresh(selected);setMessage('Synthetic examples generated for '+Object.keys(result.examples_created).length+' tasks. They remain drafts.');
 })}
 async function approve(id:number){if(selected===null)return;if(!window.confirm('Approve this training example for retrieval and model training?'))return;await act(async()=>{
  await post(`/${selected}/examples/${id}/approve`,{confirmation:'APPROVE TRAINING EXAMPLE'});await refresh(selected);setMessage('Example approved and indexed.');
 })}
 async function retrieve(){if(selected===null)return;await act(async()=>{
  const result=await post<{results:RagHit[]}>(`/${selected}/rag/query`,{task,query,limit:5});setHits(result.results);
  setMessage(result.results.length+' approved example(s) retrieved for '+compactTask(task)+'.');
 })}
 async function train(){if(selected===null)return;await act(async()=>{
  const result=await post<{status:string;metrics?:Record<string,unknown>;error?:string}>(`/${selected}/train`,{task,method,epochs});
  await refresh(selected);
  setMessage(result.status==='blocked'?('Training blocked: '+result.error):result.status==='prepared'?('LoRA manifest prepared. Run the offline script to train.'):
   ('Model evaluated. Hold-out accuracy '+formatAccuracy(result.metrics||{})+' — approve it before prediction.'));
 })}
 async function approveModel(id:number){if(selected===null)return;if(!window.confirm('Activate this company model for '+compactTask(task)+'? Previous active model will be retired.'))return;await act(async()=>{
  await post(`/${selected}/models/${id}/approve`,{confirmation:'APPROVE COMPANY MODEL'});await refresh(selected);setMessage('Model activated for this company and task.');
 })}
 async function downloadDataset(){if(selected===null)return;await act(async()=>{
  const data=await api<object>(`/${selected}/dataset?task=${task}`);download(`prism-${overview?.company.slug||'company'}-${task}-dataset.json`,data);
 })}
 async function predict(){if(selected===null)return;await act(async()=>{
  const parsed=JSON.parse(predictText) as Record<string,unknown>;
  setPrediction(await post<Prediction>(`/${selected}/predict`,{task,input:parsed}));
 })}
 const selectedCompany=companies.find(c=>c.id===selected)||null;
 return <div>
  <div className="notice"><Brain size={20}/><div><b>Per-company learning workspace</b>
   <p>Synthetic data is generated per company. Examples enter retrieval and training only after explicit approval. The default trainer is a small deterministic model, not an LLM; true LoRA fine-tuning is an opt-in offline script.</p></div></div>
  {error&&<p role="alert" className="error">{error}</p>}
  {message&&<p role="status">{message}</p>}
  <section className="panel">
   <div className="panel-heading"><div><h2>Company scope</h2><p>Each company gets an isolated example store, retrieval index and model registry.</p></div>
    <button className="small-button" disabled={busy} onClick={()=>{void refresh(selected||0)}}><RefreshCcw size={15}/> Refresh</button></div>
   <div className="tools">
    <select aria-label="Select company" value={selected??''} onChange={e=>{setSelected(Number(e.target.value)||null);setHits([]);setPrediction(null)}}>
     <option value="">Choose a company…</option>{companies.map(c=><option key={c.id} value={c.id}>{c.name} ({c.slug})</option>)}
    </select>
    <input aria-label="New company name" placeholder="Company name" value={name} onChange={e=>setName(e.target.value)}/>
    <input aria-label="New company slug" placeholder="slug e.g. acme-corp" value={slug} onChange={e=>setSlug(e.target.value)}/>
    <button className="small-button" disabled={busy} onClick={()=>void create()}><Plus size={15}/> Create</button>
   </div>
   {selectedCompany&&<div className="learn-grid">
    <div><small>EXAMPLES</small><strong>{counts.total}</strong><span>{counts.approved} approved · {counts.draft} drafts</span></div>
    <div><small>SOURCES</small><strong>{overview?.sources??0}</strong><span>synthetic, redacted or read-only schema</span></div>
    <div><small>TRAINING RUNS</small><strong>{overview?.runs??0}</strong><span>evaluated locally</span></div>
    <div><small>ACTIVE MODELS</small><strong>{overview?.active_models??0}</strong><span>approved per task</span></div>
   </div>}
  </section>
  {selectedCompany&&<>
   <section className="panel"><div className="panel-heading"><div><h2>Training data</h2><p>Generate synthetic examples or supply redacted records. Live schema sources require server-side opt-in.</p></div>
    <button className="small-button" disabled={busy} onClick={()=>void bootstrap()}><Database size={15}/> Generate all 4 tasks</button></div>
    <div className="tools">
     <select aria-label="Dataset task" value={task} onChange={e=>setTask(e.target.value)}>{LEARNING_TASKS.map(t=><option key={t} value={t}>{compactTask(t)}</option>)}</select>
     <button className="ghost-button" disabled={busy} onClick={()=>void downloadDataset()}><Download size={15}/> Export approved JSONL-ready dataset</button>
    </div>
    {sources.length>0&&<div className="table-wrap"><table><thead><tr><th>SOURCE</th><th>KIND</th><th>METADATA</th><th>CREATED</th></tr></thead><tbody>
     {sources.map(s=><tr key={s.id}><td><b>{s.name}</b></td><td>{s.kind}</td><td><code>{s.metadata_json.slice(0,120)}</code></td><td>{s.created_at}</td></tr>)}
    </tbody></table></div>}
    {sources.length===0&&<p className="fine">No training sources yet. Generate synthetic examples to begin.</p>}
   </section>
   <section className="panel"><div className="panel-heading"><div><h2>Approval queue</h2><p>Scrubbed examples stay as drafts until reviewed. Only approved examples are retrievable.</p></div>
    <select aria-label="Filter example task" value={taskFilter} onChange={e=>setTaskFilter(e.target.value)}><option value="all">All tasks</option>{LEARNING_TASKS.map(t=><option key={t} value={t}>{compactTask(t)}</option>)}</select></div>
    <div className="table-wrap"><table><thead><tr><th>ID</th><th>TASK</th><th>INPUT</th><th>EXPECTED OUTPUT</th><th>SCRUBBED</th><th>STATE</th><th/></tr></thead><tbody>
     {shown.map(e=><tr key={e.id}><td>#{e.id}</td><td>{compactTask(e.task)}</td><td><code>{pretty(e.input).slice(0,150)}</code></td>
      <td><code>{pretty(e.output).slice(0,150)}</code></td><td>{e.scrubbed_count}</td><td><span className={'pill '+(e.state==='approved'?'live':'quiet')}>{e.state}</span></td>
      <td>{e.state==='draft'&&<button className="small-button" disabled={busy} onClick={()=>void approve(e.id)}><ShieldCheck size={14}/> Approve</button>}</td></tr>)}
    </tbody></table></div>
    {shown.length===0&&<p className="fine">No examples for this filter.</p>}
   </section>
   <section className="panel"><div className="panel-heading"><div><h2>Retrieval and training</h2><p>Retrieve approved examples, then train and evaluate a company model.</p></div><Pill tone="quiet">{capabilities?.default_method??'deterministic'}</Pill></div>
    <div className="learn-grid">
     <div><label className="field-label" htmlFor="rag-query">Retrieval query</label><textarea id="rag-query" rows={3} value={query} onChange={e=>setQuery(e.target.value)} placeholder="VEND_MAST vendor amount"/><button className="small-button" disabled={busy||query.trim().length<2} onClick={()=>void retrieve()}><Search size={15}/> Retrieve</button></div>
     <div><label className="field-label" htmlFor="train-method">Method</label><select id="train-method" value={method} onChange={e=>setMethod(e.target.value)}>
      <option value="deterministic">Deterministic learned model (default)</option><option value="lora">LoRA manifest (opt-in offline script)</option></select>
      <label className="field-label" htmlFor="train-epochs">Epochs</label><input id="train-epochs" type="number" min={1} max={20} value={epochs} onChange={e=>setEpochs(Number(e.target.value))}/>
      <button className="small-button" disabled={busy} onClick={()=>void train()}><Brain size={15}/> Train &amp; evaluate</button></div>
    </div>
    {hits.length>0&&<div className="match-list"><div className="eyebrow">APPROVED MATCHES ({hits.length})</div>{hits.map(h=><div className="match" key={h.id}><b>Example #{h.id} · score {scoreLabel(h.score)}</b><p><code>{pretty(h.output).slice(0,240)}</code></p></div>)}</div>}
    {runs.length>0&&<div className="table-wrap"><table><thead><tr><th>RUN</th><th>TASK</th><th>METHOD</th><th>STATUS</th><th>ACCURACY</th><th>DETAIL</th></tr></thead><tbody>
     {runs.slice(0,10).map(r=><tr key={r.id}><td>#{r.id}</td><td>{compactTask(r.task)}</td><td>{r.method}</td><td><span className={'pill '+(r.status==='evaluated'?'live':'quiet')}>{r.status}</span></td>
      <td>{formatAccuracy(r.metrics)}</td><td>{r.error||<code>{pretty(r.metrics).slice(0,120)}</code>}</td></tr>)}
    </tbody></table></div>}
    {models.length>0&&<div className="table-wrap"><table><thead><tr><th>MODEL</th><th>TASK</th><th>VERSION</th><th>STATE</th><th>ACCURACY</th><th/></tr></thead><tbody>
     {models.map(m=><tr key={m.id}><td>#{m.id}</td><td>{compactTask(m.task)}</td><td>v{m.version}</td><td><span className={'pill '+(m.state==='active'?'live':'quiet')}>{m.state}</span></td><td>{formatAccuracy(m.metrics)}</td>
      <td>{m.state==='candidate'&&<button className="small-button" disabled={busy} onClick={()=>void approveModel(m.id)}><CheckCircle2 size={14}/> Activate</button>}</td></tr>)}
    </tbody></table></div>}
    <p className="fine">{capabilities?.note||'Training uses approved examples only.'} Optional LoRA packages: {capabilities?Object.entries(capabilities.optional_lora_dependencies).map(([k,v])=>k+'='+(v?'present':'missing')).join(', '):'loading…'} · Live DB sources: {capabilities?.live_db_sources_enabled?'enabled':'disabled'}</p>
   </section>
   <section className="panel"><div className="panel-heading"><div><h2>Predict with an approved model</h2><p>Falls back to approved-example retrieval when no model is active for the task.</p></div></div>
    <label className="field-label" htmlFor="predict-input">Input JSON</label><textarea id="predict-input" rows={4} value={predictText} onChange={e=>setPredictText(e.target.value)}/>
    <button className="primary" disabled={busy} onClick={()=>void predict()}><Brain size={16}/> Predict</button>
    {prediction&&<div className="prediction"><div className="eyebrow">{prediction.mode.toUpperCase()} · CONFIDENCE {scoreLabel(prediction.confidence)}</div>
     <h3>{compactTask(task)}</h3><pre>{pretty(prediction.prediction)}</pre>
     <p className="fine">Provenance: {pretty(prediction.provenance)}</p><p className="fine">{prediction.warning}</p>
     {prediction.supporting_examples.length>0&&<p className="fine">Supporting approved examples: {prediction.supporting_examples.map(h=>'#'+h.id).join(', ')}</p>}
    </div>}
   </section>
  </>}
 </div>;
}
function Pill({children,tone='normal'}:{children:React.ReactNode;tone?:string}){return <span className={'pill '+tone}>{children}</span>}
