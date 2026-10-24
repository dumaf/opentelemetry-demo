import React, { useEffect, useState } from 'react'
import './App.css'
import {
  EyeIcon,
  BrainIcon,
  DashboardIcon,
  ZapIcon,
  AlertTriangleIcon,
  ShieldCheckIcon,
  TerminalIcon,
  ActivityIcon,
  LayersIcon,
  SettingsIcon,
  RefreshIcon,
  SearchIcon,
  CheckIcon,
  XIcon,
  PlayIcon,
  RotateCcwIcon,
  ServerIcon,
  PowerIcon,
  FileTextIcon
} from './components/Icons'

const API = 'http://localhost:8090'

type Page = 'dashboard' | 'faults' | 'incidents' | 'approvals' | 'logs' | 'metrics' | 'traces' | 'settings'

async function api(path: string, opts?: RequestInit) {
  const r = await fetch(API + path, opts)
  if (!r.ok) {
    let errMessage = `${r.status} ${r.statusText}`
    try {
      const errBody = await r.json()
      if (errBody.detail) errMessage = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail)
    } catch {
      // ignore json parse error
    }
    throw new Error(errMessage)
  }
  return r.json()
}

function useFetch<T = any>(path: string, pollInterval?: number) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    api(path)
      .then(setData)
      .catch(e => setError(String(e.message || e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    if (pollInterval) {
      const id = setInterval(load, pollInterval)
      return () => clearInterval(id)
    }
  }, [path, pollInterval])

  return { data, loading, error, reload: load }
}

interface ModalProps {
  title: string
  isOpen: boolean
  onClose: () => void
  children: React.ReactNode
}

function Modal({ title, isOpen, onClose, children }: ModalProps) {
  if (!isOpen) return null
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3 className="card-title">{title}</h3>
          <button className="btn btn-secondary btn-sm" onClick={onClose}>
            <XIcon size={14} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        <div className="modal-footer">
          <button className="btn btn-secondary btn-sm" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}

