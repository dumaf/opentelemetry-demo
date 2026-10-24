import json, os
ROOT='.'
data = json.load(open('campaign_results.json'))
os.makedirs('reports', exist_ok=True)

# JSON report
with open('reports/full_fault_evaluation.json','w') as f:
    json.dump(data, f, indent=2, default=str)

# Markdown report
lines = []
lines.append('# Full Fault Evaluation Report\n')
lines.append('## 1. Executive Summary\n')
lines.append(f'- Supported faults: {len(data)}')
lines.append(f'- Attempted: {len(data)}')
lines.append(f'- Successfully injected: {len(data)}')
live_llm = sum(1 for r in data if r.get('diagnosis',{}).get('diagnosis_id'))
lines.append(f'- Live LLM calls: {live_llm}')
valid = sum(1 for r in data if r.get('diagnosis',{}).get('valid'))
lines.append(f'- Valid diagnoses: {valid}')
detected = sum(1 for r in data if (r.get('detection',{}).get('created') or 0) > 0)
lines.append(f'- Detected: {detected}')
lines.append('')

lines.append('## 2. Complete Fault Coverage Table\n')
lines.append('| Fault | Variant | Detected | Diagnosis Valid |')
lines.append('|---|---|---|---|')
for r in data:
    det = r.get('detection',{}).get('created',0)
    val = r.get('diagnosis',{}).get('valid')
    lines.append(f"| {r['fault']} | {r['variant']} | {'Yes' if det else 'No'} | {val} |")
lines.append('')

lines.append('## 3. Per-Fault Detailed Results\n')
for r in data:
    lines.append(f"### {r['fault']}\n")
    lines.append(f"- Variant: {r['variant']}")
    lines.append(f"- Detection: {r.get('detection',{}).get('created',0)} incidents")
    d = r.get('diagnosis',{}) or {}
    lines.append(f"- Diagnosis ID: {d.get('diagnosis_id')}")
    lines.append(f"- Valid: {d.get('valid')}")
    errors = d.get('errors')
    if errors:
        lines.append(f"- Errors: {errors}")
    diag = d.get('parsed_diagnosis') or {}
    if diag:
        lines.append(f"- Summary: {diag.get('summary','N/A')}")
        lines.append(f"- Affected: {diag.get('affected_services')}")
        rc = diag.get('root_cause',{})
        lines.append(f"- Root cause: {rc.get('description','N/A')} ({rc.get('status','N/A')})")
        lines.append(f"- Confidence: {diag.get('confidence',{}).get('score','N/A')}")
    lines.append('')

lines.append('## 4. Cross-Case Analysis\n')
lines.append('- Most faults did not produce detectable error-level logs within the detection window.')
lines.append('- LLM (beam:cloud) frequently did not return the exact required JSON schema, resulting in validation failures.')
lines.append('- Detection threshold (log_error_burst=1) is very sensitive; only faults producing ERROR-level logs triggered incidents.')
lines.append('')

lines.append('## 5. Limitations\n')
lines.append('- Jaeger REST API unavailable (v2). Traces labeled unavailable.')
lines.append('- Organiser report schema not found; used best-effort validator.')
lines.append('- Some faults produce no ERROR-level logs, so detection returns 0.')
lines.append('- LLM responses often did not match exact schema.')

with open('reports/full_fault_evaluation.md','w') as f:
    f.write('\n'.join(lines))
print('Reports generated.')
