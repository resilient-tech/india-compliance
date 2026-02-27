# Taxpayer Portal Communication

<cite>
**Referenced Files in This Document**
- [base.py](file://india_compliance/gst_india/api_classes/base.py)
- [public.py](file://india_compliance/gst_india/api_classes/public.py)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py)
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py)
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py)
- [e_waybill_errors.py](file://india_compliance/gst_india/api_classes/nic/e_waybill_errors.py)
- [india_compliance_api_usage.py](file://india_compliance/gst_india/report/india_compliance_api_usage/india_compliance_api_usage.py)
- [india_compliance_api_usage.js](file://india_compliance/gst_india/report/india_compliance_api_usage/india_compliance_api_usage.js)
- [gstr_action.py](file://india_compliance/gst_india/doctype/gstr_action/gstr_action.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)
10. [Appendices](#appendices)

## Introduction
This document explains taxpayer portal communication patterns implemented in the codebase, focusing on:
- Direct taxpayer portal integration via authenticated sessions and encryption
- Public API access for autofill and return tracking
- Authentication mechanisms, API key management, and secure communication protocols
- Differences between taxpayer portal and NIC portal integration patterns
- Public API endpoints, whitelisting, and external system integration
- Practical usage examples, response handling, and error recovery
- Security considerations, rate limiting, and API usage monitoring

## Project Structure
The taxpayer portal communication is implemented across several API classes:
- Base HTTP client and shared utilities
- Public API for autofill and return tracking
- Taxpayer portal APIs for returns and e-invoice/e-waybill downloads
- NIC portal APIs for e-invoice and e-waybill with dual authentication modes

```mermaid
graph TB
subgraph "Base Layer"
BaseAPI["BaseAPI<br/>HTTP client, masking, logging"]
end
subgraph "Public APIs"
PublicAPI["PublicAPI<br/>Autofill & Returns Info"]
end
subgraph "Taxpayer Portal"
TaxpayerBaseAPI["TaxpayerBaseAPI<br/>Encrypted requests/responses"]
ReturnsAPI["ReturnsAPI<br/>GSTR-1/2A/2B/3B/IMS"]
EInvoiceTaxpayer["EInvoiceAPI<br/>IRN list/details/download"]
end
subgraph "NIC Portal"
NICAuth["NIC Auth Strategies<br/>Standard vs Enriched"]
EInvoiceNIC["EInvoiceAPI<br/>Standard/Enriched"]
EWaybillNIC["EWaybillAPI<br/>Standard/Enriched"]
NICErrors["NIC Error Codes"]
end
BaseAPI --> PublicAPI
BaseAPI --> TaxpayerBaseAPI
TaxpayerBaseAPI --> ReturnsAPI
TaxpayerBaseAPI --> EInvoiceTaxpayer
BaseAPI --> EInvoiceNIC
BaseAPI --> EWaybillNIC
EInvoiceNIC --> NICAuth
EWaybillNIC --> NICAuth
EWaybillNIC --> NICErrors
```

**Diagram sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L23-L413)
- [public.py](file://india_compliance/gst_india/api_classes/public.py#L7-L65)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L321-L527)
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L10-L395)
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L7-L69)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L27-L195)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L12-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L17-L259)
- [e_waybill_errors.py](file://india_compliance/gst_india/api_classes/nic/e_waybill_errors.py#L1-L337)

**Section sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L23-L413)
- [public.py](file://india_compliance/gst_india/api_classes/public.py#L7-L65)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L321-L527)
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L10-L395)
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L7-L69)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L27-L195)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L12-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L17-L259)
- [e_waybill_errors.py](file://india_compliance/gst_india/api_classes/nic/e_waybill_errors.py#L1-L337)

## Core Components
- BaseAPI: Shared HTTP client with request/response lifecycle, error handling, masking, and integration logging.
- PublicAPI: Stateless public endpoints for autofill and return tracking.
- TaxpayerBaseAPI: Encrypted request/response pipeline for taxpayer portal returns and downloads.
- NIC APIs: Dual-mode e-invoice and e-waybill APIs supporting both Standard (client-side encryption) and Enriched (GSP-managed) authentication.
- Error mapping: Comprehensive error code mapping for NIC e-waybill.

**Section sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L23-L413)
- [public.py](file://india_compliance/gst_india/api_classes/public.py#L7-L65)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L321-L527)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L12-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L17-L259)
- [e_waybill_errors.py](file://india_compliance/gst_india/api_classes/nic/e_waybill_errors.py#L1-L337)

## Architecture Overview
The system supports two primary integration patterns:
- Taxpayer portal integration: Requires authenticated sessions, encryption/decryption, and HMAC validation for secure data exchange.
- NIC portal integration: Supports Standard (client-side encryption) and Enriched (GSP-managed) authentication modes.

```mermaid
sequenceDiagram
participant Client as "Client"
participant TaxAPI as "TaxpayerBaseAPI"
participant NICAuth as "NIC Auth Strategy"
participant GSP as "Government Portal"
Client->>TaxAPI : "Setup with GSTIN"
TaxAPI->>TaxAPI : "Fetch credentials"
TaxAPI->>TaxAPI : "Encrypt request"
TaxAPI->>GSP : "POST /standard/gstn_/... (encrypted)"
GSP-->>TaxAPI : "Response (encrypted)"
TaxAPI->>TaxAPI : "Decrypt response + HMAC verify"
TaxAPI-->>Client : "Parsed result"
```

**Diagram sources**
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L321-L527)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L27-L195)

