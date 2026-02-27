# Taxpayer Portal Integration

<cite>
**Referenced Files in This Document**
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py)
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py)
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py)
- [base.py](file://india_compliance/gst_india/api_classes/base.py)
- [public.py](file://india_compliance/gst_india/api_classes/public.py)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py)
- [cryptography.py](file://india_compliance/gst_india/utils/cryptography.py)
- [api.py](file://india_compliance/gst_india/utils/api.py)
- [gst_settings.py](file://india_compliance/gst_india/doctype/gst_settings/gst_settings.py)
- [gst_return_log.py](file://india_compliance/gst_india/doctype/gst_return_log/gst_return_log.py)
- [gstr_utils.py](file://india_compliance/gst_india/utils/gstr_utils.py)
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
This document explains the taxpayer portal integration for the India Compliance module, focusing on:
- Taxpayer-specific authentication mechanisms and session/IP binding
- API endpoints for GST return filing (GSTR-1, GSTR-3B, GSTR-2A/B, IMS)
- Status query systems and queued downloads
- e-invoice and e-waybill management via taxpayer portal
- Static resources API for templates and forms
- Practical usage patterns, authentication tokens, and session management
- Differences between taxpayer portal and NIC portal integrations

## Project Structure
The taxpayer portal integration is implemented primarily in Python classes under the GST India API layer. Key modules:
- Base HTTP client and request lifecycle
- Taxpayer portal authentication and request signing
- Returns APIs for GSTR-1, GSTR-3B, GSTR-2A/B, and IMS
- e-Invoice and e-Waybill APIs (NIC-standard and enriched variants)
- Utilities for logging, cryptography, and integration request persistence

```mermaid
graph TB
subgraph "Base Layer"
BA["BaseAPI<br/>HTTP client & logging"]
CR["cryptography.py<br/>AES/HMAC/Hash"]
end
subgraph "Taxpayer Portal"
TB["TaxpayerBaseAPI<br/>Headers, auth token, encryption"]
TA["TaxpayerAuthenticate<br/>OTP, refresh, IP binding"]
TEI["EInvoiceAPI<br/>IRN list/details/download"]
TR["ReturnsAPI<br/>GSTR-1/3B/GSTR2A/B/IMS"]
SR["StaticResourcesAPI<br/>Public keys/certificates"]
FI["FilesAPI<br/>Download & decrypt tar.gz"]
end
subgraph "NIC Integrations"
NA["StandardAuth<br/>Public key/session key"]
EI["StandardEInvoiceAPI<br/>e-Invoice"]
EW["StandardEWaybillAPI<br/>e-Waybill"]
end
BA --> TB
TB --> TA
TB --> TEI
TB --> TR
TB --> SR
TB --> FI
BA --> NA
NA --> EI
NA --> EW
BA --> CR
```

**Diagram sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L23-L120)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L110-L320)
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L7-L69)
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L10-L395)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L27-L195)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L12-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L17-L259)
- [cryptography.py](file://india_compliance/gst_india/utils/cryptography.py#L19-L76)

**Section sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L23-L120)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L110-L320)
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L10-L395)
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L7-L69)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L27-L195)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L12-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L17-L259)
- [cryptography.py](file://india_compliance/gst_india/utils/cryptography.py#L19-L76)

## Core Components
- BaseAPI: Central HTTP client with request/response lifecycle, error handling, masking, and integration request logging.
- TaxpayerBaseAPI: Extends BaseAPI with taxpayer portal headers, auth token, encryption/signing, and OTP handling.
- TaxpayerAuthenticate: Manages OTP requests, authentication token refresh, and IP-bound sessions.
- ReturnsAPI family: GSTR-1, GSTR-3B, GSTR-2A/B, and IMS endpoints for retrieval, saving, resetting, and filing.
- EInvoiceAPI: IRN listing, details, and file downloads for taxpayer portal.
- StaticResourcesAPI and FilesAPI: Retrieve public keys/certificates and download/verify/decrypt return files.
- NIC StandardAuth/EInvoiceAPI/EWaybillAPI: Alternative integration pattern for e-Invoice/e-Waybill via NIC.

**Section sources**
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L23-L240)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L110-L320)
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L10-L395)
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L7-L69)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L27-L195)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L12-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L17-L259)

