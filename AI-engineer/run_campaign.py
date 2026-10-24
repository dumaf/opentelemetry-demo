import os, sys, json, time, urllib.request
os.environ['FLAGD_UI_BASE_URL']='http://localhost:32918'
os.environ['PROMETHEUS_BASE_URL']='http://localhost:9090'
os.environ['JAEGER_BASE_URL']='http://localhost:32911'
os.environ['OPENSEARCH_BASE_URL']='http://localhost:32905'
ROOT='.'
if ROOT not in sys.path: sys.path.insert(0, ROOT)

from eyes_core.inventory import build_inventory
from eyes_core.flagd_client import FlagdClient
from faultcli.state import capture_baselines, get_baseline, record_control_event
import urllib.request

API='http://127.0.0.1:8090'
def api(path, method='GET', data=None):
    url=API+path
    req=urllib.request.Request(url, data=json.dumps(data).encode() if data else None, method=method, headers={'Content-Type':'application/json'})
    try:
        r=urllib.request.urlopen(req, timeout=120)
        return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'detail': e.read().decode()[:500]}
    except Exception as e:
        return {'error': str(e)}

capture_baselines()
inv = build_inventory()
# pick non-off variant for each fault
results = []
for f in inv:
    key = f['flag_key']
    if key == 'emitRawPii':
        continue
    variants = [v for v in f['available_variants'] if v != 'off']
    if not variants:
        continue
    variant = variants[0]
    print(f'\n=== {key} -> {variant} ===', flush=True)
    # trigger
    tr = api(f'/api/faults/{key}/trigger', 'POST', {'variant': variant})
    approval_id = tr.get('approval',{}).get('id')
    print('trigger proposal:', approval_id)
    # approve + execute
    if approval_id:
        api(f'/api/approvals/{approval_id}/approve', 'POST', {'actor':'human'})
        ex = api(f'/api/approvals/{approval_id}/execute', 'POST', {'actor':'human'})
        print('executed:', ex.get('status'))
    # wait for traffic
    time.sleep(45)
    # detect
    det = api('/api/detection/run', 'POST', {})
    print('detected:', det.get('created'))
    # find incidents for this service
    incs = api('/api/incidents')
    # pick most recent incident
    new_inc = None
    if isinstance(incs, list) and incs:
        new_inc = incs[0]
    result = {
        'fault': key,
        'variant': variant,
        'trigger': tr,
        'detection': det,
        'incident_id': new_inc['id'] if new_inc else None,
        'diagnosis': None,
        'raw_llm': None,
    }
    if new_inc:
        # run brain
        br = api(f'/api/brain/incidents/{new_inc["id"]}/diagnose', 'POST', {'detection_mode':'controlled'})
        result['diagnosis'] = br
        # get diagnosis detail
        did = br.get('diagnosis_id')
        if did:
            detail = api(f'/api/brain/diagnoses/{did}')
            result['raw_llm'] = detail.get('payload',{}).get('raw') if isinstance(detail.get('payload'),dict) else None
            result['parsed_diagnosis'] = detail.get('payload')
    # reset
    # find approval for reset
    rst = api(f'/api/faults/{key}/reset', 'POST')
    approval_id2 = rst.get('approval',{}).get('id')
    if approval_id2:
        api(f'/api/approvals/{approval_id2}/approve', 'POST', {'actor':'human'})
        api(f'/api/approvals/{approval_id2}/execute', 'POST', {'actor':'human'})
    results.append(result)
    # save incremental
    with open('campaign_results.json','w') as f:
        json.dump(results, f, indent=2, default=str)
    time.sleep(5)

# final save
with open('campaign_results.json','w') as f:
    json.dump(results, f, indent=2, default=str)
print('\nCampaign complete. Results in campaign_results.json')
