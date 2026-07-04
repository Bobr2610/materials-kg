import json, urllib.request, time, sys

job_id = sys.argv[1] if len(sys.argv) > 1 else "d304d22f0c254299b2b96f73b4c309a6"
base = "http://127.0.0.1:8090/demo/load-task-materials/jobs/"
start = time.time()

for i in range(300):
    try:
        resp = urllib.request.urlopen(base + job_id, timeout=30)
        job = json.loads(resp.read().decode())
        status = job.get("status")
        elapsed = time.time() - start
        if status not in ("queued", "running"):
            result = job.get("result") or {}
            ov = result.get("overview", {})
            print(f"\n=== COMPLETED in {elapsed:.0f}s ({elapsed/60:.1f} min) ===")
            print(f"entities={ov.get('total_entities',0)} relations={ov.get('total_relations',0)} obs={ov.get('total_observations',0)} evidence={ov.get('total_evidence',0)}")
            by_kind = ov.get("by_kind", {})
            for k, v in sorted(by_kind.items(), key=lambda x: -x[1]):
                print(f"  {k}: {v}")
            break
        if i % 6 == 0:
            print(f"[{elapsed:.0f}s] status={status} stage={job.get('stage','')} files={job.get('processed_files',0)}/{job.get('total_files',0)}")
    except Exception as e:
        print(f"[{time.time()-start:.0f}s] ERROR: {e}")
    time.sleep(5)
else:
    print(f"TIMEOUT after {time.time()-start:.0f}s")
