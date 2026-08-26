"""Read-only S/4HANA OData lookups via the "S43" BTP destination.

Exposed to the LLM as OpenAI-style tools (see TOOL_SCHEMAS / execute_tool),
called from ahf_agent.ai_core's tool-calling loop.

Per the project's security requirements, this module only ever issues GET
requests - it must never write back to S/4HANA (create, approve, reject,
block, unblock, or pay anything).

The $select field lists and OData service/entity paths below are standard
SAP S/4HANA Cloud public API definitions, not specific to this deployment -
spot-check them against this subaccount's actual system $metadata, since
field availability can vary by S/4HANA release/configuration.
"""

from __future__ import annotations

import httpx

from ahf_agent.destinations import DestinationError, resolve_destination
from ahf_agent.logging_config import get_logger

logger = get_logger(__name__)

_SERVICES = {
    "supplier_invoice": "/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV",
    "accounting_doc_item": "/sap/opu/odata/sap/API_OPLACCTGDOCITEMCUBE_SRV",
    "purchase_order": "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV",
    "purchase_requisition": "/sap/opu/odata/sap/API_PURCHASEREQ_PROCESS_SRV",
    "business_partner": "/sap/opu/odata/sap/API_BUSINESS_PARTNER",
}

_INVOICE_FIELDS = (
    "SupplierInvoice,FiscalYear,CompanyCode,DocumentDate,PostingDate,"
    "InvoicingParty,DocumentCurrency,InvoiceGrossAmount,SupplierInvoiceStatus,"
    "PaymentBlockingReason,IsReversal,PaymentMethod,PaymentReference"
    # Confirmed against this subaccount's actual A_SupplierInvoiceType
    # $metadata (2026-08-26): "IsInvoiceReversal" doesn't exist here (the
    # real field is "IsReversal"), and "AccountingDocument" isn't a direct
    # property on this entity at all (it's reached via a navigation
    # property this API doesn't expose in $select).
)
_CLEARING_FIELDS = (
    "AccountingDocument,FiscalYear,CompanyCode,ClearingDocument,ClearingDate,"
    "AmountInCompanyCodeCurrency,CompanyCodeCurrency"
)
_PO_FIELDS = "PurchaseOrder,CompanyCode,Supplier,PurchaseOrderType,PurchasingDocumentDate"
_PR_FIELDS = "PurchaseRequisition,PurchaseRequisitionType,CompanyCode,CreationDate"
_BUSINESS_PARTNER_FIELDS = (
    "BusinessPartner,BusinessPartnerFullName,BusinessPartnerCategory,"
    "BusinessPartnerGrouping,CreationDate"
)


