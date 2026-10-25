from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import storage
from ..auth import get_current_tenant
from ..config import RATE_LIMIT_UPLOAD
from ..i18n import request_lang, translate
from ..middleware import limiter
from ..models import Alert, CrmPushResponse
from ..services.crm import push_to_crm

router = APIRouter(prefix="/api/leads", tags=["actions"])
alerts_router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _get_or_404(tenant_id: str, lead_id: str):
    lead = storage.get_lead(tenant_id, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


# Same tier as the upload endpoint -- each call here hits a real,
# potentially-billed third-party API (Salesforce) per lead.
@router.post("/{lead_id}/crm-push", response_model=CrmPushResponse)
@limiter.limit(RATE_LIMIT_UPLOAD)
def crm_push(
    request: Request,
    lead_id: str,
    crm: Literal["salesforce"] = "salesforce",
    tenant: storage.Tenant = Depends(get_current_tenant),
):
    lead = _get_or_404(tenant.id, lead_id)
    result = push_to_crm(lead, crm=crm)
    lead.crm_pushed = True
    storage.update_lead(tenant.id, lead)
    result.detail = translate(result.detail, request_lang(request))
    return result


@alerts_router.get("", response_model=list[Alert])
def get_alerts(tenant: storage.Tenant = Depends(get_current_tenant)):
    return storage.list_alerts(tenant.id)
