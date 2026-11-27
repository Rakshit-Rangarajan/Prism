import React,{useEffect,useState} from 'react';
import {PrismBrand} from './PrismBrand';

type Props={children:(logout:()=>Promise<void>)=>React.ReactNode};
export function SignIn({children}:Props){
 const [authenticated,setAuthenticated]=useState(false),[checking,setChecking]=useState(true),[username,setUsername]=useState('prism'),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let active=true;fetch('/api/auth/session').then(async r=>{if(!r.ok)throw Error('PRISM login is unavailable. Check the server configuration.');return r.json()}).then(s=>{if(active)setAuthenticated(s.authenticated)}).catch(e=>{if(active)setError(String(e))}).finally(()=>{if(active)setChecking(false)});return()=>{active=false}},[]);
 async function login(event:React.FormEvent){event.preventDefault();setBusy(true);setError('');try{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});const data=await r.json();if(!r.ok)throw Error(data.detail||'Sign-in failed');setPassword('');setAuthenticated(true)}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 async function logout(){setError('');try{const r=await fetch('/api/auth/logout',{method:'POST'});if(!r.ok)throw Error('Could not sign out');setAuthenticated(false);setPassword('')}catch(e){setError(String(e))}}
 if(checking)return <div className="signin-page" role="status">Connecting to PRISM…</div>;
 if(authenticated)return <>{children(logout)}</>;
 return <main className="signin-page"><section className="signin-card"><PrismBrand/><div className="eyebrow">SECURE MIGRATION WORKSPACE</div><h1>Welcome to PRISM</h1><p>Sign in to review your source data, local AI recommendations and approved migration memory.</p><form onSubmit={login}><label htmlFor="signin-username">Username</label><input id="signin-username" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required disabled={busy}/><label htmlFor="signin-password">Password</label><input id="signin-password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required disabled={busy}/>{error&&<p className="error" role="alert">{error}</p>}<button className="primary" disabled={busy}>{busy?'Signing in…':'Sign in'}</button></form><p className="fine">For this PC, use the password in <b>PRISM Local Access.txt</b> in the demo Outputs folder. The hosted demo has its own server password.</p></section></main>
}
