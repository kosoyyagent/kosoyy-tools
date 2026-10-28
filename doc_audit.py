#!/usr/bin/env python3
"""doc_audit.py — check API docs against live behavior.

Reads an OpenAPI/Swagger JSON spec and probes each documented GET endpoint
with no required parameters. Reports which documented routes are dead (404),
which fail (5xx), and which respond. The exact gap an "API audit" client pays
to find — docs promising endpoints the server doesn't serve.

Usage:
  python doc_audit.py --spec https://example.com/openapi.json
  python doc_audit.py --spec spec.json --base https://api.example.com --timeout 8

Output: one line per route — STATUS path — plus a summary.
Exit 0 always; the audit result is the report, not the exit code.
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def load_spec(source):
    if source.startswith("http"):
        req = urllib.request.Request(source, headers={"User-Agent": "doc-audit/1.0"})
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    return json.load(open(source, encoding="utf-8"))


def probe(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "doc-audit/1.0"})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        r.read(4096)
        return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, str(e)[:60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--base", help="override server base url")
    ap.add_argument("--timeout", type=int, default=10)
    ap.add_argument("--delay", type=float, default=0.3)
    args = ap.parse_args()

    spec = load_spec(args.spec)
    servers = spec.get("servers") or []
    base = args.base or (servers[0]["url"] if servers else "")
    if not base:
        sys.exit("no server base; pass --base")

    paths = spec.get("paths", {})
    results = {"ok": [], "dead": [], "error": [], "skip": []}
    for path, methods in paths.items():
        get = (methods or {}).get("get")
        if not get:
            continue
        params = [p for p in (get.get("parameters") or []) if p.get("required")]
        if params:
            results["skip"].append(path + " (required params)")
            continue
        url = base.rstrip("/") + path
        code, err = probe(url, args.timeout)
        if code and 200 <= code < 400:
            results["ok"].append(f"{code} {path}")
        elif code == 404:
            results["dead"].append(path)
        elif code:
            results["error"].append(f"{code} {path}")
        else:
            results["error"].append(f"ERR {path} {err}")
        import time
        time.sleep(args.delay)

    print("== LIVE (documented GET, responds) ==")
    for x in results["ok"]:
        print(" ", x)
    print("== DEAD (documented but 404) ==")
    for x in results["dead"]:
        print(" ", x)
    print("== ERRORS ==")
    for x in results["error"]:
        print(" ", x)
    print("== SKIPPED (required params) ==")
    for x in results["skip"]:
        print(" ", x)
    n = len(paths)
    print(f"SUMMARY: {len(results['ok'])} live / {len(results['dead'])} dead / "
          f"{len(results['error'])} error / {len(results['skip'])} skipped of {n} documented")


if __name__ == "__main__":
    main()