function Dashboard({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const avail = useFetch('/api/telemetry/availability', 5000)
  const incs = useFetch('/api/incidents', 4000)
  const faults = useFetch('/api/faults/status/all', 5000)
  const approvals = useFetch('/api/approvals', 3000)
  const allApprovals = useFetch('/api/approvals/all', 4000)
  const auditLog = useFetch('/api/approvals/audit', 4000)
  const diags = useFetch('/api/brain/diagnoses', 4000)
  const modelHealth = useFetch('/api/brain/model/health', 8000)

  const [approvalTab, setApprovalTab] = useState<'pending' | 'history'>('pending')
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [modalTitle, setModalTitle] = useState('')
  const [modalData, setModalData] = useState<any>(null)

  const activeFaultsCount = Array.isArray(faults.data)
    ? faults.data.filter((f: any) => f.state === 'active').length
    : 0

  const openIncidentsCount = Array.isArray(incs.data) ? incs.data.length : 0
  const pendingApprovalsCount = Array.isArray(approvals.data) ? approvals.data.length : 0

  const decide = async (id: string, approveAction: boolean) => {
    setBusy(true)
    try {
      await api(`/api/approvals/${id}/${approveAction ? 'approve' : 'reject'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor: 'human_operator' })
      })
      setFeedbackMsg({
        type: 'success',
        text: `Proposal ${id} ${approveAction ? 'APPROVED. You may now execute the action.' : 'REJECTED.'}`
      })
      approvals.reload()
      allApprovals.reload()
      auditLog.reload()
    } catch (e: any) {
      setFeedbackMsg({ type: 'error', text: `Approval failed: ${e.message || e}` })
    } finally {
      setBusy(false)
    }
  }

  const exec = async (id: string) => {
    setBusy(true)
    try {
      const res = await api(`/api/approvals/${id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor: 'human_operator' })
      })
      setFeedbackMsg({
        type: 'success',
        text: `Action executed successfully: ${JSON.stringify(res.result || res)}`
      })
      approvals.reload()
      allApprovals.reload()
      auditLog.reload()
      faults.reload()
    } catch (e: any) {
      setFeedbackMsg({ type: 'error', text: `Execution failed: ${e.message || e}` })
    } finally {
      setBusy(false)
    }
  }

  const analyze = async (id: string) => {
    setBusy(true)
    try {
      const r = await api(`/api/incidents/${id}/analyze`, { method: 'POST' })
      setModalTitle(`Eyes Incident Investigation — ${id}`)
      setModalData(r)
      incs.reload()
    } catch (e: any) {
      setFeedbackMsg({ type: 'error', text: `Analysis error: ${e.message || e}` })
    } finally {
      setBusy(false)
    }
  }

  const brainRun = async (id: string) => {
    setBusy(true)
    try {
      const r = await api(`/api/brain/incidents/${id}/diagnose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ detection_mode: 'controlled' })
      })
      setModalTitle(`Brain AI Diagnosis — ${id}`)
      setModalData(r)
      diags.reload()
      incs.reload()
    } catch (e: any) {
      setFeedbackMsg({ type: 'error', text: `Diagnosis error: ${e.message || e}` })
    } finally {
      setBusy(false)
    }
  }

  const viewEvidence = async (id: string) => {
    setBusy(true)
    try {
      const r = await api(`/api/incidents/${id}/evidence`)
      setModalTitle(`Evidence Bundle — ${id}`)
      setModalData(r)
    } catch (e: any) {
      setFeedbackMsg({ type: 'error', text: `Evidence error: ${e.message || e}` })
    } finally {
      setBusy(false)
    }
  }

  // Map diagnoses by incident_id
  const diagMap = new Map<string, any>()
  if (Array.isArray(diags.data)) {
    diags.data.forEach((d: any) => {
      if (d.incident_id && !diagMap.has(d.incident_id)) {
        try {
          const payload = typeof d.payload_json === 'string' ? JSON.parse(d.payload_json) : d.payload_json
          diagMap.set(d.incident_id, { ...d, parsed: payload })
        } catch {
          diagMap.set(d.incident_id, d)
        }
      }
    })
  }

  return (
    <div className="content-area">
      {/* KPI Stats */}
      <div className="stat-grid">
        <div className="stat-card" onClick={() => onNavigate('faults')} style={{ cursor: 'pointer' }}>
          <div className={`stat-icon ${activeFaultsCount > 0 ? 'danger' : 'success'}`}>
            <ZapIcon size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-label">Active Faults</span>
            <span className="stat-value">{faults.loading ? '...' : activeFaultsCount}</span>
            <span className="stat-desc">{activeFaultsCount > 0 ? 'Injected anomalies active' : 'All systems baseline'}</span>
          </div>
        </div>

        <div className="stat-card" onClick={() => onNavigate('incidents')} style={{ cursor: 'pointer' }}>
          <div className="stat-icon warning">
            <AlertTriangleIcon size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-label">Observed Incidents</span>
            <span className="stat-value">{incs.loading ? '...' : openIncidentsCount}</span>
            <span className="stat-desc">Blind detection active</span>
          </div>
        </div>

        <div className="stat-card" onClick={() => onNavigate('approvals')} style={{ cursor: 'pointer' }}>
          <div className={`stat-icon ${pendingApprovalsCount > 0 ? 'danger' : 'primary'}`}>
            <ShieldCheckIcon size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-label">Pending Approvals</span>
            <span className="stat-value">{approvals.loading ? '...' : pendingApprovalsCount}</span>
            <span className="stat-desc">{pendingApprovalsCount > 0 ? 'Awaiting human authorization' : 'No pending actions'}</span>
          </div>
        </div>

        <div className="stat-card" onClick={() => onNavigate('settings')} style={{ cursor: 'pointer' }}>
          <div className="stat-icon success">
            <ServerIcon size={20} />
          </div>
          <div className="stat-info">
            <span className="stat-label">Telemetry & LLM Health</span>
            <span className="stat-value">
              {avail.data ? Object.values(avail.data).filter(Boolean).length : 0}/4
            </span>
            <span className="stat-desc">
              {modelHealth.data?.has_credentials ? 'LLM Connected' : 'LLM Not Ready'}
            </span>
          </div>
        </div>
      </div>

      {feedbackMsg && (
        <div className={`alert-banner ${feedbackMsg.type === 'error' ? 'danger' : feedbackMsg.type === 'success' ? 'success' : 'warning'}`}>
          {feedbackMsg.text}
        </div>
      )}

      {/* CORE PRODUCT FEATURE: Human Approval & Remediation Center directly in Dashboard */}
      <div className="card" style={{ borderLeft: pendingApprovalsCount > 0 ? '4px solid var(--warning)' : '4px solid var(--primary)' }}>
        <div className="card-header">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 className="card-title">
                <ShieldCheckIcon size={18} color="var(--primary)" />
                Human Approval & Remediation Control Center
              </h3>
              {pendingApprovalsCount > 0 ? (
                <span className="badge badge-critical">
                  <span className="dot pulse" /> {pendingApprovalsCount} Awaiting Operator Action
                </span>
              ) : (
                <span className="badge badge-inactive">Safe · All Proposals Decided</span>
              )}
            </div>
            <p className="card-subtitle">
              Every state-changing remediation requires explicit human authorization before Action API execution.
            </p>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <div style={{ display: 'flex', background: 'var(--bg-input)', padding: 3, borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
              <button
                className={`btn btn-sm ${approvalTab === 'pending' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ border: 'none', background: approvalTab === 'pending' ? 'var(--primary)' : 'transparent' }}
                onClick={() => setApprovalTab('pending')}
              >
                Pending ({pendingApprovalsCount})
              </button>
              <button
                className={`btn btn-sm ${approvalTab === 'history' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ border: 'none', background: approvalTab === 'history' ? 'var(--primary)' : 'transparent' }}
                onClick={() => setApprovalTab('history')}
              >
                History & Recovery
              </button>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={() => { approvals.reload(); allApprovals.reload(); auditLog.reload(); }}>
              <RefreshIcon size={14} /> Refresh
            </button>
          </div>
        </div>

        {approvalTab === 'pending' && (
          <div>
            {approvals.loading && <p style={{ color: 'var(--text-muted)' }}>Checking approval queue...</p>}
            {Array.isArray(approvals.data) && approvals.data.length === 0 && (
              <div className="empty-state">
                <div className="empty-icon"><CheckIcon size={24} color="var(--success)" /></div>
                <span>All proposals decided. No remediation actions awaiting approval.</span>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {Array.isArray(approvals.data) &&
                approvals.data.map((a: any) => {
                  const riskClass =
                    a.risk === 'high' ? 'badge-critical' : a.risk === 'medium' ? 'badge-high' : 'badge-medium'

                  const isPending = a.status === 'pending'
                  const isApproved = a.status === 'approved'

                  return (
                    <div
                      key={a.id}
                      style={{
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-lg)',
                        padding: '16px 20px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 12
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <span className={`badge ${riskClass}`}>RISK: {a.risk || 'MEDIUM'}</span>
                          <span className="badge badge-low">STATUS: {a.status.toUpperCase()}</span>
                          <b style={{ color: '#fff', fontSize: 14 }}>{a.id}</b>
                          <span className="service-tag">{a.action}</span>
                          <span style={{ color: 'var(--text-muted)' }}>on</span>
                          <span className="service-tag">{a.target}</span>
                        </div>
                        <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                          Expires: {a.expires_ts ? a.expires_ts.slice(11, 19) : 'N/A'}
                        </span>
                      </div>

                      {/* Rationale and Rollback Info */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                          <b>Rationale & Expected Outcome: </b>{a.reason || 'Remediate anomaly and return target to baseline state.'}
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                          <b>Reversible: </b>{a.reversible ? 'Yes (Can be rolled back via Action API)' : 'No'} · <b>Requester: </b>system/operator
                        </div>
                      </div>

                      {/* Parameters Box */}
                      {a.params && Object.keys(a.params).length > 0 && (
                        <div style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)', borderRadius: 6, padding: '8px 12px' }}>
                          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', fontWeight: 600 }}>Proposed Parameters:</div>
                          <pre style={{ margin: 0, fontSize: 12, fontFamily: 'var(--font-mono)', color: '#e2e8f0' }}>
                            {JSON.stringify(a.params, null, 2)}
                          </pre>
                        </div>
                      )}

                      {/* Action Decision Buttons */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginTop: 4 }}>
                        <span style={{ fontSize: 12, color: isApproved ? 'var(--success)' : 'var(--warning)', fontWeight: 500 }}>
                          {isApproved ? '✓ Proposal approved by human. Ready to execute through Action API.' : '⏳ Awaiting explicit human approval to proceed.'}
                        </span>

                        <div style={{ display: 'flex', gap: 8 }}>
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => decide(a.id, false)}
                            disabled={busy || !isPending}
                          >
                            <XIcon size={14} /> Reject Proposal
                          </button>
                          <button
                            className="btn btn-success btn-sm"
                            onClick={() => decide(a.id, true)}
                            disabled={busy || !isPending}
                          >
                            <CheckIcon size={14} /> Approve Proposal
                          </button>
                          <button
                            className="btn btn-danger btn-sm"
                            onClick={() => exec(a.id)}
                            disabled={busy || !isApproved}
                          >
                            <PlayIcon size={12} color="#fff" /> Execute via Action API
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
            </div>
          </div>
        )}

        {approvalTab === 'history' && (
          <div>
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Approval ID</th>
                    <th>Action</th>
                    <th>Target</th>
                    <th>Status</th>
                    <th>Approver</th>
                    <th>Execution Result</th>
                    <th>Recovery Verification</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {Array.isArray(allApprovals.data) &&
                    allApprovals.data.slice(0, 10).map((a: any) => {
                      let recovery = null
                      try {
                        const parsedRes = a.execution_result ? JSON.parse(a.execution_result) : null
                        recovery = parsedRes?.recovery_verification
                      } catch {
                        // ignore
                      }

                      return (
                        <tr key={a.id}>
                          <td><b style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{a.id}</b></td>
                          <td><span className="service-tag">{a.action}</span></td>
                          <td><span className="service-tag">{a.target}</span></td>
                          <td>
                            <span className={`badge ${a.status === 'completed' ? 'badge-inactive' : a.status === 'rejected' ? 'badge-critical' : 'badge-low'}`}>
                              {a.status.toUpperCase()}
                            </span>
                          </td>
                          <td>{a.decided_by || 'operator'}</td>
                          <td>
                            <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                              {a.execution_status || 'N/A'}
                            </span>
                          </td>
                          <td>
                            {recovery ? (
                              <span className={`badge ${recovery.recovered ? 'badge-inactive' : 'badge-high'}`}>
                                {recovery.recovered ? 'VERIFIED' : 'PARTIAL'}
                              </span>
                            ) : (
                              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>—</span>
                            )}
                          </td>
                          <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                            {a.executed_ts?.slice(11, 19) || a.proposed_ts?.slice(11, 19)}
                          </td>
                        </tr>
                      )
                    })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Incidents & LLM Diagnostic Intelligence */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <AlertTriangleIcon size={18} color="var(--warning)" />
              Active Incidents & Diagnostic Intelligence
            </h3>
            <p className="card-subtitle">Real-time incident detection correlated with LLM root-cause synthesis</p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => { incs.reload(); diags.reload(); }}>
            <RefreshIcon size={14} /> Refresh
          </button>
        </div>

        {incs.loading && <p style={{ color: 'var(--text-muted)' }}>Loading incidents...</p>}
        {Array.isArray(incs.data) && incs.data.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon"><CheckIcon size={24} color="var(--success)" /></div>
            <span>No active incidents detected. All services healthy.</span>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {Array.isArray(incs.data) &&
            incs.data.slice(0, 5).map((i: any) => {
              let services: string[] = []
              try {
                services = JSON.parse(i.affected_services || '[]')
              } catch {
                services = [i.affected_services]
              }

              const sevClass =
                i.severity?.toLowerCase() === 'critical'
                  ? 'badge-critical'
                  : i.severity?.toLowerCase() === 'high'
                  ? 'badge-high'
                  : 'badge-medium'

              const diag = diagMap.get(i.id)
              const rootCause = diag?.parsed?.root_cause
              const confidence = diag?.parsed?.confidence
              const evidenceRefs = diag?.parsed?.symptoms?.flatMap((s: any) => s.evidence_refs || []) || []
              const alternatives = diag?.parsed?.alternative_hypotheses || []
              const nextSteps = diag?.parsed?.recommended_next_steps || []

              return (
                <div
                  key={i.id}
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '18px 20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span className={`badge ${sevClass}`}>{i.severity || 'UNKNOWN'}</span>
                      <b style={{ color: '#fff', fontSize: 14 }}>{i.id}</b>
                      <span className="badge badge-low">INVESTIGATION: {i.status?.toUpperCase() || 'OPEN'}</span>
                      {services.map(s => <span key={s} className="service-tag">{s}</span>)}
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      Detected: {i.detection_ts}
                    </span>
                  </div>

                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    <b>Triggering Anomaly: </b>{i.rationale || 'Telemetry threshold breach'}
                  </div>

                  {/* AI Diagnostic Intelligence Panel if diagnosis exists */}
                  {diag ? (
                    <div
                      style={{
                        background: 'rgba(99, 102, 241, 0.05)',
                        border: '1px solid rgba(99, 102, 241, 0.2)',
                        borderRadius: 'var(--radius-md)',
                        padding: '14px 16px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 10
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <BrainIcon size={16} color="var(--primary)" />
                          <b style={{ color: '#fff', fontSize: 13 }}>Brain AI Root Cause Diagnosis:</b>
                          {rootCause?.status && (
                            <span className={`badge ${rootCause.status === 'confirmed' ? 'badge-inactive' : rootCause.status === 'hypothesized' ? 'badge-high' : 'badge-critical'}`}>
                              STATUS: {rootCause.status.toUpperCase()}
                            </span>
                          )}
                        </div>

                        {confidence?.score !== undefined && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                            <span style={{ color: 'var(--text-muted)' }}>Confidence:</span>
                            <b style={{ color: confidence.score >= 0.7 ? 'var(--success)' : confidence.score >= 0.4 ? 'var(--warning)' : 'var(--danger)' }}>
                              {(confidence.score * 100).toFixed(0)}%
                            </b>
                          </div>
                        )}
                      </div>

                      <div style={{ fontSize: 13, color: '#e2e8f0' }}>
                        {rootCause?.description || diag.parsed?.summary || 'Diagnosis completed.'}
                      </div>

                      {evidenceRefs.length > 0 && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', fontSize: 12 }}>
                          <span style={{ color: 'var(--text-muted)' }}>Supporting Evidence:</span>
                          {evidenceRefs.slice(0, 6).map((ref: string, idx: number) => (
                            <span key={idx} style={{ background: 'var(--primary-bg)', color: 'var(--primary)', padding: '1px 6px', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                              {ref}
                            </span>
                          ))}
                        </div>
                      )}

                      {alternatives.length > 0 && (
                        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                          <b>Alternative Hypothesis: </b>
                          {alternatives[0]?.description || 'None documented'}
                        </div>
                      )}

                      {nextSteps.length > 0 && (
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                          <b>Proposed Remediation: </b>{nextSteps.join('; ')}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'rgba(255,255,255,0.02)', borderRadius: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                      <span>No AI diagnosis generated yet. Run Eyes investigation or Brain diagnosis below:</span>
                    </div>
                  )}

                  {/* Incident Action Buttons */}
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
                    <button className="btn btn-secondary btn-sm" onClick={() => viewEvidence(i.id)} disabled={busy}>
                      <FileTextIcon size={14} /> View Evidence
                    </button>
                    <button className="btn btn-primary btn-sm" onClick={() => analyze(i.id)} disabled={busy}>
                      <EyeIcon size={14} /> Run Eyes
                    </button>
                    <button className="btn btn-danger btn-sm" onClick={() => brainRun(i.id)} disabled={busy}>
                      <BrainIcon size={14} /> Run Brain Diagnosis
                    </button>
                  </div>
                </div>
              )
            })}
        </div>
      </div>

      {/* Two Column Section: Telemetry Backends & Audit Trail */}
      <div className="grid-2">
        {/* Telemetry Availability Card */}
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">
                <ActivityIcon size={18} color="var(--primary)" />
                Telemetry Availability
              </h3>
              <p className="card-subtitle">Backends status and health checks</p>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={avail.reload}>
              <RefreshIcon size={14} /> Refresh
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { id: 'prometheus', name: 'Prometheus (Metrics)', url: 'http://localhost:9090' },
              { id: 'jaeger', name: 'Jaeger (Traces)', url: 'http://localhost:16686' },
              { id: 'opensearch', name: 'OpenSearch (Logs)', url: 'http://localhost:9200' },
              { id: 'otel_collector', name: 'OTel Collector', url: 'http://localhost:4318' }
            ].map(b => {
              const isUp = avail.data ? Boolean(avail.data[b.id]) : false
              return (
                <div
                  key={b.id}
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: '10px 14px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <ServerIcon size={16} color="var(--text-muted)" />
                    <div>
                      <div style={{ fontWeight: 500, color: '#fff', fontSize: 13 }}>{b.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {b.url}
                      </div>
                    </div>
                  </div>
                  <span className={`status-pill ${isUp ? 'success' : 'danger'}`}>
                    <span className="dot" />
                    {isUp ? 'Online' : 'Unavailable'}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Live Audit Log Card */}
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">
                <FileTextIcon size={18} color="var(--primary)" />
                Real-Time Audit Trail
              </h3>
              <p className="card-subtitle">Immutable log of operator authorizations and safety checks</p>
            </div>
            <button className="btn btn-secondary btn-sm" onClick={auditLog.reload}>
              <RefreshIcon size={14} /> Refresh
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {Array.isArray(auditLog.data) &&
              auditLog.data.slice(0, 5).map((log: any, idx: number) => (
                <div
                  key={log.id || idx}
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: '8px 12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontSize: 12
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                      <span className="badge badge-low">{log.event_type}</span>
                      <b style={{ color: '#fff' }}>{log.action || 'system'}</b>
                      <span style={{ color: 'var(--text-muted)' }}>by {log.actor || 'operator'}</span>
                    </div>
                    <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                      Target: {log.target || 'global'} · Outcome: {log.outcome}
                    </span>
                  </div>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                    {log.ts?.slice(11, 19) || 'now'}
                  </span>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* Inspector Modal */}
      <Modal title={modalTitle} isOpen={Boolean(modalData)} onClose={() => setModalData(null)}>
        <pre className="code-box">{JSON.stringify(modalData, null, 2)}</pre>
      </Modal>
    </div>
  )
}

function Faults() {
  const faults = useFetch('/api/faults')
  const statuses = useFetch('/api/faults/status/all', 5000)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [variant, setVariant] = useState('')
  const [msg, setMsg] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const trigger = async () => {
    if (!selected || !variant) return
    setBusy(true)
    try {
      const r = await api(`/api/faults/${selected}/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variant })
      })
      setMsg({
        type: 'info',
        text: `Approval proposed (ID: ${r.approval?.id || '?'}). Please approve and execute in Approvals tab.`
      })
      statuses.reload()
    } catch (e: any) {
      setMsg({ type: 'error', text: `Trigger failed: ${e.message || e}` })
    } finally {
      setBusy(false)
    }
  }

  const reset = async (f: string) => {
    setBusy(true)
    try {
      const r = await api(`/api/faults/${f}/reset`, { method: 'POST' })
      setMsg({
        type: 'info',
        text: `Reset approval proposed (ID: ${r.approval?.id || '?'}). Please approve in Approvals.`
      })
      statuses.reload()
    } catch (e: any) {
      setMsg({ type: 'error', text: `Reset failed: ${e.message || e}` })
    } finally {
      setBusy(false)
    }
  }

  const resetAll = async () => {
    if (!confirm('Are you sure you want to restore all active feature flags to baseline?')) return
    setBusy(true)
    try {
      const r = await api(`/api/faults/reset-all`, { method: 'POST' })
      setMsg({ type: 'success', text: `Successfully reset ${r.reset ?? 0} flags back to baseline.` })
      statuses.reload()
    } catch (e: any) {
      setMsg({ type: 'error', text: `Reset-all failed: ${e.message || e}` })
    } finally {
      setBusy(false)
    }
  }

  const statusMap = new Map<string, any>()
  if (Array.isArray(statuses.data)) {
    statuses.data.forEach((s: any) => statusMap.set(s.flag, s))
  }

  const filteredFaults = Array.isArray(faults.data)
    ? faults.data.filter((f: any) => {
        const q = search.toLowerCase()
        return (
          f.flag_key.toLowerCase().includes(q) ||
          (f.affected_service && f.affected_service.toLowerCase().includes(q))
        )
      })
    : []

  return (
    <div className="content-area">
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <ZapIcon size={18} color="var(--primary)" />
              Fault Injection Inventory
            </h3>
            <p className="card-subtitle">Simulate real-world microservice failures and observe reactions</p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn btn-danger btn-sm" onClick={resetAll} disabled={busy}>
              <RotateCcwIcon size={14} /> Reset All to Baseline
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => { faults.reload(); statuses.reload(); }}>
              <RefreshIcon size={14} /> Refresh
            </button>
          </div>
        </div>

        {msg && (
          <div className={`alert-banner ${msg.type === 'error' ? 'danger' : msg.type === 'success' ? 'success' : 'info'}`} style={{ marginBottom: 16 }}>
            {msg.text}
          </div>
        )}

        {/* Search bar */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <input
              type="text"
              className="input"
              style={{ width: '100%', paddingLeft: 34 }}
              placeholder="Search by fault name or affected service (e.g. cart, payment)..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <div style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-muted)' }}>
              <SearchIcon size={16} />
            </div>
          </div>
        </div>

        {/* Table */}
        {faults.loading && <p style={{ color: 'var(--text-muted)' }}>Loading fault inventory...</p>}
        {faults.error && <p style={{ color: 'var(--danger)' }}>{faults.error}</p>}

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Fault Flag</th>
                <th>Target Service</th>
                <th>Current / Baseline</th>
                <th>Available Variants</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredFaults.map((f: any) => {
                const liveStatus = statusMap.get(f.flag_key)
                const isActive = liveStatus?.state === 'active'
                const currentVariant = liveStatus?.current || f.configured_default

                return (
                  <tr key={f.flag_key}>
                    <td>
                      <span className={`badge ${isActive ? 'badge-active' : 'badge-inactive'}`}>
                        {isActive ? 'ACTIVE' : 'INACTIVE'}
                      </span>
                    </td>
                    <td>
                      <b style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{f.flag_key}</b>
                    </td>
                    <td>
                      <span className="service-tag">{f.affected_service || 'shared'}</span>
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                        {currentVariant} <span style={{ color: 'var(--text-muted)' }}>/ {f.configured_default}</span>
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {f.available_variants.map((v: string) => (
                          <span
                            key={v}
                            style={{
                              padding: '2px 6px',
                              borderRadius: 4,
                              background: v === currentVariant ? 'var(--primary-bg)' : 'rgba(255,255,255,0.04)',
                              color: v === currentVariant ? 'var(--primary)' : 'var(--text-secondary)',
                              fontSize: 11,
                              fontFamily: 'var(--font-mono)'
                            }}
                          >
                            {v}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: 6 }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setSelected(f.flag_key)
                            setVariant(f.available_variants.find((v: string) => v !== 'off') || 'off')
                          }}
                        >
                          Select
                        </button>
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => reset(f.flag_key)}
                          disabled={busy || !isActive}
                        >
                          Reset
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Trigger Modal / Drawer */}
      <Modal
        title={`Trigger Fault: ${selected}`}
        isOpen={Boolean(selected)}
        onClose={() => setSelected(null)}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <p style={{ color: 'var(--text-secondary)' }}>
            Select variant to inject. State changes require confirmation via the Human-in-the-Loop Approval workflow.
          </p>

          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-secondary)' }}>
              Target Variant
            </label>
            <select
              className="select"
              value={variant}
              onChange={e => setVariant(e.target.value)}
              style={{ width: '100%' }}
            >
              {faults.data
                ?.find((f: any) => f.flag_key === selected)
                ?.available_variants.map((v: string) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
            </select>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 10 }}>
            <button className="btn btn-secondary" onClick={() => setSelected(null)}>Cancel</button>
            <button className="btn btn-danger" onClick={trigger} disabled={busy}>
              <PlayIcon size={12} color="#fff" /> Submit Injection Proposal
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

function Incidents() {
  const incs = useFetch('/api/incidents', 5000)
  const diags = useFetch('/api/brain/diagnoses', 5000)
  const [modalTitle, setModalTitle] = useState('')
  const [inspectData, setInspectData] = useState<any>(null)
  const [mode, setMode] = useState<'controlled' | 'blind'>('controlled')
  const [busy, setBusy] = useState(false)

  const analyze = async (id: string) => {
    setBusy(true)
    try {
      const r = await api(`/api/incidents/${id}/analyze`, { method: 'POST' })
      setModalTitle(`Eyes Analysis Report — ${id}`)
      setInspectData(r)
    } catch (e: any) {
      setModalTitle(`Eyes Analysis Error`)
      setInspectData({ error: e.message || String(e) })
    } finally {
      setBusy(false)
    }
  }

  const brainRun = async (id: string) => {
    setBusy(true)
    try {
      const r = await api(`/api/brain/incidents/${id}/diagnose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ detection_mode: mode })
      })
      setModalTitle(`Brain Diagnosis Result — ${id}`)
      setInspectData(r)
      diags.reload()
    } catch (e: any) {
      setModalTitle(`Brain Diagnosis Error`)
      setInspectData({ error: e.message || String(e) })
    } finally {
      setBusy(false)
    }
  }

  const viewEvidence = async (id: string) => {
    setBusy(true)
    try {
      const r = await api(`/api/incidents/${id}/evidence`)
      setModalTitle(`Evidence Bundle — ${id}`)
      setInspectData(r)
    } catch (e: any) {
      setModalTitle(`Evidence Unavailable`)
      setInspectData({ error: e.message || String(e) })
    } finally {
      setBusy(false)
    }
  }

  const brainEval = async (did: string) => {
    setBusy(true)
    try {
      const r = await api(`/api/brain/diagnoses/${did}/evaluate`, { method: 'POST' })
      setModalTitle(`Diagnosis Evaluation — ${did}`)
      setInspectData(r)
    } catch (e: any) {
      setModalTitle(`Evaluation Error`)
      setInspectData({ error: e.message || String(e) })
    } finally {
      setBusy(false)
    }
  }

  const viewDiag = async (did: string) => {
    setBusy(true)
    try {
      const r = await api(`/api/brain/diagnoses/${did}`)
      setModalTitle(`Diagnosis Details — ${did}`)
      setInspectData(r)
    } catch (e: any) {
      setModalTitle(`Error`)
      setInspectData({ error: e.message || String(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="content-area">
      {/* Incidents Section */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <AlertTriangleIcon size={18} color="var(--warning)" />
              Detected Incidents
            </h3>
            <p className="card-subtitle">Blind detection cycles observing anomalies across telemetry</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>LLM Diagnosis Mode:</span>
            <select
              className="select"
              value={mode}
              onChange={e => setMode(e.target.value as any)}
              style={{ padding: '4px 8px', fontSize: 12 }}
            >
              <option value="controlled">Controlled</option>
              <option value="blind">Blind (Zero prior knowledge)</option>
            </select>
            <button className="btn btn-secondary btn-sm" onClick={incs.reload}>
              <RefreshIcon size={14} /> Refresh
            </button>
          </div>
        </div>

        {incs.loading && <p style={{ color: 'var(--text-muted)' }}>Loading incidents...</p>}
        {incs.error && <p style={{ color: 'var(--danger)' }}>{incs.error}</p>}
        {Array.isArray(incs.data) && incs.data.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon"><CheckIcon size={24} /></div>
            <span>No incidents recorded yet. Trigger a fault in the Faults tab to test detection.</span>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {Array.isArray(incs.data) &&
            incs.data.map((i: any) => {
              let services: string[] = []
              try {
                services = JSON.parse(i.affected_services || '[]')
              } catch {
                services = [i.affected_services]
              }

              const sevClass =
                i.severity?.toLowerCase() === 'critical'
                  ? 'badge-critical'
                  : i.severity?.toLowerCase() === 'high'
                  ? 'badge-high'
                  : 'badge-medium'

              return (
                <div
                  key={i.id}
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '16px 20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span className={`badge ${sevClass}`}>{i.severity || 'UNKNOWN'}</span>
                      <b style={{ color: '#fff', fontSize: 14 }}>{i.id}</b>
                      <span className="badge badge-low">{i.status || 'open'}</span>
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      {i.detection_ts}
                    </span>
                  </div>

                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    {i.rationale || 'Anomaly triggered by automated telemetry threshold rule.'}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Affected Services:</span>
                      {services.map(s => (
                        <span key={s} className="service-tag">{s}</span>
                      ))}
                    </div>

                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn btn-secondary btn-sm" onClick={() => viewEvidence(i.id)} disabled={busy}>
                        <FileTextIcon size={14} /> Evidence
                      </button>
                      <button className="btn btn-primary btn-sm" onClick={() => analyze(i.id)} disabled={busy}>
                        <EyeIcon size={14} /> Run Eyes
                      </button>
                      <button className="btn btn-danger btn-sm" onClick={() => brainRun(i.id)} disabled={busy}>
                        <BrainIcon size={14} /> Run Brain
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
        </div>
      </div>

      {/* Diagnoses Section */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <BrainIcon size={18} color="var(--primary)" />
              Brain AI Root-Cause Diagnoses
            </h3>
            <p className="card-subtitle">LLM-synthesized root-cause analyses with schema validation</p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={diags.reload}>
            <RefreshIcon size={14} /> Refresh
          </button>
        </div>

        {diags.loading && <p style={{ color: 'var(--text-muted)' }}>Loading diagnoses...</p>}
        {Array.isArray(diags.data) && diags.data.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon"><BrainIcon size={24} /></div>
            <span>No AI diagnoses run yet. Click "Run Brain" on an incident above.</span>
          </div>
        )}

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Diagnosis ID</th>
                <th>Incident ID</th>
                <th>Detection Mode</th>
                <th>Schema Valid</th>
                <th>Timestamp</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {Array.isArray(diags.data) &&
                diags.data.map((d: any) => (
                  <tr key={d.id}>
                    <td><b style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{d.id}</b></td>
                    <td><span className="service-tag">{d.incident_id}</span></td>
                    <td>
                      <span className="badge badge-low">{d.detection_mode || 'controlled'}</span>
                    </td>
                    <td>
                      <span className={`badge ${d.valid ? 'badge-inactive' : 'badge-active'}`}>
                        {d.valid ? 'VALID' : 'INVALID'}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{d.created_ts?.slice(0, 19)}</td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: 6 }}>
                        <button className="btn btn-secondary btn-sm" onClick={() => viewDiag(d.id)} disabled={busy}>
                          View Details
                        </button>
                        <button className="btn btn-primary btn-sm" onClick={() => brainEval(d.id)} disabled={busy}>
                          Evaluate
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Inspector Modal */}
      <Modal title={modalTitle} isOpen={Boolean(inspectData)} onClose={() => setInspectData(null)}>
        <pre className="code-box">{JSON.stringify(inspectData, null, 2)}</pre>
      </Modal>
    </div>
  )
}

function Approvals() {
  const pending = useFetch('/api/approvals', 4000)
  const auditLog = useFetch('/api/approvals/audit', 5000)
  const killSwitch = useFetch('/api/approvals/kill-switch/status', 5000)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const decide = async (id: string, approve: boolean) => {
    setBusy(true)
    try {
      await api(`/api/approvals/${id}/${approve ? 'approve' : 'reject'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor: 'operator' })
      })
      setMsg(`Action ${approve ? 'approved' : 'rejected'}.`)
      pending.reload()
      auditLog.reload()
    } catch (e: any) {
      setMsg(`Decision failed: ${e.message || e}`)
    } finally {
      setBusy(false)
    }
  }

  const exec = async (id: string) => {
    setBusy(true)
    try {
      const r = await api(`/api/approvals/${id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor: 'operator' })
      })
      setMsg(`Executed successfully: ${JSON.stringify(r)}`)
      pending.reload()
      auditLog.reload()
    } catch (e: any) {
      setMsg(`Execution failed: ${e.message || e}`)
    } finally {
      setBusy(false)
    }
  }

  const toggleKillSwitch = async () => {
    const isCurrentlyEnabled = killSwitch.data?.enabled
    const endpoint = isCurrentlyEnabled
      ? '/api/approvals/kill-switch/disable'
      : '/api/approvals/kill-switch/enable'
    setBusy(true)
    try {
      await api(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Manual toggle from UI' })
      })
      killSwitch.reload()
    } catch (e: any) {
      setMsg(`Kill-switch toggle error: ${e.message || e}`)
    } finally {
      setBusy(false)
    }
  }

  const isKsActive = Boolean(killSwitch.data?.enabled)

  return (
    <div className="content-area">
      {/* Kill Switch Hero Card */}
      <div
        className="card"
        style={{
          borderLeft: isKsActive ? '4px solid var(--danger)' : '4px solid var(--success)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 16
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div className={`stat-icon ${isKsActive ? 'danger' : 'success'}`}>
            <PowerIcon size={22} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 style={{ fontSize: 16, fontWeight: 600 }}>Emergency Kill Switch</h3>
              <span className={`badge ${isKsActive ? 'badge-critical' : 'badge-inactive'}`}>
                {isKsActive ? 'ACTIVATED (LOCKED)' : 'DISARMED (NORMAL)'}
              </span>
            </div>
            <p style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginTop: 4 }}>
              When activated, all state-changing fault modifications and executions are immediately halted.
            </p>
          </div>
        </div>

        <button
          className={`btn ${isKsActive ? 'btn-success' : 'btn-danger'}`}
          onClick={toggleKillSwitch}
          disabled={busy}
        >
          <PowerIcon size={14} />
          {isKsActive ? 'Deactivate Kill Switch' : 'Engage Kill Switch'}
        </button>
      </div>

      {msg && <div className="alert-banner info">{msg}</div>}

      {/* Pending Approvals Queue */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <ShieldCheckIcon size={18} color="var(--primary)" />
              Pending Approvals Queue ({Array.isArray(pending.data) ? pending.data.length : 0})
            </h3>
            <p className="card-subtitle">Every automated or manual state modification requires human sign-off</p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={pending.reload}>
            <RefreshIcon size={14} /> Refresh
          </button>
        </div>

        {pending.loading && <p style={{ color: 'var(--text-muted)' }}>Loading queue...</p>}
        {Array.isArray(pending.data) && pending.data.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon"><CheckIcon size={24} /></div>
            <span>No pending approvals awaiting review.</span>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {Array.isArray(pending.data) &&
            pending.data.map((a: any) => {
              const riskClass =
                a.risk === 'high' ? 'badge-critical' : a.risk === 'medium' ? 'badge-high' : 'badge-medium'

              return (
                <div
                  key={a.id}
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '16px 20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span className={`badge ${riskClass}`}>Risk: {a.risk}</span>
                      <b style={{ color: '#fff', fontSize: 14 }}>{a.id}</b>
                      <span className="service-tag">{a.action}</span>
                      <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>on</span>
                      <span className="service-tag">{a.target}</span>
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      Expires: {a.expires_ts ? a.expires_ts.slice(11, 19) : 'N/A'}
                    </span>
                  </div>

                  {a.reason && (
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      <b>Reason: </b>{a.reason}
                    </div>
                  )}

                  {a.params && Object.keys(a.params).length > 0 && (
                    <pre className="code-box" style={{ margin: 0, padding: '8px 12px' }}>
                      {JSON.stringify(a.params, null, 2)}
                    </pre>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
                    <button className="btn btn-secondary btn-sm" onClick={() => decide(a.id, false)} disabled={busy}>
                      <XIcon size={14} /> Reject
                    </button>
                    <button className="btn btn-success btn-sm" onClick={() => decide(a.id, true)} disabled={busy}>
                      <CheckIcon size={14} /> Approve
                    </button>
                    <button className="btn btn-danger btn-sm" onClick={() => exec(a.id)} disabled={busy}>
                      <PlayIcon size={12} color="#fff" /> Execute
                    </button>
                  </div>
                </div>
              )
            })}
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <FileTextIcon size={18} color="var(--primary)" />
              Approval Audit Trail
            </h3>
            <p className="card-subtitle">Permanent record of human decisions and safety checks</p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={auditLog.reload}>
            <RefreshIcon size={14} /> Refresh
          </button>
        </div>

        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Event ID</th>
                <th>Action</th>
                <th>Actor</th>
                <th>Status</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {Array.isArray(auditLog.data) &&
                auditLog.data.slice(0, 15).map((log: any, idx: number) => (
                  <tr key={log.id || idx}>
                    <td><b style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{log.id || `#${idx + 1}`}</b></td>
                    <td><span className="service-tag">{log.action || log.event_type}</span></td>
                    <td>{log.actor || 'operator'}</td>
                    <td>
                      <span className="badge badge-low">{log.status || log.decision || 'recorded'}</span>
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                      {log.timestamp || log.created_ts || 'N/A'}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
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
    try {
      const res = await api(`/api/telemetry/logs?service=${svc}&severity=${sev}&limit=50`)
      setData(res)
    } catch (e: any) {
      setData({ error: e.message || String(e) })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="content-area">
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <TerminalIcon size={18} color="var(--primary)" />
              OpenSearch Log Explorer
            </h3>
            <p className="card-subtitle">Filter and stream service logs directly from the observability pipeline</p>
          </div>
        </div>

        {/* Filter Controls */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
          <input
            className="input"
            placeholder="Service (e.g. frontend, cartservice)"
            value={svc}
            onChange={e => setSvc(e.target.value)}
            style={{ minWidth: 240 }}
          />
          <select className="select" value={sev} onChange={e => setSev(e.target.value)}>
            <option value="">All Severities</option>
            <option value="ERROR">ERROR</option>
            <option value="WARN">WARN</option>
            <option value="INFO">INFO</option>
          </select>
          <button className="btn btn-primary" onClick={search} disabled={loading}>
            <SearchIcon size={14} /> Search Logs
          </button>
        </div>

        {data?.available === false && (
          <div className="alert-banner warning">
            OpenSearch backend is currently unavailable. Ensure the demo observability layer is running.
          </div>
        )}

        {loading && <p style={{ color: 'var(--text-muted)' }}>Querying logs...</p>}

        {Array.isArray(data?.data) && data.data.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon"><TerminalIcon size={24} /></div>
            <span>No log records match the current filter.</span>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {Array.isArray(data?.data) &&
            data.data.map((l: any, i: number) => {
              const severity = (l.payload?.severity || sev || 'INFO').toUpperCase()
              const isError = severity === 'ERROR'
              const isWarn = severity === 'WARN'

              return (
                <div
                  key={i}
                  style={{
                    backgroundColor: 'var(--bg-input)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: '10px 14px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                    <span
                      style={{
                        padding: '1px 6px',
                        borderRadius: 3,
                        fontSize: 10.5,
                        fontWeight: 700,
                        backgroundColor: isError ? 'var(--danger-bg)' : isWarn ? 'var(--warning-bg)' : 'rgba(255,255,255,0.06)',
                        color: isError ? 'var(--danger)' : isWarn ? 'var(--warning)' : 'var(--text-secondary)'
                      }}
                    >
                      {severity}
                    </span>
                    <span className="service-tag">{l.service || 'unknown-service'}</span>
                    <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{l.timestamp}</span>
                  </div>
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', color: '#e2e8f0' }}>
                    {typeof l.payload === 'object' ? JSON.stringify(l.payload) : l.payload}
                  </pre>
                </div>
              )
            })}
        </div>
      </div>
    </div>
  )
}

function Metrics() {
  const [q, setQ] = useState('up')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const run = async () => {
    setLoading(true)
    try {
      const res = await api(`/api/telemetry/prometheus/query?q=${encodeURIComponent(q)}`)
      setData(res)
    } catch (e: any) {
      setData({ error: e.message || String(e) })
    } finally {
      setLoading(false)
    }
  }

  const presets = ['up', 'http_requests_total', 'traces_service_count', 'process_cpu_seconds_total']

  return (
    <div className="content-area">
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <ActivityIcon size={18} color="var(--primary)" />
              Prometheus Metrics Explorer
            </h3>
            <p className="card-subtitle">Query PromQL expressions against the demo metrics storage</p>
          </div>
        </div>

        {/* Query Input */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
          <input
            className="input"
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="PromQL query (e.g. up, rate(...))"
            style={{ flex: 1, fontFamily: 'var(--font-mono)' }}
          />
          <button className="btn btn-primary" onClick={run} disabled={loading}>
            <ActivityIcon size={14} /> Query
          </button>
        </div>

        {/* Quick Presets */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Quick Presets:</span>
          {presets.map(p => (
            <button
              key={p}
              className="btn btn-secondary btn-sm"
              onClick={() => { setQ(p); }}
              style={{ fontFamily: 'var(--font-mono)' }}
            >
              {p}
            </button>
          ))}
        </div>

        {data?.available === false && (
          <div className="alert-banner warning">
            Prometheus backend is currently unavailable. Ensure the demo observability layer is active on port 9090.
          </div>
        )}

        {loading && <p style={{ color: 'var(--text-muted)' }}>Running PromQL query...</p>}

        {Array.isArray(data?.data) && (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Metric / Service</th>
                  <th>Value</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {data.data.slice(0, 30).map((m: any, idx: number) => (
                  <tr key={idx}>
                    <td>
                      <b style={{ color: '#fff' }}>{m.service || 'system'}</b>
                      <pre style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--text-muted)' }}>
                        {JSON.stringify(m.payload?.metric || m.payload || {})}
                      </pre>
                    </td>
                    <td>
                      <span className="badge badge-medium">
                        {String(m.payload?.value?.[1] ?? m.payload?.value ?? '1')}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                      {m.timestamp || 'now'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function Traces() {
  const [svc, setSvc] = useState('')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const run = async () => {
    setLoading(true)
    try {
      const res = await api(`/api/telemetry/traces?service=${svc}&limit=20`)
      setData(res)
    } catch (e: any) {
      setData({ error: e.message || String(e) })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="content-area">
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <LayersIcon size={18} color="var(--primary)" />
              Jaeger Distributed Traces
            </h3>
            <p className="card-subtitle">Analyze distributed transactions and locate latency bottlenecks</p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
          <input
            className="input"
            placeholder="Service filter (e.g. frontend, checkoutservice)"
            value={svc}
            onChange={e => setSvc(e.target.value)}
            style={{ minWidth: 260 }}
          />
          <button className="btn btn-primary" onClick={run} disabled={loading}>
            <LayersIcon size={14} /> Load Traces
          </button>
        </div>

        {data?.available === false && (
          <div className="alert-banner warning">
            Jaeger backend is currently unavailable. Ensure Jaeger is running on port 16686.
          </div>
        )}

        {loading && <p style={{ color: 'var(--text-muted)' }}>Loading traces...</p>}

        {Array.isArray(data?.data) && data.data.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon"><LayersIcon size={24} /></div>
            <span>No traces found for query.</span>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {Array.isArray(data?.data) &&
            data.data.map((t: any, i: number) => {
              const hasError = Boolean(t.payload?.has_error)
              return (
                <div
                  key={i}
                  style={{
                    backgroundColor: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-md)',
                    padding: '12px 16px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span className={`badge ${hasError ? 'badge-critical' : 'badge-inactive'}`}>
                      {hasError ? 'ERROR' : 'OK'}
                    </span>
                    <div>
                      <b style={{ color: '#fff', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
                        {t.payload?.trace_id || `trace-${i}`}
                      </b>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                        Spans: {t.payload?.span_count ?? 'N/A'} · Timestamp: {t.timestamp}
                      </div>
                    </div>
                  </div>
                  <span className="service-tag">{t.service || 'distributed'}</span>
                </div>
              )
            })}
        </div>
      </div>
    </div>
  )
}

function Settings() {
  const m = useFetch('/api/settings/model')
  const t = useFetch('/api/settings/telemetry')
  const h = useFetch('/api/brain/model/health')

  return (
    <div className="content-area">
      <div className="grid-2">
        {/* Model Settings Card */}
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">
                <BrainIcon size={18} color="var(--primary)" />
                LLM Configuration
              </h3>
              <p className="card-subtitle">AI model credentials and runtime parameters</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Provider</span>
              <b style={{ color: '#fff' }}>{m.data?.provider || 'openai'}</b>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Model Name</span>
              <b style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{m.data?.model || 'gpt-4o-mini'}</b>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Base URL</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
                {m.data?.base_url || 'default'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ color: 'var(--text-secondary)' }}>API Key Status</span>
              <span className={`badge ${m.data?.has_api_key ? 'badge-inactive' : 'badge-critical'}`}>
                {m.data?.has_api_key ? 'CONFIGURED' : 'MISSING (.env.model)'}
              </span>
            </div>
          </div>
        </div>

        {/* Model Health Card */}
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">
                <ServerIcon size={18} color="var(--primary)" />
                Model Connectivity
              </h3>
              <p className="card-subtitle">Verification of model credentials</p>
            </div>
            <span className={`status-pill ${h.data?.has_credentials ? 'success' : 'danger'}`}>
              <span className="dot" />
              {h.data?.has_credentials ? 'Ready' : 'Not Configured'}
            </span>
          </div>

          <pre className="code-box">{JSON.stringify(h.data || {}, null, 2)}</pre>
          <p style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 12 }}>
            Credentials are strictly managed on the backend and never exposed to the client.
          </p>
        </div>
      </div>

      {/* Telemetry Endpoints Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3 className="card-title">
              <ActivityIcon size={18} color="var(--primary)" />
              Observability Registry
            </h3>
            <p className="card-subtitle">Direct connections into OpenTelemetry Demo components</p>
          </div>
        </div>

        <pre className="code-box">{JSON.stringify(t.data || {}, null, 2)}</pre>
      </div>
    </div>
  )
}

const PAGES: { id: Page; label: string; icon: React.FC<any> }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: DashboardIcon },
  { id: 'faults', label: 'Faults', icon: ZapIcon },
  { id: 'incidents', label: 'Incidents', icon: AlertTriangleIcon },
  { id: 'approvals', label: 'Approvals', icon: ShieldCheckIcon },
  { id: 'logs', label: 'Logs', icon: TerminalIcon },
  { id: 'metrics', label: 'Metrics', icon: ActivityIcon },
  { id: 'traces', label: 'Traces', icon: LayersIcon },
  { id: 'settings', label: 'Settings', icon: SettingsIcon },
]

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [cycleMsg, setCycleMsg] = useState<string | null>(null)
  const [runningCycle, setRunningCycle] = useState(false)

  const faults = useFetch('/api/faults/status/all', 5000)
  const approvals = useFetch('/api/approvals', 5000)

  const activeFaultsCount = Array.isArray(faults.data)
    ? faults.data.filter((f: any) => f.state === 'active').length
    : 0

  const pendingApprovalsCount = Array.isArray(approvals.data) ? approvals.data.length : 0

  const triggerDetectionCycle = async () => {
    setRunningCycle(true)
    try {
      const res = await api('/api/detection/run', { method: 'POST' })
      setCycleMsg(`Detection completed. Created ${res.created ?? 0} incidents.`)
      setTimeout(() => setCycleMsg(null), 4000)
    } catch (e: any) {
      setCycleMsg(`Detection error: ${e.message || e}`)
      setTimeout(() => setCycleMsg(null), 4000)
    } finally {
      setRunningCycle(false)
    }
  }

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand-icon">
            <EyeIcon size={22} color="#fff" />
          </div>
          <div>
            <div className="brand-title">Eyes</div>
            <div className="brand-subtitle">AI Observability</div>
          </div>
        </div>

        <nav className="nav-list">
          {PAGES.map(p => {
            const Icon = p.icon
            const isActive = page === p.id
            const badgeCount =
              p.id === 'faults' && activeFaultsCount > 0
                ? activeFaultsCount
                : p.id === 'approvals' && pendingApprovalsCount > 0
                ? pendingApprovalsCount
                : null

            return (
              <button
                key={p.id}
                className={`nav-item ${isActive ? 'active' : ''}`}
                onClick={() => setPage(p.id)}
              >
                <span className="icon"><Icon size={18} color={isActive ? '#fff' : 'var(--text-secondary)'} /></span>
                <span className="label">{p.label}</span>
                {badgeCount !== null && <span className="nav-badge">{badgeCount}</span>}
              </button>
            )
          })}
        </nav>

        <div className="sidebar-footer">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="dot pulse" style={{ color: 'var(--success)' }} />
            <span>OpenTelemetry Connected</span>
          </div>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>v0.1.0 · Localhost</span>
        </div>
      </aside>

      {/* Main Area */}
      <div className="main-wrapper">
        <header className="top-header">
          <div className="page-title">
            <h2 style={{ textTransform: 'capitalize', fontSize: 18 }}>{page}</h2>
          </div>

          <div className="header-actions">
            {cycleMsg && (
              <span style={{ fontSize: 12, color: 'var(--primary)', fontWeight: 500 }}>{cycleMsg}</span>
            )}
            <button
              className="btn btn-secondary btn-sm"
              onClick={triggerDetectionCycle}
              disabled={runningCycle}
            >
              <PlayIcon size={12} color="var(--primary)" />
              {runningCycle ? 'Running Cycle...' : 'Run Detection Cycle'}
            </button>
            <div className={`status-pill ${activeFaultsCount > 0 ? 'danger' : 'success'}`}>
              <span className="dot pulse" />
              <span>{activeFaultsCount > 0 ? `${activeFaultsCount} Active Faults` : 'System Baseline'}</span>
            </div>
          </div>
        </header>

        <main>
          {page === 'dashboard' && <Dashboard onNavigate={setPage} />}
          {page === 'faults' && <Faults />}
          {page === 'incidents' && <Incidents />}
          {page === 'approvals' && <Approvals />}
          {page === 'logs' && <Logs />}
          {page === 'metrics' && <Metrics />}
          {page === 'traces' && <Traces />}
          {page === 'settings' && <Settings />}
        </main>
      </div>
    </div>
  )
}