## Detailed Component Analysis

### Public API Access (Autofill and Returns Tracking)
PublicAPI exposes:
- Autofill party information by GSTIN
- Returns tracking by GSTIN and financial year

Key behaviors:
- Enforces sandbox restrictions for autofill
- Generates request IDs for traceability
- Ignores specific “no documents found” error codes

```mermaid
sequenceDiagram
participant Client as "Client"
participant Pub as "PublicAPI"
participant ASP as "ASP Public API"
Client->>Pub : "get_gstin_info(gstin)"
Pub->>ASP : "GET /commonapi/search?action=TP&gstin={gstin}"
ASP-->>Pub : "Party info"
Pub-->>Client : "Party info"
Client->>Pub : "get_returns_info(gstin, fy)"
Pub->>ASP : "GET /commonapi/returns?action=RETTRACK&gstin={gstin}&fy={fy}"
ASP-->>Pub : "Returns status"
Pub-->>Client : "Returns status"
```

**Diagram sources**
- [public.py](file://india_compliance/gst_india/api_classes/public.py#L31-L65)

**Section sources**
- [public.py](file://india_compliance/gst_india/api_classes/public.py#L7-L65)

### Taxpayer Portal Integration (Returns and Downloads)
TaxpayerBaseAPI implements:
- Encrypted request preparation and HMAC-verified responses
- Session-based authentication with OTP handling
- Download pipeline for return-related files

```mermaid
sequenceDiagram
participant Client as "Client"
participant TaxAPI as "TaxpayerBaseAPI"
participant Auth as "TaxpayerAuthenticate"
participant GSP as "GST Returns API"
Client->>TaxAPI : "Setup(company_gstin)"
TaxAPI->>Auth : "Authenticate with OTP or cached token"
Auth-->>TaxAPI : "auth_token, session_key, expiry"
TaxAPI->>TaxAPI : "Encrypt request payload"
TaxAPI->>GSP : "GET/POST with auth-token"
GSP-->>TaxAPI : "Encrypted response + HMAC"
TaxAPI->>TaxAPI : "Decrypt + HMAC verify"
TaxAPI-->>Client : "Parsed result"
```

**Diagram sources**
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L321-L527)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L110-L320)

**Section sources**
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L110-L320)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L321-L527)

### Returns APIs (GSTR-1/2A/2B/3B/IMS)
ReturnsAPI and specialized classes expose:
- GSTR-1 summary and e-invoice data
- GSTR-2A/2B retrieval and regeneration
- GSTR-3B data, offsets, interest, and filing
- IMS data retrieval and save/reset

