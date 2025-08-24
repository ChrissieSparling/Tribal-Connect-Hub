from fastapi import APIRouter
from typing import Dict
import hashlib, time

router = APIRouter(prefix="/audit", tags=["audit"])

AUDIT_LOG: Dict[int, dict] = {}
AUDIT_SEQ = 0

def _hash_entry(prev_hash: str, entry: dict) -> str:
    raw = (prev_hash or "") + str(entry) + str(time.time())
    return hashlib.sha256(raw.encode()).hexdigest()

def append_audit(entry: dict):
    global AUDIT_SEQ
    prev_hash = AUDIT_LOG.get(AUDIT_SEQ - 1, {}).get("hash", "")
    h = _hash_entry(prev_hash, entry)
    AUDIT_LOG[AUDIT_SEQ] = {**entry, "hash": h, "prev_hash": prev_hash}
    AUDIT_SEQ += 1
    return h

@router.get("")
def audit_log():
    return {"entries": list(AUDIT_LOG.values())}
