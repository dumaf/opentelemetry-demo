import { useEffect, useState } from 'react'
import './App.css'

const API = 'http://localhost:8090'

type Page = 'dashboard' | 'faults' | 'incidents' | 'approvals' | 'logs' | 'metrics' | 'traces' | 'settings'

async function api(path: string, opts?: RequestInit) {
  const r = await fetch(API + path, opts)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

function useFetch(path: string) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setLoading(true); setError(null)
    api(path).then(setData).catch(e => setError(String(e))).finally(() => setLoading(false))
  }, [path])
  return { data, loading, error, reload: () => { setLoading(true); api(path).then(setData).catch(e=>setError(String(e))).finally(()=>setLoading(false)) } }
}

function Dashboard() {
  const avail = useFetch('/api/telemetry/availability')
  const incs = useFetch('/api/incidents')
  const faults = useFetch('/api/faults/status/all')
  const approvals = useFetch('/api/approvals')
  return (
    <div>
      <h2>Dashboard</h2>
      <div className="card">
        <h3>Telemetry availability</h3>
        {avail.loading && <p className="muted">Loading...</p>}
        {avail.error && <p className="error">{avail.error}</p>}
        {avail.data && <pre>{JSON.stringify(avail.data, null, 2)}</pre>}
      </div>
      <div className="card">
        <h3>Recent incidents ({Array.isArray(incs.data) ? incs.data.length : 0})</h3>
        {incs.loading && <p className="muted">Loading...</p>}
        {incs.error && <p className="error">{incs.error}</p>}
        {Array.isArray(incs.data) && incs.data.length === 0 && <p className="empty">No incidents detected yet.</p>}
        {Array.isArray(incs.data) && incs.data.map((i: any) => (
          <div key={i.id} className="stat" style={{marginBottom:8}}>
            <div><b>{i.id}</b> — {i.severity}</div>
            <div className="muted">{i.detection_ts} · {JSON.parse(i.affected_services || '[]').join(', ')}</div>
          </div>
        ))}
      </div>
      <div className="card">
        <h3>Pending approvals ({Array.isArray(approvals.data) ? approvals.data.length : 0})</h3>
        {Array.isArray(approvals.data) && approvals.data.length === 0 && <p className="empty">No pending approvals.</p>}
        {Array.isArray(approvals.data) && approvals.data.map((a:any) => (
          <div key={a.id}>{a.id} — {a.action} on {a.target}</div>
        ))}
      </div>
      <div className="card">
        <h3>Active faults</h3>
        {Array.isArray(faults.data) && faults.data.filter((f:any)=>f.state==='active').length === 0 && <p className="empty">None active.</p>}
        {Array.isArray(faults.data) && faults.data.filter((f:any)=>f.state==='active').map((f:any)=>(
          <div key={f.flag}>{f.flag}: {f.current}</div>
        ))}
      </div>
    </div>
  )
}