```mermaid
flowchart TD
Start(["ReturnsAPI Call"]) --> Choose["Choose Return Type"]
Choose --> |GSTR-1| GSTR1["get_gstr_1_data / save / reset / file"]
Choose --> |GSTR-2A/2B| GSTR2["get_data / regenerate / status"]
Choose --> |GSTR-3B| GSTR3B["get_data / save / submit / interest / offsets"]
Choose --> |IMS| IMS["get_data / save / reset / status"]
GSTR1 --> End(["Return Parsed Data"])
GSTR2 --> End
GSTR3B --> End
IMS --> End
```

**Diagram sources**
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L10-L395)

**Section sources**
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L10-L395)

### e-Invoice Taxpayer Integration
EInvoiceAPI provides:
- IRN list filtering by period, supplier/recipient GSTIN
- IRN details lookup
- File downloads for e-invoice batches

```mermaid
sequenceDiagram
participant Client as "Client"
participant EI as "EInvoiceAPI"
participant GSP as "GST e-Invoice API"
Client->>EI : "get_irn_list(period, type, filters)"
EI->>GSP : "GET /einvoice?action=IRNLIST..."
GSP-->>EI : "IRN list"
EI-->>Client : "IRN list"
Client->>EI : "download_files(period, token)"
EI->>GSP : "GET /einvoice?action=FILEDETL..."
GSP-->>EI : "File metadata"
EI->>EI : "Decrypt + parse"
EI-->>Client : "Decrypted files"
```

**Diagram sources**
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L34-L69)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L479-L491)

**Section sources**
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L7-L69)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L479-L491)

### NIC Portal Integration (e-Invoice and e-Waybill)
Dual authentication modes:
- Standard: Client-side encryption/decryption and HMAC verification
- Enriched: GSP manages encryption/decryption

```mermaid
classDiagram
class BaseAPI {
+get()/post()/put()
+process_response()
+handle_error_response()
+mask_sensitive_info()
}
class NICAuth {
<<abstract>>
+prepare_request()
+process_response()
}
class StandardAuth {
+prepare_request()
+process_response()
-_encrypt_request()
-_decrypt_response()
}
class EnrichedAuth {
+prepare_request()
+process_response()
}
class EInvoiceAPI {
+generate_irn()
+get_e_invoice_by_irn()
+cancel_irn()
+update_distance()
}
class EWaybillAPI {
+generate_e_waybill()
+get_e_waybill()
+cancel_e_waybill()
+update_vehicle_info()
+extend_validity()
+update_transporter()
}
BaseAPI <|-- EInvoiceAPI
BaseAPI <|-- EWaybillAPI
NICAuth <|-- StandardAuth
NICAuth <|-- EnrichedAuth
EInvoiceAPI --> StandardAuth : "uses"
EWaybillAPI --> StandardAuth : "uses"
EInvoiceAPI --> EnrichedAuth : "uses"
EWaybillAPI --> EnrichedAuth : "uses"
```

**Diagram sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L23-L413)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L27-L195)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L12-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L17-L259)

**Section sources**
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L27-L195)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L12-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L17-L259)

### Error Handling and Recovery
- BaseAPI handles HTTP codes and raises domain-specific exceptions.
- TaxpayerBaseAPI and NIC APIs implement error code mapping and ignored-error handling.
- OTP handling for taxpayer portal authentication.

```mermaid
flowchart TD
Start(["API Request"]) --> MakeReq["Make HTTP Request"]
MakeReq --> Resp["Parse Response"]
Resp --> Success{"Success?"}
Success --> |Yes| Process["Process Response"]
Success --> |No| HandleErr["Map Error Codes / Ignore Errors"]
HandleErr --> Retry{"Retry/Auth?"}
Retry --> |OTP| OTPFlow["Request/Submit OTP"]
Retry --> |Token| Refresh["Refresh Token"]
Retry --> |No| Throw["Throw Error"]
OTPFlow --> MakeReq
Refresh --> MakeReq
Process --> End(["Return Result"])
Throw --> End
```

**Diagram sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L124-L220)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L443-L477)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L211-L259)