## Architecture Overview
The taxpayer portal flow integrates with the ASP gateway using encrypted requests and HMAC verification. Authentication is OTP-based and session-bound to the taxpayer’s public IP.

```mermaid
sequenceDiagram
participant Client as "Client"
participant API as "TaxpayerBaseAPI"
participant Auth as "TaxpayerAuthenticate"
participant ASP as "ASP Gateway"
Client->>API : setup(company_gstin)
API->>Auth : get_auth_token()
alt token missing/expired
Auth->>ASP : POST authenticate (OTPREQUEST)
ASP-->>Auth : status_cd=1, otp requested
Auth-->>API : OTPRequestedError(response)
Client->>API : authenticate_with_otp(otp)
API->>ASP : POST authenticate (AUTHTOKEN)
ASP-->>API : auth_token, sek, expiry
API->>API : decrypt_response()<br/>store session_key/session_expiry
else token valid
API->>ASP : GET/POST returns/einvoice with auth-token
ASP-->>API : encrypted data + hmac
API->>API : decrypt_response(), verify hmac
API-->>Client : decrypted result
end
```

**Diagram sources**
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L110-L320)
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L124-L220)

## Detailed Component Analysis

### Taxpayer Authentication and Session Management
- OTP request and authentication:
  - OTP request initiates via authenticate endpoint with app_key and username.
  - On success, an OTP is requested; subsequent AUTHTOKEN call exchanges OTP for auth_token, sek, and expiry.
- Session IP binding:
  - Public IP fetched from ASP and stored; all requests include ip-usr header.
- Token refresh and validation:
  - REFRESHTOKEN endpoint rotates tokens.
  - validate_auth_token performs a dummy request to pre-validate tokens.
- Error handling:
  - Specific error codes mapped to user-friendly error types (e.g., otp_requested, invalid_otp, authorization_failed).
  - Public key rotation triggered when invalid public key error occurs.

```mermaid
flowchart TD
Start(["Start"]) --> CheckToken["Check auth_token + expiry"]
CheckToken --> |Valid| MakeReq["Make API request with auth-token"]
CheckToken --> |Expired/Missing| RequestOTP["OTP request"]
RequestOTP --> OTPReq["Send OTPREQUEST"]
OTPReq --> OTPResp{"OTP requested?"}
OTPResp --> |Yes| RaiseOTP["Raise OTPRequestedError"]
OTPResp --> |No| AuthToken["Send AUTHTOKEN with OTP"]
AuthToken --> StoreCreds["Store auth_token, sek, expiry"]
StoreCreds --> MakeReq
MakeReq --> DecryptVerify["Decrypt response + verify HMAC"]
DecryptVerify --> End(["End"])
```

**Diagram sources**
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L110-L320)
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L124-L220)

**Section sources**
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L110-L320)
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L124-L220)

### Returns APIs: GSTR-1, GSTR-3B, GSTR-2A/B, IMS
- GSTR-1:
  - Retrieve summary and sections, save draft data, reset, and file with EVC (PAN + EVC OTP).
  - Download e-invoice data for GSTR-1.
- GSTR-3B:
  - Retrieve summary, save, submit, offset liabilities, auto-calc interest, recompute interest, manage balances.
- GSTR-2A/2B:
  - Retrieve data by return period, regenerate 2B, check generation status.
- IMS:
  - Retrieve invoice data, save/reset, get request status, download files.

