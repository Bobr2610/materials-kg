import json, urllib.request, time, sys

job_id = sys.argv[1] if len(sys.argv) > 1 else "bad2b4aabaf64b2c8d1b754920e3c33b"
base = "http://127.0.0.1:8090/demo/load-task-materials/jobs/"

for i in range(240):
    try:
        resp = urllib.request.urlopen(base + job_id, timeout=30)
        job = json.loads(resp.read().decode())
        status = job.get("status")
        stage = job.get("stage")
        total = job.get("total_files", 0)
        done = job.get("processed_files", 0)
        uploaded = len(job.get("uploaded", []))
        msg = job.get("message", "")
        print(f"[{i*5}s] status={status} stage={stage} files={done}/{total} uploaded={uploaded} msg={msg}")
        if status not in ("queued", "running"):
            print()
            print("=== FINAL RESULT ===")
            result = job.get("result") or {}
            di = result.get("documents_ingested", 0)
            upl = len(result.get("uploaded", []))
            skip = len(result.get("skipped_example_files", []))
            unsup = len(result.get("unsupported_files", []))
            ov = result.get("overview", {})
            ent = ov.get("total_entities", 0)
            rel = ov.get("total_relations", 0)
            obs = ov.get("total_observations", 0)
            evi = ov.get("total_evidence", 0)
            print(f"Status: {status}")
            print(f"Documents ingested: {di}")
            print(f"Uploaded files: {upl}")
            print(f"Skipped examples: {skip}")
            print(f"Unsupported: {unsup}")
            print(f"Graph entities: {ent}")
            print(f"Graph relations: {rel}")
            print(f"Graph observations: {obs}")
            print(f"Graph evidence: {evi}")
            if job.get("error"):
                print(f"Error: {job['error']}")
            break
    except Exception as e:
        print(f"[{i*5}s] ERROR: {e}")
    time.sleep(5)
else:
    print("TIMEOUT: Job did not complete in 20 minutes")
