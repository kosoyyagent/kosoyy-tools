#!/usr/bin/env python3
"""txlegs.py — dump the ERC-20 Transfer legs of a transaction receipt.

Answers the question an index page cannot: what actually moved, from where,
to where, in one tx. Distinguishes a swap (WBNB into pool + token out) from
an LP withdrawal (both tokens out of the pool) and reveals contracts that
forward funds to a different final holder.

Stdlib only. Usage:

  python txlegs.py --tx 0xHASH [--rpc URL] [--token 0xADDR]
  python txlegs.py --tx 0xHASH --tx 0xHASH2 ... --rpc https://bsc.publicnode.com

Default RPC: https://bsc-dataseed.binance.org (BSC). Use --rpc for any chain.
Output: one JSON line per Transfer leg, then a summary line.
Exit 0 on success, 1 if a receipt is missing, 2 on usage errors.
"""
import argparse
import json
import sys
import urllib.request

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DEFAULT_RPC = "https://bsc-dataseed.binance.org"
# well-known decimals; everything else falls back to --decimals
KNOWN = {
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": 18,  # WBNB
    "0x55d398326f99059ff775485246999027b3197955": 18,  # USDT BSC
    "0xe9e7cea3dedca5984780bafc599bd69add087d56": 18,  # BUSD
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": 18,  # USDC BSC
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": 6,   # USDC Base
}


def rpc_call(url, method, params):
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "txlegs/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read().decode())
    if "error" in out:
        raise RuntimeError(str(out["error"])[:200])
    return out.get("result")


def decimals_of(rpc, token):
    if token in KNOWN:
        return KNOWN[token]
    try:
        res = rpc_call(rpc, "eth_call", [{"to": token, "data": "0x313ce567"}, "latest"])
        return int(res, 16)
    except Exception:
        return 18


def legs(rpc, tx_hash, token_filter, default_decimals):
    rec = rpc_call(rpc, "eth_getTransactionReceipt", [tx_hash])
    if rec is None:
        return None
    out = []
    for lg in rec.get("logs", []):
        topics = lg.get("topics") or []
        if len(topics) != 3 or topics[0] != TRANSFER_TOPIC:
            continue
        token = lg["address"].lower()
        if token_filter and token != token_filter.lower():
            continue
        raw = int(lg["data"], 16)
        dec = decimals_of(rpc, token) if default_decimals is None else default_decimals
        out.append({
            "token": token,
            "from": "0x" + topics[1][-40:],
            "to": "0x" + topics[2][-40:],
            "raw": str(raw),
            "amount": raw / (10 ** dec) if raw < 10 ** 40 else "huge",
            "decimals": dec,
        })
    return {"tx": tx_hash, "status": rec["status"],
            "block": int(rec["blockNumber"], 16), "legs": out}


def main():
    ap = argparse.ArgumentParser(description="Dump ERC-20 Transfer legs of tx receipts.")
    ap.add_argument("--tx", action="append", required=True, help="tx hash (repeatable)")
    ap.add_argument("--rpc", default=DEFAULT_RPC)
    ap.add_argument("--token", help="only legs of this token contract")
    ap.add_argument("--decimals", type=int, default=None,
                    help="override decimals for all tokens")
    args = ap.parse_args()
    rc = 0
    for tx in args.tx:
        try:
            res = legs(args.rpc, tx, args.token, args.decimals)
        except Exception as e:
            print(json.dumps({"tx": tx, "error": str(e)[:200]}))
            rc = 1
            continue
        if res is None:
            print(json.dumps({"tx": tx, "error": "no receipt (pending or wrong chain)"}))
            rc = 1
            continue
        for leg in res["legs"]:
            print(json.dumps({"tx": tx, "block": res["block"], "status": res["status"], **leg}))
        print(json.dumps({"tx": tx, "block": res["block"], "status": res["status"],
                          "legs": len(res["legs"]), "summary": True}))
    return rc


if __name__ == "__main__":
    sys.exit(main())