```mermaid
classDiagram
class ReturnsAPI {
+download_files(return_period, token)
+get_return_status(return_period, reference_id)
+proceed_to_file(return_type, return_period, is_nil_return)
}
class GSTR1API {
+get_gstr_1_data(action, return_period)
+get_einvoice_data(section, return_period)
+save_gstr_1_data(return_period, data)
+reset_gstr_1_data(return_period)
+file_gstr_1(return_period, summary_data, pan, evc_otp)
}
class GSTR3bAPI {
+get_data()
+save_gstr3b(data)
+submit_gstr3b(data)
+save_offset_liability_gstr3b(data)
+file_gstr_3b(data, pan, evc_otp)
+get_itc_liab_data()
+validate_3b_against_auto_calc(data)
+get_system_calc_interest()
+recompute_interest()
+save_past_liab(data)
+get_itc_reversal_bal()
+get_rcm_bal()
+get_opening_bal()
+get_rcm_opening_bal()
+save_opening_bal(data)
+submit_rcm_opening_bal(data)
}
class GSTR2aAPI {
+get_data(action, return_period)
}
class GSTR2bAPI {
+get_data(return_period, file_num)
+regenerate(return_period)
+generation_status(transaction_id)
}
class IMSAPI {
+get_data(section)
+download_files(return_period, token)
+get_files(return_period, token, action, endpoint)
+save(data)
+reset(data)
+get_request_status(transaction_id)
}
ReturnsAPI <|-- GSTR1API
ReturnsAPI <|-- GSTR3bAPI
ReturnsAPI <|-- GSTR2aAPI
ReturnsAPI <|-- GSTR2bAPI
ReturnsAPI <|-- IMSAPI
```

**Diagram sources**
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L10-L395)

**Section sources**
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L10-L395)

### e-Invoice and e-Waybill via Taxpayer Portal
- EInvoiceAPI:
  - List IRNs, get IRN details, and download files for a return period.
- FilesAPI:
  - Download encrypted tar.gz archives, verify SHA-256 hash, decrypt with session key, and parse JSON.

```mermaid
sequenceDiagram
participant Client as "Client"
participant EIAPI as "EInvoiceAPI"
participant TPAPI as "TaxpayerBaseAPI"
participant Files as "FilesAPI"
participant ASP as "ASP Gateway"
Client->>EIAPI : download_files(return_period, token)
EIAPI->>TPAPI : get(action=FILEDETL, endpoint=einvoice)
TPAPI->>ASP : GET returns/einvoice?ret_period&token
ASP-->>TPAPI : {urls : [{ul, hash, ek}], status}
TPAPI-->>EIAPI : response
EIAPI->>Files : get_all(url_details)
loop for each URL
Files->>ASP : GET ul
ASP-->>Files : tar.gz bytes
Files->>Files : verify hash
Files->>Files : decrypt with ek
Files-->>EIAPI : merged JSON
end
EIAPI-->>Client : decrypted data
```

**Diagram sources**
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L65-L69)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L47-L108)
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L124-L220)

**Section sources**
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L7-L69)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L47-L108)

### Static Resources and Templates
- StaticResourcesAPI:
  - Retrieve GSTN public certificate and NIC public key from ASP.
- PublicAPI:
  - Provides common endpoints for GSTIN info and returns tracking; useful for template discovery and status queries.