function Faults() {
  const faults = useFetch('/api/faults')
  const [selected, setSelected] = useState<string | null>(null)
  const [variant, setVariant] = useState('')
  const [msg, setMsg] = useState('')
  const trigger = async () => {
    if (!selected || !variant) return
    try {
      const r = await api(`/api/faults/${selected}/trigger`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({variant})})
      setMsg('Approval required. Approval ID: ' + (r.approval?.id || '?') + '. Go to Approvals page to approve and execute.')
    } catch (e) { setMsg('Error: ' + String(e)) }
  }
  const reset = async (f: string) => {
    try {
      const r = await api(`/api/faults/${f}/reset`, {method:'POST'})
      setMsg('Approval required. Approval ID: ' + (r.approval?.id || '?') + '. Go to Approvals page.')
    } catch (e) { setMsg('Error: ' + String(e)) }
  }
  return (
    <div>
      <h2>Faults</h2>
      {msg && <p className="muted">{msg}</p>}
      {faults.loading && <p className="muted">Loading...</p>}
      {faults.error && <p className="error">{faults.error}</p>}
      {Array.isArray(faults.data) && (
        <table>
          <thead><tr><th>Flag</th><th>Service</th><th>Variants</th><th>Default</th><th>Actions</th></tr></thead>
          <tbody>
            {faults.data.map((f:any) => (
              <tr key={f.flag_key}>
                <td>{f.flag_key}</td>
                <td>{f.affected_service}</td>
                <td>{f.available_variants.join(', ')}</td>
                <td>{f.configured_default}</td>
                <td>
                  <button className="primary" onClick={()=>{setSelected(f.flag_key); setVariant(f.available_variants.find((v:string)=>v!=='off')||'off')}}>Select</button>
                  {' '}
                  <button onClick={()=>reset(f.flag_key)}>Reset</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {selected && (
        <div className="card">
          <h3>Trigger {selected}</h3>
          <select value={variant} onChange={e=>setVariant(e.target.value)}>
            {faults.data?.find((f:any)=>f.flag_key===selected)?.available_variants.map((v:string)=><option key={v} value={v}>{v}</option>)}
          </select>
          <button className="danger" onClick={trigger} style={{marginLeft:8}}>Trigger</button>
          <p className="muted">Confirmation required by operator before activation.</p>
        </div>
      )}
    </div>
  )
}

function Incidents() {
  const incs = useFetch('/api/incidents')
  const diags = useFetch('/api/brain/diagnoses')
  const [report, setReport] = useState<any>(null)
  const [mode, setMode] = useState('controlled')
  const analyze = async (id: string) => {
    try {
      const r = await api(`/api/incidents/${id}/analyze`, {method:'POST'})
      setReport(r)
    } catch (e) { setReport({error: String(e)}) }
  }
  const brainRun = async (id: string) => {
    try {
      const r = await api(`/api/brain/incidents/${id}/diagnose`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({detection_mode: mode})})
      setReport(r)
    } catch (e) { setReport({error: String(e)}) }
  }
  const brainEval = async (did: string) => {
    try {
      const r = await api(`/api/brain/diagnoses/${did}/evaluate`, {method:'POST'})
      setReport(r)
    } catch (e) { setReport({error: String(e)}) }
  }
  return (
    <div>
      <h2>Incidents</h2>
      <div className="card">
        <label>Detection mode for Brain: </label>
        <select value={mode} onChange={e=>setMode(e.target.value)}>
          <option value="controlled">controlled</option>
          <option value="blind">blind</option>
        </select>
      </div>
      {Array.isArray(incs.data) && incs.data.length === 0 && <p className="empty">No incidents. Trigger a fault and wait for detection.</p>}
      {Array.isArray(incs.data) && incs.data.map((i:any) => (
        <div key={i.id} className="card">
          <div><b>{i.id}</b> — {i.severity} — {i.status}</div>
          <div className="muted">{i.detection_ts} · {JSON.parse(i.affected_services || '[]').join(', ')}</div>
          <div style={{marginTop:8}}>
            <button className="primary" onClick={()=>analyze(i.id)}>Run Eyes</button>
            <button className="danger" onClick={()=>brainRun(i.id)} style={{marginLeft:8}}>Run Brain</button>
            <button onClick={async ()=>{const r=await api(`/api/incidents/${i.id}/evidence`); setReport(r)}} style={{marginLeft:8}}>Evidence</button>
          </div>
        </div>
      ))}
      <h3>Brain diagnoses</h3>
      {Array.isArray(diags.data) && diags.data.length === 0 && <p className="empty">No diagnoses yet.</p>}
      {Array.isArray(diags.data) && diags.data.map((d:any) => (
        <div key={d.id} className="card">
          <div><b>{d.id}</b> — incident {d.incident_id} — valid={String(d.valid)}</div>
          <div className="muted">{d.created_ts} · mode={d.detection_mode}</div>
          <button onClick={async ()=>{const r=await api(`/api/brain/diagnoses/${d.id}`); setReport(r)}} style={{marginLeft:0,marginTop:8}}>View</button>
          <button onClick={()=>brainEval(d.id)} style={{marginLeft:8,marginTop:8}}>Evaluate</button>
        </div>
      ))}
      {report && <div className="card"><h3>Result</h3><pre>{JSON.stringify(report, null, 2)}</pre></div>}
    </div>
  )
}

function Logs() {
  const [svc, setSvc] = useState('')
  const [sev, setSev] = useState('')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const search = async () => {
    setLoading(true)
    try { setData(await api(`/api/telemetry/logs?service=${svc}&severity=${sev}&limit=50`)) } catch(e){ setData({error:String(e)}) }
    setLoading(false)
  }
  return (
    <div>
      <h2>Logs</h2>
      <div className="card">
        <input placeholder="service" value={svc} onChange={e=>setSvc(e.target.value)} />
        <select value={sev} onChange={e=>setSev(e.target.value)} style={{marginLeft:8}}>
          <option value="">any</option><option>ERROR</option><option>WARN</option><option>INFO</option>
        </select>
        <button className="primary" onClick={search} style={{marginLeft:8}}>Search</button>
      </div>
      {loading && <p className="muted">Loading...</p>}
      {data?.available === false && <p className="muted">OpenSearch unavailable.</p>}
      {Array.isArray(data?.data) && data.data.map((l:any,i:number)=>(
        <div key={i} className="card"><pre>{JSON.stringify(l.payload)}</pre><div className="muted">{l.timestamp} {l.service}</div></div>
      ))}
    </div>
  )
}

function Metrics() {
  const [q, setQ] = useState('up')
  const [data, setData] = useState<any>(null)
  const run = async () => { try { setData(await api(`/api/telemetry/prometheus/query?q=${encodeURIComponent(q)}`)) } catch(e){ setData({error:String(e)}) } }
  return (
    <div>
      <h2>Metrics</h2>
      <div className="card">
        <input value={q} onChange={e=>setQ(e.target.value)} style={{width:300}} />
        <button className="primary" onClick={run} style={{marginLeft:8}}>Query</button>
      </div>
      {data?.available === false && <p className="muted">Prometheus unavailable.</p>}
      {Array.isArray(data?.data) && <pre>{JSON.stringify(data.data.slice(0,20), null, 2)}</pre>}
    </div>
  )
}

function Traces() {
  const [svc, setSvc] = useState('')
  const [data, setData] = useState<any>(null)
  const run = async () => { try { setData(await api(`/api/telemetry/traces?service=${svc}&limit=20`)) } catch(e){ setData({error:String(e)}) } }
  return (
    <div>
      <h2>Traces</h2>
      <div className="card">
        <input placeholder="service" value={svc} onChange={e=>setSvc(e.target.value)} />
        <button className="primary" onClick={run} style={{marginLeft:8}}>Load</button>
      </div>
      {data?.available === false && <p className="muted">Jaeger unavailable.</p>}
      {Array.isArray(data?.data) && data.data.map((t:any,i:number)=>(
        <div key={i} className="card"><div>{t.payload?.trace_id} spans={t.payload?.span_count} error={String(t.payload?.has_error)}</div><div className="muted">{t.timestamp}</div></div>
      ))}
    </div>
  )
}

function Settings() {
  const m = useFetch('/api/settings/model')
  const t = useFetch('/api/settings/telemetry')
  const h = useFetch('/api/brain/model/health')
  return (
    <div>
      <h2>Settings</h2>
      <div className="card"><h3>Model</h3><pre>{JSON.stringify(m.data, null, 2)}</pre></div>
      <div className="card"><h3>Model connectivity</h3><pre>{JSON.stringify(h.data, null, 2)}</pre></div>
      <div className="card"><h3>Telemetry backends</h3><pre>{JSON.stringify(t.data, null, 2)}</pre></div>
      <p className="muted">Credentials are kept on the backend only and never exposed.</p>
    </div>
  )
}

function Approvals() {
  const pending = useFetch('/api/approvals')
  const [msg, setMsg] = useState('')
  const decide = async (id: string, approve: boolean) => {
    try {
      const r = await api(`/api/approvals/${id}/${approve?'approve':'reject'}`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({actor:'human'})})
      setMsg(JSON.stringify(r))
    } catch (e) { setMsg('Error: ' + String(e)) }
  }
  const exec = async (id: string) => {
    try {
      const r = await api(`/api/approvals/${id}/execute`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({actor:'human'})})
      setMsg(JSON.stringify(r))
    } catch (e) { setMsg('Error: ' + String(e)) }
  }
  return (
    <div>
      <h2>Pending Approvals</h2>
      {msg && <p className="muted">{msg}</p>}
      {Array.isArray(pending.data) && pending.data.length === 0 && <p className="empty">No pending approvals.</p>}
      {Array.isArray(pending.data) && pending.data.map((a:any) => (
        <div key={a.id} className="card">
          <div><b>{a.id}</b> — {a.action} on {a.target}</div>
          <div className="muted">risk={a.risk} reversible={String(a.reversible)} expires={a.expires_ts}</div>
          <pre>{JSON.stringify(a.params, null, 2)}</pre>
          <div style={{marginTop:8}}>
            <button className="primary" onClick={()=>decide(a.id, true)}>Approve</button>
            <button onClick={()=>decide(a.id, false)} style={{marginLeft:8}}>Reject</button>
            <button className="danger" onClick={()=>exec(a.id)} style={{marginLeft:8}}>Execute (after approval)</button>
          </div>
        </div>
      ))}
    </div>
  )
}

const PAGES: {id: Page; label: string}[] = [
  {id:'dashboard', label:'Dashboard'},
  {id:'faults', label:'Faults'},
  {id:'incidents', label:'Incidents'},
  {id:'approvals', label:'Approvals'},
  {id:'logs', label:'Logs'},
  {id:'metrics', label:'Metrics'},
  {id:'traces', label:'Traces'},
  {id:'settings', label:'Settings'},
]

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  return (
    <div className="app">
      <aside className="sidebar">
        <h3>Eyes</h3>
        {PAGES.map(p => (
          <button key={p.id} className={page===p.id?'active':''} onClick={()=>setPage(p.id)}>{p.label}</button>
        ))}
      </aside>
      <main className="main">
        {page==='dashboard' && <Dashboard/>}
        {page==='faults' && <Faults/>}
        {page==='incidents' && <Incidents/>}
        {page==='approvals' && <Approvals/>}
        {page==='logs' && <Logs/>}
        {page==='metrics' && <Metrics/>}
        {page==='traces' && <Traces/>}
        {page==='settings' && <Settings/>}
      </main>
    </div>
  )
}
