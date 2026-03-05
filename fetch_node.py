"""
Call Blacklight node endpoint and pretty-print the result.

Usage:
  python fetch_node.py [node_address]
  (default node: 0x789f9ba768aee89ebac8daf61aa8a4afdff15908)
"""
import json
import re
import sys

import requests

BASE_URL = "https://blacklight.nillion.com"
DEFAULT_NODE = "0x789f9ba768aee89ebac8daf61aa8a4afdff15908"

# next-action for payload [address] only (get block number)
NEXT_ACTION_BLOCK = "402588467ad177655767e5f4b7b366339cb7ca6482"
# next-action for payload [address, round_id, limit] (get heartbeat list)
NEXT_ACTION_HEARTBEATS = "705f39a1dea9f55e5ff7c9d6e19fb9655374a022e3"


def _headers(next_action: str) -> dict[str, str]:
    """Minimal headers required for Blacklight RSC endpoint (content-type, accept, next-action)."""
    return {
        "content-type": "text/plain;charset=UTF-8",
        "accept": "text/x-component",
        "next-action": next_action,
    }


def fetch_node_block_number(node_address: str) -> int | None:
    """POST with payload [address] only; parse response and return block number for this node."""
    url = f"{BASE_URL}/nodes/{node_address}"
    payload = [node_address]
    resp = requests.post(url, data=json.dumps(payload), headers=_headers(NEXT_ACTION_BLOCK), timeout=15)
    resp.raise_for_status()
    return _parse_block_number_from_rsc(resp.text)


def _parse_block_number_from_rsc(text: str) -> int | None:
    """Extract block number from RSC response (e.g. array [address, blockNum, limit] or object with block/round)."""
    for line in text.split("\n"):
        if not line.strip():
            continue
        m = re.match(r"^\d+:(.+)$", line)
        if not m:
            continue
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, list) and len(obj) >= 2:
                # e.g. [address, blockNum, limit]
                candidate = obj[1]
                if isinstance(candidate, (int, float)) and 0 < candidate < 1e10:
                    return int(candidate)
            if isinstance(obj, dict):
                for key in ("block", "blockNumber", "block_num", "round", "roundId"):
                    if key in obj and obj[key] is not None:
                        v = obj[key]
                        if isinstance(v, (int, float)) and 0 < v < 1e10:
                            return int(v)
                # With minimal headers, payload [address] returns {"data": [{..., "block_num": N}]}
                if "data" in obj and isinstance(obj["data"], list) and len(obj["data"]) > 0:
                    first = obj["data"][0]
                    if isinstance(first, dict) and "block_num" in first:
                        v = first["block_num"]
                        if isinstance(v, (int, float)) and 0 < v < 1e10:
                            return int(v)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def fetch_node(node_address: str, round_id: int, limit: int = 50):
    url = f"{BASE_URL}/nodes/{node_address}"
    payload = [node_address, round_id, limit]
    resp = requests.post(url, data=json.dumps(payload), headers=_headers(NEXT_ACTION_HEARTBEATS), timeout=15)
    resp.raise_for_status()
    return resp.text


def parse_rsc_response(text: str) -> list | dict | None:
    """Extract JSON data from Next.js RSC stream (lines like '1:{"data":[...]}')."""
    found = None
    for line in text.split("\n"):
        if not line.strip():
            continue
        m = re.match(r"^\d+:(.+)$", line)
        if m:
            try:
                obj = json.loads(m.group(1))
                if "data" in obj and isinstance(obj.get("data"), list):
                    return obj["data"]
                if found is None:
                    found = obj
            except json.JSONDecodeError:
                continue
    return found


def main() -> None:
    node = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NODE
    print(f"Fetching node: {node}\n")
    block = fetch_node_block_number(node)
    if block is None:
        print("Could not get block number for node; cannot fetch heartbeats.")
        return
    print(f"Block number: {block}\n")
    text = fetch_node(node, block, 50)
    data = parse_rsc_response(text)
    if data is not None:
        print(json.dumps(data, indent=2))
    else:
        print("Could not parse data from response. Raw (first 1500 chars):")
        print(text[:1500])


if __name__ == "__main__":
    main()
