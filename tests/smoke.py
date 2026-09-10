"""Minimal APG API smoke-test helper. Run with the server on localhost."""
import urllib.request, json
base='http://127.0.0.1:8000'
for path in ['/api/health','/manifest.webmanifest']:
    with urllib.request.urlopen(base+path,timeout=5) as r:
        assert r.status==200
        print(path, r.status, json.loads(r.read()))
