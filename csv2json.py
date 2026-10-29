#!/usr/bin/env python3
"""csv2json — parse CSV files and emit clean JSON.

Handles: comma/semicolon/tab/pipe delimiters (auto-detected or forced),
quoted fields with embedded delimiters/newlines, BOM, custom encoding,
type inference (int/float/bool/null), headerless files, streaming for
large inputs.

Usage:
    python csv2json.py input.csv [-o out.json] [--delimiter ,]
        [--no-infer] [--no-header] [--encoding utf-8] [--ndjson]
    python csv2json.py input.json --to-csv [-o out.csv] [--delimiter ,]
"""
import argparse, csv, json, sys, io

def sniff_dialect(sample, forced=None):
    if forced:
        d = csv.excel()
        d.delimiter = forced
        return d
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel()

def infer(v):
    v = v.strip()
    if v == "": return None
    low = v.lower()
    if low in ("true", "false"): return low == "true"
    if low in ("null", "none", "n/a", "na"): return None
    # leading-zero values ("001", "007.5") are identifiers, not numbers — keep them verbatim
    if len(v) > 1 and v[0] == "0" and v[1].isdigit() or (v[0] in "+-" and len(v) > 2 and v[1] == "0" and v[2].isdigit()):
        return v
    try: return int(v)
    except ValueError: pass
    try: return float(v)
    except ValueError: pass
    return v

def read_csv(path, encoding, dialect):
    with io.open(path, "r", encoding=encoding, errors="replace", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        yield from csv.reader(f, sniff_dialect(sample, dialect))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--delimiter")
    p.add_argument("--no-infer", action="store_true")
    p.add_argument("--no-header", action="store_true")
    p.add_argument("--encoding", default="utf-8-sig")
    p.add_argument("--ndjson", action="store_true")
    p.add_argument("--to-csv", action="store_true", help="convert JSON array of objects to CSV")
    a = p.parse_args()

    if a.to_csv:
        write_csv(a)
        return

    rows = read_csv(a.input, a.encoding, a.delimiter)
    rows = list(rows) if not a.no_header else iter(rows)
    if a.no_header:
        header = None
        data_rows = rows
    else:
        if not rows:
            print("empty input", file=sys.stderr); sys.exit(1)
        header = [h.strip() or f"col{i}" for i, h in enumerate(rows[0])]
        data_rows = rows[1:]

    conv = (lambda v: v) if a.no_infer else infer
    out = sys.stdout if not a.output else io.open(a.output, "w", encoding="utf-8")

    def emit(obj):
        out.write(json.dumps(obj, ensure_ascii=False) + "\n")

    if a.ndjson:
        for r in data_rows:
            vals = [conv(v) for v in r]
            emit(dict(zip(header, vals)) if header else vals)
    else:
        objs = []
        for r in data_rows:
            vals = [conv(v) for v in r]
            objs.append(dict(zip(header, vals)) if header else vals)
        json.dump(objs, out, ensure_ascii=False, indent=2)
        out.write("\n")
    if a.output: out.close()

def write_csv(a):
    with io.open(a.input, "r", encoding=a.encoding, errors="replace") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        print("--to-csv expects a JSON array of objects", file=sys.stderr)
        sys.exit(1)
    header = []
    for r in data:
        for k in r:
            if k not in header:
                header.append(k)
    out = sys.stdout if not a.output else io.open(a.output, "w", encoding="utf-8", newline="")
    w = csv.writer(out, delimiter=a.delimiter or ",")
    w.writerow(header)
    for r in data:
        w.writerow([json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list))
                    else ("" if v is None else v) for v in (r.get(k) for k in header)])
    if a.output:
        out.close()

if __name__ == "__main__":
    main()
