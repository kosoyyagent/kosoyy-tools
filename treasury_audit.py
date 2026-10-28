#!/usr/bin/env python3
"""treasury_audit.py — list ERC-20 outflows from a wallet over a UTC date window.

Rebuilds what an auditor reports for "all transfers out of treasury X on date D":
every Transfer log from <wallet> for <token>, with tx hash, block, UTC timestamp,
recipient, and amount. Pure public RPC, no API keys, nothing trusted.

Usage:
  python treasury_audit.py --rpc https://bsc.publicnode.com \
      --token 0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df \
      --wallet 0x7C34E9e21eE28A49Ff0b84B61774119E6633359f \
      --date 2026-10-27 --decimals 18 --tz-offset -5

Outputs JSON lines to stdout (one per transfer) plus a summary line.
"""
import argparse
import datetime
import json
import sys
import urllib.request

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def rpc(url, method, params):
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "treasury-audit/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(out["error"])
    return out.get("result")


def find_block_by_ts(url, target_ts):
    """Binary-search the block whose timestamp is closest to target_ts."""
    lo, hi = 1, int(rpc(url, "eth_blockNumber", []), 16)
    while lo < hi:
        mid = (lo + hi) // 2
        b = rpc(url, "eth_getBlockByNumber", [hex(mid), False])
        if int(b["timestamp"], 16) < target_ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--wallet", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--decimals", type=int, default=18)
    ap.add_argument("--tz-offset", type=int, default=0, help="hours from UTC for 'the day'")
    ap.add_argument("--chunk", type=int, default=5000, help="log query block span")
    ap.add_argument("--start-block", type=int, help="skip binary search")
    ap.add_argument("--end-block", type=int)
    args = ap.parse_args()

    day = datetime.date.fromisoformat(args.date)
    tz = datetime.timezone(datetime.timedelta(hours=args.tz_offset))
    start_ts = int(datetime.datetime.combine(day, datetime.time(0, 0), tz).timestamp())
    end_ts = start_ts + 86400

    b0 = args.start_block or find_block_by_ts(args.rpc, start_ts)
    b1 = args.end_block or find_block_by_ts(args.rpc, end_ts) - 1
    total = 0.0
    n = 0
    wallet_topic = "0x" + args.wallet.lower().replace("0x", "").rjust(64, "0")

    b = b0
    while b <= b1:
        span = min(args.chunk, b1 - b + 1)
        flt = {
            "fromBlock": hex(b),
            "toBlock": hex(b + span - 1),
            "address": args.token,
            "topics": [TRANSFER_TOPIC, wallet_topic],
        }
        try:
            logs = rpc(args.rpc, "eth_getLogs", [flt]) or []
        except RuntimeError:
            span = max(1, span // 10)
            logs = rpc(args.rpc, "eth_getLogs", [{**flt, "toBlock": hex(b + span - 1)}]) or []
        for lg in logs:
            to = "0x" + lg["topics"][2][-40:]
            amt = int(lg["data"], 16) / 10**args.decimals
            blk = int(lg["blockNumber"], 16)
            hdr = rpc(args.rpc, "eth_getBlockByNumber", [hex(blk), False])
            ts = int(hdr["timestamp"], 16)
            iso = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()
            print(json.dumps({"tx": lg["transactionHash"], "block": blk,
                              "utc": iso, "to": to, "amount": amt}))
            total += amt
            n += 1
        b += span

    print(json.dumps({"summary": {"transfers": n, "total": total,
                                  "window": [start_ts, end_ts],
                                  "blocks": [b0, b1]}}))


if __name__ == "__main__":
    main()