async def _call_odata(
    client: httpx.AsyncClient, destination_name: str, service_key: str, entity_path: str, params: dict
) -> dict:
    dest = await resolve_destination(client, destination_name)
    query = dict(params)
    query.setdefault("$format", "json")
    url = f"{dest['url']}{_SERVICES[service_key]}/{entity_path}"
    headers = dest["headers"]
    proxy = dest.get("proxy")
    if proxy:
        # httpx has no per-request proxy kwarg (only a client-level one), so
        # OnPremise destinations need a short-lived client configured with it.
        headers = {**headers, **proxy["headers"]}
        async with httpx.AsyncClient(proxy=proxy["url"]) as proxied_client:
            resp = await proxied_client.get(url, headers=headers, params=query, timeout=30.0)
    else:
        resp = await client.get(url, headers=headers, params=query, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


async def _get_invoice_status(
    client: httpx.AsyncClient, destination_name: str,
    *, supplier_invoice: str, fiscal_year: str = "", company_code: str = "",
) -> dict:
    filters = [f"SupplierInvoice eq '{supplier_invoice}'"]
    if fiscal_year:
        filters.append(f"FiscalYear eq '{fiscal_year}'")
    if company_code:
        filters.append(f"CompanyCode eq '{company_code}'")
    data = await _call_odata(
        client, destination_name, "supplier_invoice", "A_SupplierInvoice",
        {
            "$filter": " and ".join(filters),
            "$select": _INVOICE_FIELDS,
            "$orderby": "FiscalYear desc,PostingDate desc",
            "$top": "1",
        },
    )
    results = data.get("d", {}).get("results", [])
    return results[0] if results else {"error": "No invoice found matching that number."}


async def _search_invoices_by_vendor(
    client: httpx.AsyncClient, destination_name: str,
    *, vendor: str, company_code: str = "", top: int = 10,
) -> list | dict:
    filters = [f"InvoicingParty eq '{vendor}'"]
    if company_code:
        filters.append(f"CompanyCode eq '{company_code}'")
    data = await _call_odata(
        client, destination_name, "supplier_invoice", "A_SupplierInvoice",
        {
            "$filter": " and ".join(filters),
            "$select": _INVOICE_FIELDS,
            "$orderby": "PostingDate desc",
            "$top": str(top),
        },
    )
    return data.get("d", {}).get("results", [])


async def _get_payment_clearing_status(
    client: httpx.AsyncClient, destination_name: str,
    *, accounting_document: str, fiscal_year: str, company_code: str = "",
) -> dict:
    filters = [
        f"AccountingDocument eq '{accounting_document}'",
        f"FiscalYear eq '{fiscal_year}'",
    ]
    if company_code:
        filters.append(f"CompanyCode eq '{company_code}'")
    data = await _call_odata(
        client, destination_name, "accounting_doc_item", "A_OperationalAcctgDocItemCube",
        {"$filter": " and ".join(filters), "$select": _CLEARING_FIELDS},
    )
    results = data.get("d", {}).get("results", [])
    return results[0] if results else {
        "error": "No accounting document found matching that number, fiscal year, and company code."
    }


async def _get_purchase_order_status(
    client: httpx.AsyncClient, destination_name: str,
    *, purchase_order: str, company_code: str = "",
) -> dict:
    filters = [f"PurchaseOrder eq '{purchase_order}'"]
    if company_code:
        filters.append(f"CompanyCode eq '{company_code}'")
    data = await _call_odata(
        client, destination_name, "purchase_order", "A_PurchaseOrder",
        {"$filter": " and ".join(filters), "$select": _PO_FIELDS},
    )
    results = data.get("d", {}).get("results", [])
    return results[0] if results else {"error": "No purchase order found matching that number and company code."}


async def _get_purchase_requisition_status(
    client: httpx.AsyncClient, destination_name: str,
    *, purchase_requisition: str, company_code: str = "",
) -> dict:
    filters = [f"PurchaseRequisition eq '{purchase_requisition}'"]
    if company_code:
        filters.append(f"CompanyCode eq '{company_code}'")
    data = await _call_odata(
        client, destination_name, "purchase_requisition", "A_PurchaseRequisition",
        {"$filter": " and ".join(filters), "$select": _PR_FIELDS},
    )
    results = data.get("d", {}).get("results", [])
    return results[0] if results else {
        "error": "No purchase requisition found matching that number and company code."
    }


async def _get_vendor_details(
    client: httpx.AsyncClient, destination_name: str, *, business_partner: str,
) -> dict:
    data = await _call_odata(
        client, destination_name, "business_partner", "A_BusinessPartner",
        {
            "$filter": f"BusinessPartner eq '{business_partner}'",
            "$select": _BUSINESS_PARTNER_FIELDS,
        },
    )
    results = data.get("d", {}).get("results", [])
    return results[0] if results else {"error": "No business partner found matching that number."}


_DISPATCH = {
    "get_invoice_status": _get_invoice_status,
    "search_invoices_by_vendor": _search_invoices_by_vendor,
    "get_payment_clearing_status": _get_payment_clearing_status,
    "get_purchase_order_status": _get_purchase_order_status,
    "get_purchase_requisition_status": _get_purchase_requisition_status,
    "get_vendor_details": _get_vendor_details,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_invoice_status",
            "description": "Look up a single supplier invoice's status and header details in SAP S/4HANA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_invoice": {"type": "string", "description": "Supplier invoice document number, e.g. '5105601234'."},
                    "fiscal_year": {"type": "string", "description": "Optional fiscal year to narrow the search, e.g. '2026'."},
                    "company_code": {"type": "string", "description": "Optional company code to narrow the search, e.g. '1000'."},
                },
                "required": ["supplier_invoice"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_invoices_by_vendor",
            "description": "Search recent supplier invoices for a given vendor (supplier) in SAP S/4HANA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string", "description": "SAP supplier/vendor account number, e.g. '100000'."},
                    "company_code": {"type": "string", "description": "Optional company code to narrow the search."},
                    "top": {"type": "integer", "description": "Maximum number of invoices to return (default 10)."},
                },
                "required": ["vendor"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_payment_clearing_status",
            "description": (
                "Check whether a payment has actually posted (cleared) against an accounting "
                "document in SAP S/4HANA - use this rather than get_invoice_status when the user "
                "specifically asks if a payment has cleared."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "accounting_document": {"type": "string", "description": "Accounting document number, e.g. '1400000123'."},
                    "fiscal_year": {"type": "string", "description": "Fiscal year the document was posted in, e.g. '2026'."},
                    "company_code": {"type": "string", "description": "Optional company code to narrow the search."},
                },
                "required": ["accounting_document", "fiscal_year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_purchase_order_status",
            "description": "Look up a purchase order's status and header details in SAP S/4HANA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "purchase_order": {"type": "string", "description": "Purchase order number, e.g. '4500001234'."},
                    "company_code": {"type": "string", "description": "Optional company code to narrow the search."},
                },
                "required": ["purchase_order"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_purchase_requisition_status",
            "description": "Look up a purchase requisition's status and header details in SAP S/4HANA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "purchase_requisition": {"type": "string", "description": "Purchase requisition number, e.g. '1000005678'."},
                    "company_code": {"type": "string", "description": "Optional company code to narrow the search."},
                },
                "required": ["purchase_requisition"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vendor_details",
            "description": (
                "Look up a vendor's (business partner's) master data in SAP S/4HANA, e.g. to "
                "confirm onboarding/setup status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "business_partner": {"type": "string", "description": "SAP business partner (vendor) number, e.g. '100000'."},
                },
                "required": ["business_partner"],
            },
        },
    },
]


async def execute_tool(client: httpx.AsyncClient, destination_name: str, name: str, arguments: dict) -> dict | list:
    """Dispatch a tool call by name to the matching S/4HANA lookup.

    Never raises: tool failures come back as {"error": ...} so the LLM can
    report them plainly instead of the whole chat turn failing.
    """
    func = _DISPATCH.get(name)
    if not func:
        return {"error": f"Unknown tool {name!r}"}
    try:
        return await func(client, destination_name, **arguments)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "s4hana_tool_call_failed",
            tool=name,
            status_code=exc.response.status_code,
            body=exc.response.text[:500],
        )
        return {"error": f"S/4HANA returned an error ({exc.response.status_code})."}
    except DestinationError as exc:
        logger.error("s4hana_destination_error", tool=name, error=str(exc))
        return {"error": f"Could not reach S/4HANA: {exc}"}
    except TypeError as exc:
        return {"error": f"Invalid arguments for {name!r}: {exc}"}
