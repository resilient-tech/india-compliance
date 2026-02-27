# System Overview

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [hooks.py](file://india_compliance/hooks.py)
- [boot.py](file://india_compliance/boot.py)
- [desktop.py](file://india_compliance/config/desktop.py)
- [gst_india.json](file://india_compliance/workspace_sidebar/gst_india.json)
- [constants/__init__.py](file://india_compliance/gst_india/constants/__init__.py)
- [audit_trail/overrides/version.py](file://india_compliance/audit_trail/overrides/version.py)
- [audit_trail/report/audit_trail/audit_trail.py](file://india_compliance/audit_trail/report/audit_trail/audit_trail.py)
- [gst_india/api_classes/nic/auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py)
- [gst_india/api_classes/nic/e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py)
- [gst_india/api_classes/nic/e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py)
- [gst_india/utils/e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py)
- [gst_india/utils/e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py)
- [gst_india/doctype/e_invoice_log/e_invoice_log.py](file://india_compliance/gst_india/doctype/e_invoice_log/e_invoice_log.py)
- [gst_india/doctype/e_waybill_log/e_waybill_log.py](file://india_compliance/gst_india/doctype/e_waybill_log/e_waybill_log.py)
- [gst_india/doctype/gst_settings/gst_settings.py](file://india_compliance/gst_india/doctype/gst_settings/gst_settings.py)
- [gst_india/doctype/purchase_reconciliation_tool/purchase_reconciliation_tool.py](file://india_compliance/gst_india/doctype/purchase_reconciliation_tool/purchase_reconciliation_tool.py)
- [gst_india/report/gstr_1/gstr_1.py](file://india_compliance/gst_india/report/gstr_1/gstr_1.py)
- [gst_india/report/gstr_3b_report/gstr_3b_report.py](file://india_compliance/gst_india/report/gstr_3b_report/gstr_3b_report.py)
- [gst_india/report/e_invoice_summary/e_invoice_summary.py](file://india_compliance/gst_india/report/e_invoice_summary/e_invoice_summary.py)
- [gst_india/print_format/e_invoice/e_invoice.py](file://india_compliance/gst_india/print_format/e_invoice/e_invoice.py)
- [gst_india/print_format/e_waybill/e_waybill.py](file://india_compliance/gst_india/print_format/e_waybill/e_waybill.py)
- [gst_india/client_scripts/sales_invoice.js](file://india_compliance/gst_india/client_scripts/sales_invoice.js)
- [gst_india/client_scripts/purchase_invoice.js](file://india_compliance/gst_india/client_scripts/purchase_invoice.js)
- [gst_india/client_scripts/e_waybill_actions.js](file://india_compliance/gst_india/client_scripts/e_waybill_actions.js)
- [gst_india/client_scripts/e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js)
- [gst_india/overrides/sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py)
- [gst_india/overrides/purchase_invoice.py](file://india_compliance/gst_india/overrides/purchase_invoice.py)
- [gst_india/overrides/company.py](file://india_compliance/gst_india/overrides/company.py)
- [gst_india/overrides/party.py](file://india_compliance/gst_india/overrides/party.py)
- [gst_india/overrides/transaction.py](file://india_compliance/gst_india/overrides/transaction.py)
- [gst_india/overrides/delivery_note.py](file://india_compliance/gst_india/overrides/delivery_note.py)
- [gst_india/overrides/item.py](file://india_compliance/gst_india/overrides/item.py)
- [gst_india/overrides/item_tax_template.py](file://india_compliance/gst_india/overrides/item_tax_template.py)
- [gst_india/overrides/payment_entry.py](file://india_compliance/gst_india/overrides/payment_entry.py)
- [gst_india/overrides/journal_entry.py](file://india_compliance/gst_india/overrides/journal_entry.py)
- [gst_india/overrides/gl_entry.py](file://india_compliance/gst_india/overrides/gl_entry.py)
- [gst_india/overrides/tax_category.py](file://india_compliance/gst_india/overrides/tax_category.py)
- [gst_india/overrides/subcontracting_transaction.py](file://india_compliance/gst_india/overrides/subcontracting_transaction.py)
- [gst_india/overrides/unreconcile_payment.py](file://india_compliance/gst_india/overrides/unreconcile_payment.py)
- [income_tax_india/overrides/company.py](file://india_compliance/income_tax_india/overrides/company.py)
- [income_tax_india/overrides/tax_withholding_category.py](file://india_compliance/income_tax_india/overrides/tax_withholding_category.py)
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

## Introduction
India Compliance is an ERPNext extension designed to simplify compliance with Indian Rules and Regulations. It integrates tightly with ERPNext and the Frappe Framework to automate recurring compliance tasks, particularly around Goods and Services Tax (GST). The system focuses on:
- E-invoice generation aligned with IRP (Invoice Registration Portal)
- E-waybill management for inter-state and intra-state movement
- Audit trail maintenance for regulatory transparency
- Comprehensive reporting for GSTR-1, GSTR-3B, and reconciliation
- Real-time validation via GST APIs and intelligent data mapping

Target audience includes businesses in India that require GST compliance automation, streamlined invoice actions, and robust reporting capabilities without replacing ERPNext’s core functionality.

**Section sources**
- [README.md](file://README.md#L26-L64)

## Project Structure
The application is organized as a Frappe app layered under ERPNext. Key areas:
- Core app metadata and hooks for ERPNext integration
- Boot-time initialization for client-side context
- GST-specific domain modules (e-invoice, e-waybill, returns, reconciliation)
- Audit trail subsystem for maintaining compliance logs
- Income Tax module for TDS-related integrations
- Workspace and desktop navigation tailored for GST India
- Extensive client scripts and overrides to extend ERPNext behavior

```mermaid
graph TB
ERPNext["ERPNext Core"]
Hooks["india_compliance/hooks.py<br/>App hooks, overrides, scheduler"]
Boot["india_compliance/boot.py<br/>Boot info, notifications"]
Desktop["india_compliance/config/desktop.py<br/>Desk module"]
Workspace["india_compliance/workspace_sidebar/gst_india.json<br/>Workspace links"]
GST["gst_india/<br/>E-Invoice, E-Waybill, Returns, Reconciliation"]
Audit["audit_trail/<br/>Audit trail, reports, overrides"]
IncomeTax["income_tax_india/<br/>TDS, Asset Depreciation"]
Reports["gst_india/report/*<br/>GSTR-1, GSTR-3B, E-Invoice Summary"]
Print["gst_india/print_format/*<br/>E-Invoice, E-Waybill"]
ClientScripts["gst_india/client_scripts/*<br/>UI actions, validations"]
Overrides["gst_india/overrides/*<br/>DocType behavior extensions"]
ERPNext --> Hooks
Hooks --> Boot
Hooks --> Desktop
Hooks --> Workspace
Hooks --> GST
Hooks --> Audit
Hooks --> IncomeTax
GST --> Reports
GST --> Print
GST --> ClientScripts
GST --> Overrides
```

**Diagram sources**
- [hooks.py](file://india_compliance/hooks.py#L1-L120)
- [boot.py](file://india_compliance/boot.py#L1-L76)
- [desktop.py](file://india_compliance/config/desktop.py#L1-L14)
- [gst_india.json](file://india_compliance/workspace_sidebar/gst_india.json#L1-L131)

**Section sources**
- [hooks.py](file://india_compliance/hooks.py#L1-L120)
- [boot.py](file://india_compliance/boot.py#L1-L76)
- [desktop.py](file://india_compliance/config/desktop.py#L1-L14)
- [gst_india.json](file://india_compliance/workspace_sidebar/gst_india.json#L1-L131)

## Core Components
- E-Invoice Module
  - Generation, cancellation, and retry workflows
  - IRP integration and logging
  - Print formats and QR code generation
- E-Waybill Module
  - Auto-applicability detection and actions
  - Scheduling and extension utilities
  - Logging and print formats
- GST Settings and Credentials
  - Centralized configuration for GST operations
  - API credentials and sandbox mode support
- Audit Trail
  - Maintains logs for key documents and settings
  - Notifications and triggers for compliance visibility
- Returns and Reconciliation
  - GSTR-1 and GSTR-3B reporting utilities
  - Purchase Reconciliation Tool for GSTR-2A/2B matching
- Income Tax (TDS)
  - Overrides for company fixtures and tax withholding categories
- Workspace and Navigation
  - GST India workspace with shortcuts to tools and reports

Key value propositions:
- E-invoice generation aligned with IRP
- E-waybill management with scheduling and extension
- Audit trail maintenance for compliance transparency
- Intelligent reporting for GSTR-1, GSTR-3B, and reconciliation
- Real-time validation via GST APIs

**Section sources**
- [README.md](file://README.md#L37-L64)
- [gst_india/doctype/gst_settings/gst_settings.py](file://india_compliance/gst_india/doctype/gst_settings/gst_settings.py)
- [gst_india/doctype/e_invoice_log/e_invoice_log.py](file://india_compliance/gst_india/doctype/e_invoice_log/e_invoice_log.py)
- [gst_india/doctype/e_waybill_log/e_waybill_log.py](file://india_compliance/gst_india/doctype/e_waybill_log/e_waybill_log.py)
- [audit_trail/overrides/version.py](file://india_compliance/audit_trail/overrides/version.py)
- [gst_india/report/gstr_1/gstr_1.py](file://india_compliance/gst_india/report/gstr_1/gstr_1.py)
- [gst_india/report/gstr_3b_report/gstr_3b_report.py](file://india_compliance/gst_india/report/gstr_3b_report/gstr_3b_report.py)
- [gst_india/report/e_invoice_summary/e_invoice_summary.py](file://india_compliance/gst_india/report/e_invoice_summary/e_invoice_summary.py)
- [gst_india/print_format/e_invoice/e_invoice.py](file://india_compliance/gst_india/print_format/e_invoice/e_invoice.py)
- [gst_india/print_format/e_waybill/e_waybill.py](file://india_compliance/gst_india/print_format/e_waybill/e_waybill.py)

## Architecture Overview
India Compliance extends ERPNext by:
- Installing as an app with required dependencies on ERPNext
- Registering hooks for document events, regional overrides, and scheduler tasks
- Injecting client scripts and UI actions for GST-specific workflows
- Providing backend utilities for API communication and data processing
- Maintaining audit trail and generating compliance-ready reports

```mermaid
graph TB
subgraph "ERPNext"
SalesInv["Sales Invoice"]
PurchaseInv["Purchase Invoice"]
DeliveryNote["Delivery Note"]
PaymentEntry["Payment Entry"]
JournalEntry["Journal Entry"]
GL["GL Entry"]
Item["Item"]
Party["Party"]
Company["Company"]
end
subgraph "India Compliance"
Overrides["Overrides<br/>gst_india/overrides/*"]
Utils["Utils<br/>gst_india/utils/*"]
Logs["Logs<br/>e_invoice_log, e_waybill_log"]
Reports["Reports<br/>gstr_1, gstr_3b_report, e_invoice_summary"]
PrintFmt["Print Formats<br/>e_invoice, e_waybill"]
Client["Client Scripts<br/>gst_india/client_scripts/*"]
Audit["Audit Trail<br/>audit_trail/*"]
Settings["GST Settings<br/>gst_settings"]
end
SalesInv --> Overrides
PurchaseInv --> Overrides
DeliveryNote --> Overrides
PaymentEntry --> Overrides
JournalEntry --> Overrides
GL --> Overrides
Item --> Overrides
Party --> Overrides
Company --> Overrides
Overrides --> Utils
Overrides --> Logs
Overrides --> Reports
Overrides --> PrintFmt
Overrides --> Client
Overrides --> Audit
Overrides --> Settings
```

**Diagram sources**
- [hooks.py](file://india_compliance/hooks.py#L118-L388)
- [gst_india/overrides/transaction.py](file://india_compliance/gst_india/overrides/transaction.py)
- [gst_india/utils/e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py)
- [gst_india/utils/e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py)
- [gst_india/doctype/e_invoice_log/e_invoice_log.py](file://india_compliance/gst_india/doctype/e_invoice_log/e_invoice_log.py)
- [gst_india/doctype/e_waybill_log/e_waybill_log.py](file://india_compliance/gst_india/doctype/e_waybill_log/e_waybill_log.py)
- [gst_india/report/gstr_1/gstr_1.py](file://india_compliance/gst_india/report/gstr_1/gstr_1.py)
- [gst_india/report/gstr_3b_report/gstr_3b_report.py](file://india_compliance/gst_india/report/gstr_3b_report/gstr_3b_report.py)
- [gst_india/report/e_invoice_summary/e_invoice_summary.py](file://india_compliance/gst_india/report/e_invoice_summary/e_invoice_summary.py)
- [gst_india/print_format/e_invoice/e_invoice.py](file://india_compliance/gst_india/print_format/e_invoice/e_invoice.py)
- [gst_india/print_format/e_waybill/e_waybill.py](file://india_compliance/gst_india/print_format/e_waybill/e_waybill.py)
- [gst_india/client_scripts/sales_invoice.js](file://india_compliance/gst_india/client_scripts/sales_invoice.js)
- [gst_india/client_scripts/purchase_invoice.js](file://india_compliance/gst_india/client_scripts/purchase_invoice.js)
- [audit_trail/overrides/version.py](file://india_compliance/audit_trail/overrides/version.py)
- [gst_india/doctype/gst_settings/gst_settings.py](file://india_compliance/gst_india/doctype/gst_settings/gst_settings.py)

## Detailed Component Analysis

### E-Invoice Workflow
End-to-end flow from invoice submission to IRP integration and logging.

```mermaid
sequenceDiagram
participant User as "User"
participant SI as "Sales Invoice"
participant Overrides as "gst_india/overrides/sales_invoice.py"
participant Utils as "gst_india/utils/e_invoice.py"
participant NIC as "gst_india/api_classes/nic/e_invoice.py"
participant Log as "e_invoice_log"
User->>SI : Submit Sales Invoice
SI->>Overrides : on_submit/on_update_after_submit
Overrides->>Utils : prepare_e_invoice_data()
Utils->>NIC : generate_e_invoice()
NIC-->>Utils : {ackNum, ackDt, qrCode, eli, rc}
Utils->>Log : create e-invoice log
Log-->>User : Status and JSON/XML
```

**Diagram sources**
- [gst_india/overrides/sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py)
- [gst_india/utils/e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py)
- [gst_india/api_classes/nic/e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py)
- [gst_india/doctype/e_invoice_log/e_invoice_log.py](file://india_compliance/gst_india/doctype/e_invoice_log/e_invoice_log.py)

**Section sources**
- [gst_india/overrides/sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py)
- [gst_india/utils/e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py)
- [gst_india/api_classes/nic/e_invoice.py](file://india_compliance/gst_india/api_classes/nic/e_invoice.py)
- [gst_india/doctype/e_invoice_log/e_invoice_log.py](file://india_compliance/gst_india/doctype/e_invoice_log/e_invoice_log.py)

### E-Waybill Workflow
Auto-applicability detection, generation, and scheduling.

```mermaid
sequenceDiagram
participant User as "User"
participant PI as "Purchase Invoice"
participant Overrides as "gst_india/overrides/purchase_invoice.py"
participant Utils as "gst_india/utils/e_waybill.py"
participant NIC as "gst_india/api_classes/nic/e_waybill.py"
participant Log as "e_waybill_log"
User->>PI : Validate/Submit
PI->>Overrides : validate/before_submit
Overrides->>Utils : check_applicability()
Utils->>NIC : generate_e_waybill()
NIC-->>Utils : {ewayBillNumber,ewayBillDate,validUpto}
Utils->>Log : create e-waybill log
Log-->>User : Status and print format
```

**Diagram sources**
- [gst_india/overrides/purchase_invoice.py](file://india_compliance/gst_india/overrides/purchase_invoice.py)
- [gst_india/utils/e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py)
- [gst_india/api_classes/nic/e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py)
- [gst_india/doctype/e_waybill_log/e_waybill_log.py](file://india_compliance/gst_india/doctype/e_waybill_log/e_waybill_log.py)

**Section sources**
- [gst_india/overrides/purchase_invoice.py](file://india_compliance/gst_india/overrides/purchase_invoice.py)
- [gst_india/utils/e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py)
- [gst_india/api_classes/nic/e_waybill.py](file://india_compliance/gst_india/api_classes/nic/e_waybill.py)
- [gst_india/doctype/e_waybill_log/e_waybill_log.py](file://india_compliance/gst_india/doctype/e_waybill_log/e_waybill_log.py)

### Audit Trail Maintenance
Tracks changes to key documents and settings, with notifications and triggers.

```mermaid
flowchart TD
Start(["Document Change"]) --> CheckAudit["Check Audit Trail Enabled"]
CheckAudit --> |Enabled| Capture["Capture Version/Property Setter Changes"]
CheckAudit --> |Disabled| Skip["Skip Audit"]
Capture --> Notify["Enqueue Notification if Required"]
Notify --> End(["Done"])
Skip --> End
```

**Diagram sources**
- [audit_trail/overrides/version.py](file://india_compliance/audit_trail/overrides/version.py)
- [boot.py](file://india_compliance/boot.py#L47-L57)

**Section sources**
- [audit_trail/overrides/version.py](file://india_compliance/audit_trail/overrides/version.py)
- [boot.py](file://india_compliance/boot.py#L47-L57)

### Purchase Reconciliation Tool
Automates matching of GSTR-2A/2B with purchase invoices.

```mermaid
flowchart TD
Init["Initiate Tool"] --> Download["Download GSTR-2A/2B"]
Download --> Match["Auto-match with Purchase Invoices"]
Match --> Reconcile["Reconcile and Update Status"]
Reconcile --> Report["Generate Reconciliation Report"]
Report --> End(["Done"])
```

**Diagram sources**
- [gst_india/doctype/purchase_reconciliation_tool/purchase_reconciliation_tool.py](file://india_compliance/gst_india/doctype/purchase_reconciliation_tool/purchase_reconciliation_tool.py)

**Section sources**
- [gst_india/doctype/purchase_reconciliation_tool/purchase_reconciliation_tool.py](file://india_compliance/gst_india/doctype/purchase_reconciliation_tool/purchase_reconciliation_tool.py)

### GST Settings and API Credentials
Centralized configuration for GST operations and API access.

```mermaid
classDiagram
class GSTSettings {
+string gstin
+bool sandbox_mode
+string ic_api_secret
+dict credentials
+dict gst_accounts
+enable_e_invoice()
+enable_e_waybill()
}
class APICredentials {
+string username
+string password
+string app_key
+string auth_token
}
GSTSettings --> APICredentials : "stores"
```

**Diagram sources**
- [gst_india/doctype/gst_settings/gst_settings.py](file://india_compliance/gst_india/doctype/gst_settings/gst_settings.py)
- [gst_india/api_classes/nic/auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py)

**Section sources**
- [gst_india/doctype/gst_settings/gst_settings.py](file://india_compliance/gst_india/doctype/gst_settings/gst_settings.py)
- [gst_india/api_classes/nic/auth.py](file://india_compliance/gst_india/api_classes/nic/auth.py)

## Dependency Analysis
- App-level dependencies
  - Required app: frappe/erpnext
  - Boot-time and runtime dependencies for GST operations
- Regional overrides
  - Extends ERPNext’s regional accounting behavior for GST and TDS
- Scheduler-driven tasks
  - Retry e-invoice/e-waybill generation
  - Auto-download and reconcile GSTR-2A/2B
  - Extend scheduled e-waybills
- Client-side integration
  - Client scripts for UI actions and validations across Sales/Purchase/Stock documents

```mermaid
graph LR
Hooks["hooks.py"] --> Overrides["gst_india/overrides/*"]
Hooks --> ClientScripts["gst_india/client_scripts/*"]
Hooks --> Scheduler["Scheduler Events"]
Overrides --> Utils["gst_india/utils/*"]
Overrides --> Logs["e_invoice_log/e_waybill_log"]
Overrides --> Reports["gst_india/report/*"]
Overrides --> PrintFmt["gst_india/print_format/*"]
Overrides --> Audit["audit_trail/*"]
Overrides --> Settings["gst_india/doctype/gst_settings"]
Scheduler --> Utils
```

**Diagram sources**
- [hooks.py](file://india_compliance/hooks.py#L353-L492)
- [gst_india/overrides/transaction.py](file://india_compliance/gst_india/overrides/transaction.py)
- [gst_india/utils/e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py)
- [gst_india/utils/e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py)
- [gst_india/doctype/e_invoice_log/e_invoice_log.py](file://india_compliance/gst_india/doctype/e_invoice_log/e_invoice_log.py)
- [gst_india/doctype/e_waybill_log/e_waybill_log.py](file://india_compliance/gst_india/doctype/e_waybill_log/e_waybill_log.py)
- [gst_india/report/gstr_1/gstr_1.py](file://india_compliance/gst_india/report/gstr_1/gstr_1.py)
- [gst_india/report/gstr_3b_report/gstr_3b_report.py](file://india_compliance/gst_india/report/gstr_3b_report/gstr_3b_report.py)
- [gst_india/print_format/e_invoice/e_invoice.py](file://india_compliance/gst_india/print_format/e_invoice/e_invoice.py)
- [gst_india/print_format/e_waybill/e_waybill.py](file://india_compliance/gst_india/print_format/e_waybill/e_waybill.py)
- [audit_trail/overrides/version.py](file://india_compliance/audit_trail/overrides/version.py)
- [gst_india/doctype/gst_settings/gst_settings.py](file://india_compliance/gst_india/doctype/gst_settings/gst_settings.py)

**Section sources**
- [hooks.py](file://india_compliance/hooks.py#L353-L492)

## Performance Considerations
- Batch retries and scheduled jobs reduce manual intervention for failed e-invoice/e-waybill generations.
- Centralized GST settings minimize repeated credential lookups and improve reliability.
- Client scripts optimize UI responsiveness by deferring heavy computations to server-side utilities.
- Reports leverage pre-built mappings to GSTR formats, reducing real-time computation overhead.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common areas to check:
- E-invoice/e-waybill generation failures
  - Verify GST Settings and API credentials
  - Review logs and retry mechanisms
- Audit trail not capturing changes
  - Confirm audit trail is enabled and notifications are configured
- Purchase reconciliation mismatches
  - Refresh GSTR downloads and review match criteria
- Scheduler tasks not running
  - Confirm scheduler configuration and job intervals

**Section sources**
- [gst_india/doctype/gst_settings/gst_settings.py](file://india_compliance/gst_india/doctype/gst_settings/gst_settings.py)
- [gst_india/doctype/e_invoice_log/e_invoice_log.py](file://india_compliance/gst_india/doctype/e_invoice_log/e_invoice_log.py)
- [gst_india/doctype/e_waybill_log/e_waybill_log.py](file://india_compliance/gst_india/doctype/e_waybill_log/e_waybill_log.py)
- [audit_trail/overrides/version.py](file://india_compliance/audit_trail/overrides/version.py)
- [gst_india/doctype/purchase_reconciliation_tool/purchase_reconciliation_tool.py](file://india_compliance/gst_india/doctype/purchase_reconciliation_tool/purchase_reconciliation_tool.py)
- [hooks.py](file://india_compliance/hooks.py#L473-L492)

## Conclusion
India Compliance is a modular, ERPNext-native extension that automates GST compliance workflows. By integrating with NIC APIs, extending ERPNext document behaviors, and providing audit trail and reporting capabilities, it enables businesses to meet regulatory requirements efficiently. The modular design allows selective activation of features per company needs, ensuring flexibility and scalability across diverse compliance scenarios.

[No sources needed since this section summarizes without analyzing specific files]