**Section sources**
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L47-L68)
- [public.py](file://india_compliance/gst_india/api_classes/public.py#L7-L65)

### Integration Request Logging and Scheduling
- Integration requests are persisted asynchronously with masked sensitive data.
- Scheduler requirement enforced for e-Invoice/e-Waybill features.

**Section sources**
- [api.py](file://india_compliance/gst_india/utils/api.py#L4-L57)
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L372-L394)

## Dependency Analysis
- Cryptography:
  - AES ECB for symmetric encryption/decryption of payloads and session keys.
  - HMAC-SHA256 for integrity verification.
  - Hash-256 for file integrity checks.
- Authentication:
  - Taxpayer portal uses OTP-based tokens with session IP binding.
  - NIC integration uses asymmetric encryption with public/private keys and session-based HMAC verification.

```mermaid
graph LR
CR["cryptography.py"] --> TA["TaxpayerAuthenticate"]
CR --> TB["TaxpayerBaseAPI"]
CR --> NA["StandardAuth"]
TA --> TB
NA --> EI["StandardEInvoiceAPI"]
NA --> EW["StandardEWaybillAPI"]
```

**Diagram sources**
- [cryptography.py](file://india_compliance/gst_india/utils/cryptography.py#L19-L76)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L247-L442)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L80-L184)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L178-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L152-L259)

**Section sources**
- [cryptography.py](file://india_compliance/gst_india/utils/cryptography.py#L19-L76)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L247-L442)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L80-L184)

## Performance Considerations
- Asynchronous file downloads:
  - Queued downloads are processed in background jobs to avoid blocking UI.
- Request masking:
  - Sensitive headers and bodies are masked before logging to reduce risk exposure.
- Scheduler enforcement:
  - Ensures reliable background tasks for e-Invoice/e-Waybill generation and retries.

**Section sources**
- [gstr_utils.py](file://india_compliance/gst_india/utils/gstr_utils.py#L55-L128)
- [api.py](file://india_compliance/gst_india/utils/api.py#L4-L57)
- [base.py](file://india_compliance/gst_india/api_classes/base.py#L372-L394)

## Troubleshooting Guide
- OTP-related errors:
  - OTPRequestedError and InvalidOTPError are raised and handled gracefully; retry with a fresh OTP.
- Authorization failures:
  - Refresh token or re-authenticate; verify session IP binding.
- Public key invalid:
  - StaticResourcesAPI refreshes the GSTN public certificate automatically.
- Queued downloads:
  - Use download_queued_request to process pending return file downloads.
- Return filing status:
  - Use get_return_status and GST Return Log to track filing status and acknowledgments.

**Section sources**
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L113-L125)
- [gstr_utils.py](file://india_compliance/gst_india/utils/gstr_utils.py#L55-L128)
- [gst_return_log.py](file://india_compliance/gst_india/doctype/gst_return_log/gst_return_log.py#L141-L153)

## Conclusion
The taxpayer portal integration provides a secure, encrypted, and session-aware pathway to GST returns and e-invoice/e-waybill operations. It supports robust OTP-based authentication, HMAC verification, and asynchronous file downloads. Compared to NIC integrations, taxpayer portal APIs emphasize encrypted payloads and HMAC verification, while NIC APIs rely on asymmetric encryption and standardized authentication flows. Choose the integration pattern based on your use case: taxpayer portal for return filing and document downloads, NIC APIs for e-Invoice/e-Waybill generation.

## Appendices

### Practical Usage Patterns
- Authentication:
  - Request OTP and authenticate to obtain an auth token with session key and expiry.
  - Use validate_auth_token to pre-validate tokens.
- Return filing:
  - For GSTR-1: retrieve summary, save data, reset if needed, and file with EVC (PAN + EVC OTP).
  - For GSTR-3B: retrieve summary, save/submit, compute interest, and manage balances.
- Downloads:
  - Use download_files to fetch queued return files and decrypt them locally.
- Templates and Forms:
  - Use PublicAPI endpoints for GSTIN info and returns tracking; StaticResourcesAPI for certificates/keys.

**Section sources**
- [gstr_utils.py](file://india_compliance/gst_india/utils/gstr_utils.py#L29-L53)
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L115-L183)
- [taxpayer_returns.py](file://india_compliance/gst_india/api_classes/taxpayer_returns.py#L185-L240)
- [taxpayer_e_invoice.py](file://india_compliance/gst_india/api_classes/taxpayer_e_invoice.py#L65-L69)
- [public.py](file://india_compliance/gst_india/api_classes/public.py#L31-L47)
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L47-L68)

### Differences: Taxpayer Portal vs NIC Portal
- Authentication:
  - Taxpayer portal: OTP-based, session-bound IP, encrypted requests with HMAC.
  - NIC portal: Username/password/app_key, optional asymmetric encryption, separate auth endpoints.
- Encryption:
  - Taxpayer portal: Uses session key for payload encryption and HMAC verification.
  - NIC portal: Uses public key for initial encryption and session key for subsequent requests.
- Use Cases:
  - Taxpayer portal: Return filing, e-invoice/e-waybill via taxpayer channel, file downloads.
  - NIC portal: Direct e-Invoice/e-Waybill generation and management.

**Section sources**
- [taxpayer_base.py](file://india_compliance/gst_india/api_classes/taxpayer_base.py#L247-L442)
- [auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py#L80-L184)
- [e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py#L178-L271)
- [e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py#L152-L259)