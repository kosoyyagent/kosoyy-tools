#!/usr/bin/env python3
"""paycheck.py — verify an on-chain payment claim.

Given a transaction hash, checks (all from a public RPC, nothing trusted):
  - receipt exists and status == success
  - an ERC-20 Transfer log moved the claimed token
  - funds went to the claimed recipient, amount matches claimed value

Usage:
  paycheck.py --tx 0xHASH --token usdc-base --to 0xRECIPIENT --amount 5.00
  paycheck.py --tx 0xHASH --token 0x90c8889f... --to 0xRECIPIENT --amount 150000 --decimals 18 --rpc https://bsc.publicnode.com

Exit code 0 = VERIFIED, 1 = mismatch/not found, 2 = usage/rpc error.
"""
import argparse
import json
import sys
import urllib.request

TOKENS = {
    "usdc-base": ("https://mainnet.base.org", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 6),
    "usdc-bsc": ("https://bsc.publicnode.com", "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", 18),
}
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def rpc_call(url, method, params):
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "paycheck/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(out["error"])
    return out.get("result")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tx", required=True)
    ap.add_argument("--token", required=True, help="symbol alias or 0x contract address")
    ap.add_argument("--to", required=True)
    ap.add_argument("--amount", required=True, type=float)
    ap.add_argument("--decimals", type=int, help="override token decimals")
    ap.add_argument("--rpc", help="override RPC url")
    ap.add_argument("--tolerance", type=float, default=0.000001)
    args = ap.parse_args()

    if args.token in TOKENS:
        url, token, dec = TOKENS[args.token]
    elif args.token.startswith("0x"):
        if not args.decimals:
            sys.exit("decimals required for custom token address")
        url, token, dec = None, args.token, args.decimals
    else:
        sys.exit("unknown token alias; pass a 0x contract address")
    url = args.rpc or url
    if not url:
        sys.exit("no RPC for this token; pass --rpc")
    dec = args.decimals or dec

    try:
        rc = rpc_call(url, "eth_getTransactionReceipt", [args.tx])
    except Exception as e:
        print(f"RPC error: {e}")
        sys.exit(2)
    if not rc:
        print("NOT FOUND: no such tx on this network")
        sys.exit(1)
    if rc["status"] != "0x1":
        print("FAILED TX: receipt status != success")
        sys.exit(1)

    want_to = args.to.lower()
    want_amt = args.amount
    seen = []
    for lg in rc.get("logs", []):
        if lg["address"].lower() != token.lower():
            continue
        if not lg.get("topics") or lg["topics"][0].lower() != TRANSFER_TOPIC:
            continue
        frm = "0x" + lg["topics"][1][-40:]
        to = "0x" + lg["topics"][2][-40:]
        amt = int(lg["data"], 16) / 10**dec
        seen.append((frm, to, amt))

    block = int(rc["blockNumber"], 16)
    if not seen:
        print(f"NO TRANSFER: tx exists (block {block}) but moves no {token}")
        sys.exit(1)
    for frm, to, amt in seen:
        if to.lower() == want_to and abs(amt - want_amt) <= args.tolerance:
            print(f"VERIFIED: {amt} tokens -> {to} in block {block} (from {frm})")
            sys.exit(0)
    print("MISMATCH: transfers found but none matches claimed recipient+amount:")
    for frm, to, amt in seen:
        print(f"  {amt} -> {to} (from {frm})")
    sys.exit(1)


if __name__ == "__main__":
    main()