**Section sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L124-L220)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L443-L477)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L211-L259)

## Dependency Analysis
- BaseAPI is the foundation for all API clients and enforces consistent error handling and logging.
- Taxpayer APIs depend on encryption utilities and credential storage.
- NIC APIs depend on authentication strategies and error code mapping.

```mermaid
graph LR
BaseAPI --> PublicAPI
BaseAPI --> TaxpayerBaseAPI
TaxpayerBaseAPI --> ReturnsAPI
TaxpayerBaseAPI --> EInvoiceTaxpayer
BaseAPI --> EInvoiceNIC
BaseAPI --> EWaybillNIC
EInvoiceNIC --> NICAuth
EWaybillNIC --> NICAuth
EWaybillNIC --> NICErrors
```

**Diagram sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L23-L413)
- [public.py](file://india_compliance/gst_india/api_classes/public.py#L7-L65)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L321-L527)
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L10-L395)
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L7-L69)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L27-L195)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L12-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L17-L259)
- [e_waybill_errors.py](file://india_compliance/gst_india/api_classes/nic/e_waybill_errors.py#L1-L337)

**Section sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L23-L413)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L321-L527)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L12-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L17-L259)

## Performance Considerations
- Encryption/decryption overhead: Prefer batched downloads and reuse of authenticated sessions.
- Scheduler dependency: e-Invoice/e-Waybill features require the scheduler to be enabled.
- Sandbox mode: Use for development; avoid in production for taxpayer portal APIs.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and recovery steps:
- API key invalid or credits exhausted: Validate API key and ensure sufficient credits.
- Authentication failures: Reset auth token and retry; ensure IP is whitelisted.
- OTP-related errors: Handle OTP requested and invalid OTP scenarios.
- HMAC mismatch: Indicates tampering or decryption key mismatch.
- NIC token invalid: Refresh token and retry request.

**Section sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L282-L312)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L443-L477)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L174-L183)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L211-L259)

## Conclusion
The codebase implements robust, secure taxpayer portal communication with:
- Encrypted request/response pipelines and HMAC verification
- Dual authentication modes for NIC APIs
- Public APIs for autofill and returns tracking
- Comprehensive error handling and recovery
- Monitoring via integration logs and usage reports

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### API Usage Monitoring
- India Compliance API Usage report aggregates API requests by endpoint/date/document.

```mermaid
flowchart TD
Start(["Run Report"]) --> Filters["Select Filters (by Endpoint/Date/Document)"]
Filters --> Query["Query Integration Requests"]
Query --> Aggregate["Aggregate Counts"]
Aggregate --> Output["Render Columns + Data"]
Output --> End(["View Report"])
```

**Diagram sources**
- [india_compliance_api_usage.py](file://india_compliance/gst_india/report/india_compliance_api_usage/india_compliance_api_usage.py#L19-L101)
- [india_compliance_api_usage.js](file://india_compliance/gst_india/report/india_compliance_api_usage/india_compliance_api_usage.js#L4-L42)

**Section sources**
- [india_compliance_api_usage.py](file://india_compliance/gst_india/report/india_compliance_api_usage/india_compliance_api_usage.py#L19-L101)
- [india_compliance_api_usage.js](file://india_compliance/gst_india/report/india_compliance_api_usage/india_compliance_api_usage.js#L4-L42)

### External System Integration and Webhooks
- Government portal callbacks are recorded and linked to documents via GSTR Action records.

```mermaid
sequenceDiagram
participant GSP as "Government Portal"
participant System as "ERPNext"
participant Doc as "Document"
participant Log as "GSTRAction"
GSP-->>System : "Callback with token"
System->>Log : "set_gstr_actions(doc, type, token, id)"
Log-->>Doc : "Attach action row"
Doc-->>System : "Trigger downstream tasks"
```

**Diagram sources**
- [gstr_action.py](file://india_compliance/gst_india/doctype/gstr_action/gstr_action.py#L12-L29)

**Section sources**
- [gstr_action.py](file://india_compliance/gst_india/doctype/gstr_action/gstr_action.py#L12-L29)