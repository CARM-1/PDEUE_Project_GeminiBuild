from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, List
from app.domain.accounting_gateway import AccountingGateway

router = APIRouter(prefix='/api/v1/accounting', tags=['Independent Accounting'])
global_accounting_gateway = AccountingGateway()

class AckPayload(BaseModel):
    ack_id: str
    sequence_id: int
    system_id: str
    received_hash: str

@router.get('/events')
def fetch_accounting_outbox(
    since_seq: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200)
):
    events = global_accounting_gateway.get_outbox_events(since_seq=since_seq, limit=limit)
    return {
        'total_count': len(events),
        'since_seq': since_seq,
        'events': events
    }

@router.post('/reconciliation-ack')
def submit_reconciliation_ack(payload: AckPayload):
    res = global_accounting_gateway.acknowledge_receipt(
        ack_id=payload.ack_id,
        sequence_id=payload.sequence_id,
        system_id=payload.system_id,
        received_hash=payload.received_hash
    )
    if res.get('status') == 'REJECTED':
        raise HTTPException(status_code=400, detail=res.get('reason'))
    return res
