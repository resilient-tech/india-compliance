# Data Validation & Business Rules

<cite>
**Referenced Files in This Document**
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py)
- [e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py)
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py)
- [purchase_invoice.py](file://india_compliance/gst_india/overrides/purchase_invoice.py)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py)
- [e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js)
- [e_waybill_applicability.js](file://india_compliance/gst_india/client_scripts/e_waybill_applicability.js)
- [address.py](file://india_compliance/gst_india/overrides/address.py)
- [__init__.py](file://india_compliance/gst_india/constants/__init__.py)
- [test_transaction.py](file://india_compliance/gst_india/overrides/test_transaction.py)
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
This document explains the data validation rules and business logic enforcement for GST-enabled document creation and modifications in the India Compliance module. It covers:
- GSTIN format validation and state alignment checks
- Place of supply determination and tax category classification
- e-invoice and e-waybill applicability thresholds, amount limits, and compliance requirements
- Validation logic for reverse charge, exports, and interstate supplies
- Error handling, validation messages, and user feedback
- Integration between client-side validation and server-side processing
- Alignment with government compliance requirements

## Project Structure
The validation and business logic span several modules:
- Overrides for Sales/Purchase transactions enforce GST-specific validations during save/submit/cancel
- Utilities generate e-invoices/e-waybills and apply strict validation rules
- Client scripts provide user-facing applicability checks and feedback
- Constants define GST categories, tax types, and state mappings used across validations

```mermaid
graph TB
subgraph "Client Scripts"
JS_EINV["e_invoice_actions.js"]
JS_EWB["e_waybill_applicability.js"]
end
subgraph "Overrides"
OV_Sales["sales_invoice.py"]
OV_Purchase["purchase_invoice.py"]
OV_Transaction["transaction.py"]
OV_Address["address.py"]
end
subgraph "Utilities"
UT_TransData["transaction_data.py"]
UT_EInvoice["e_invoice.py"]
UT_EWaybill["e_waybill.py"]
end
CONST["constants/__init__.py"]
JS_EINV --> UT_EInvoice
JS_EWB --> UT_EWaybill
OV_Sales --> UT_EInvoice
OV_Sales --> UT_EWaybill
OV_Purchase --> UT_EWaybill
OV_Transaction --> UT_TransData
OV_Address --> OV_Transaction
UT_EInvoice --> UT_TransData
UT_EWaybill --> UT_TransData
UT_TransData --> CONST
```

**Diagram sources**
- [e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js#L1-L422)
- [e_waybill_applicability.js](file://india_compliance/gst_india/client_scripts/e_waybill_applicability.js#L1-L141)
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L1-L383)
- [purchase_invoice.py](file://india_compliance/gst_india/overrides/purchase_invoice.py#L1-L268)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L1-L800)
- [address.py](file://india_compliance/gst_india/overrides/address.py#L96-L105)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L1-L704)
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L1-L800)
- [e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py#L1-L800)
- [__init__.py](file://india_compliance/gst_india/constants/__init__.py#L1-L800)

**Section sources**
- [e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js#L1-L422)
- [e_waybill_applicability.js](file://india_compliance/gst_india/client_scripts/e_waybill_applicability.js#L1-L141)
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L1-L383)
- [purchase_invoice.py](file://india_compliance/gst_india/overrides/purchase_invoice.py#L1-L268)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L1-L800)
- [address.py](file://india_compliance/gst_india/overrides/address.py#L96-L105)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L1-L704)
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L1-L800)
- [e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py#L1-L800)
- [__init__.py](file://india_compliance/gst_india/constants/__init__.py#L1-L800)

## Core Components
- GSTIN validation and state alignment: Ensures GSTIN prefix matches the state number and validates postal code ranges per state.
- Place of supply and tax category classification: Determines PoS based on party and address fields and maps GST categories to e-Invoice classifications.
- e-Invoice applicability: Thresholds, mandatory fields, item taxability, and date gating.
- e-waybill applicability: Thresholds, goods presence, and transport-related validations.
- Reverse charge and export validations: Prevents invalid account usage and enforces export rules.
- Client-server integration: Client-side checks surface applicability and validation messages; server-side processing enforces strict rules and logs outcomes.

**Section sources**
- [address.py](file://india_compliance/gst_india/overrides/address.py#L96-L105)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L581-L613)
- [__init__.py](file://india_compliance/gst_india/constants/__init__.py#L28-L63)
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L553-L604)
- [e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py#L166-L332)
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L263-L273)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L381-L410)

## Architecture Overview
End-to-end flow for e-invoice and e-waybill generation with validation:

```mermaid
sequenceDiagram
participant User as "User"
participant Client as "Client Script"
participant Sales as "Sales Invoice Override"
participant Utils as "E-Invoice/EWaybill Utils"
participant TransData as "Transaction Data"
participant API as "GST Gateway API"
User->>Client : Open Sales Invoice
Client->>Client : Validate invoice number, PoS, HSN
Client-->>User : Show applicability status/messages
User->>Sales : Submit Sales Invoice
Sales->>TransData : Build transaction data
Sales->>Utils : Validate e-invoice/e-waybill applicability
Utils->>API : Generate IRN / EWaybill
API-->>Utils : Result (success/error)
Utils-->>Sales : Log and update status
Sales-->>User : Notify outcome and update fields
```

**Diagram sources**
- [e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js#L325-L421)
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L70-L108)
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L119-L267)
- [e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py#L154-L332)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L280-L316)

## Detailed Component Analysis

### GSTIN Validation and State Alignment
- GSTIN prefix must match the state number derived from the address.
- Postal code must align with state’s first three-digit pincode range; otherwise, a validation error is raised with a link to master codes.

```mermaid
flowchart TD
Start(["Validate GSTIN and Address"]) --> CheckPrefix["Compare GSTIN prefix with state number"]
CheckPrefix --> PrefixMatch{"Match?"}
PrefixMatch --> |No| ThrowPrefix["Throw invalid GSTIN/state error"]
PrefixMatch --> |Yes| ValidatePincode["Validate pincode range for state"]
ValidatePincode --> PincodeValid{"Valid?"}
PincodeValid --> |No| ThrowPincode["Throw invalid postal code error"]
PincodeValid --> |Yes| End(["Validation Passed"])
```

**Diagram sources**
- [address.py](file://india_compliance/gst_india/overrides/address.py#L96-L105)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L268-L296)

**Section sources**
- [address.py](file://india_compliance/gst_india/overrides/address.py#L96-L105)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L268-L296)

### Place of Supply and Tax Category Classification
- Place of supply is determined based on party details and doctype-specific logic.
- GST categories map to e-Invoice classification codes (B2B, B2C, EXP, SEZ, etc.).

```mermaid
flowchart TD
PS_Start(["Compute Place of Supply"]) --> UseParty["Use company/supplier GSTIN or fallback address state"]
UseParty --> IsOverseas{"Overseas?"}
IsOverseas --> |Yes| PoS96["PoS = 96-Other Countries"]
IsOverseas --> |No| StateCode["State code from GSTIN or address"]
StateCode --> PoSComputed["PoS = <state>-<name>"]
PoS96 --> PoSComputed
PoSComputed --> CatMap["Map GST Category to e-Invoice Category"]
CatMap --> End(["Ready for validation"])
```

**Diagram sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L402-L410)
- [__init__.py](file://india_compliance/gst_india/constants/__init__.py#L28-L39)

**Section sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L402-L410)
- [__init__.py](file://india_compliance/gst_india/constants/__init__.py#L28-L39)

### e-Invoice Validation Rules
- Applicability checks:
  - Company and billing GSTIN must differ
  - At least one taxable or zero-rated item required
  - B2C invoices require billing GSTIN; exports allowed without payment of GST
  - Applicability date gating enforced via settings
- Additional validations:
  - Customer address mandatory for e-Invoice
  - Item count limit enforced
  - HSN/SAC mandatory and length validated
  - Invoice number validation performed

```mermaid
flowchart TD
EInvStart(["Validate e-Invoice Applicability"]) --> CheckGSTIN["Company GSTIN != Billing GSTIN"]
CheckGSTIN --> GSTINOK{"OK?"}
GSTINOK --> |No| Block["Block e-Invoice"]
GSTINOK --> |Yes| CheckItems["Has taxable/zero-rated item?"]
CheckItems --> ItemsOK{"OK?"}
ItemsOK --> |No| Block
ItemsOK --> |Yes| CheckB2C["B2C: Billing GSTIN present?"]
CheckB2C --> B2COK{"OK?"}
B2COK --> |No| Block
B2COK --> |Yes| CheckDate["Posting date >= Applicable From?"]
CheckDate --> DateOK{"OK?"}
DateOK --> |No| Block
DateOK --> |Yes| CheckFields["Customer address, HSN/SAC, invoice number OK?"]
CheckFields --> FieldsOK{"OK?"}
FieldsOK --> |No| Block
FieldsOK --> |Yes| Proceed["Proceed to Generate IRN"]
```

**Diagram sources**
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L553-L604)
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L95-L130)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L280-L316)

**Section sources**
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L553-L604)
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L95-L130)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L280-L316)

### e-Invoice Generation and Cancellation Flow
```mermaid
sequenceDiagram
participant UI as "Client UI"
participant Actions as "e_invoice_actions.js"
participant Utils as "e_invoice.py"
participant API as "GST API"
UI->>Actions : Click "Generate"
Actions->>Utils : generate_e_invoice(docname, force=true)
Utils->>Utils : validate_e_invoice_applicability()
Utils->>API : Generate IRN
API-->>Utils : IRN or error
Utils-->>Actions : Log and update status
Actions-->>UI : Success/Failure message
UI->>Actions : Click "Cancel"
Actions->>Utils : cancel_e_invoice(docname, values)
Utils->>API : Cancel IRN
API-->>Utils : Result
Utils-->>Actions : Log and update status
Actions-->>UI : Success/Failure message
```

**Diagram sources**
- [e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js#L42-L99)
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L119-L267)

**Section sources**
- [e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js#L1-L422)
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L119-L267)

### e-Waybill Validation Rules and Auto-Generation
- Applicability threshold: Grand total must exceed the configured e-waybill threshold.
- Must include at least one non-service item (HSN not starting with 99).
- Transporter details required depending on mode of transport.
- Auto-generation conditions: enabled in settings, not a return/debit note, and applicable.

```mermaid
flowchart TD
EWBStart(["Validate e-Waybill Applicability"]) --> CheckThreshold["Grand Total >= Threshold"]
CheckThreshold --> ThreshOK{"OK?"}
ThreshOK --> |No| Block["Not Applicable"]
ThreshOK --> |Yes| CheckGoods["Has goods item (HSN not starting with 99)?"]
CheckGoods --> GoodsOK{"OK?"}
GoodsOK --> |No| Block
GoodsOK --> |Yes| CheckTransport["Mode of Transport / Vehicle/LR set?"]
CheckTransport --> TransOK{"OK?"}
TransOK --> |No| Block
TransOK --> |Yes| AutoGen["Auto-generate if enabled and conditions met"]
AutoGen --> End(["Ready to Generate"])
```

**Diagram sources**
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L263-L273)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L192-L231)
- [e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py#L166-L332)

**Section sources**
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L263-L273)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L192-L231)
- [e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py#L166-L332)

### Reverse Charge and Export Validation
- Reverse charge:
  - Prevents using RCM accounts when not applicable
  - Validates tax rows and ensures correct charge types
- Export:
  - Overseas transactions require appropriate settings and shipping address rules
  - Export without payment of GST disallows charging GST in specific validations

```mermaid
flowchart TD
RCStart(["Reverse Charge Validation"]) --> CheckRCM["Is RCM applicable?"]
CheckRCM --> RCMApplies{"Yes?"}
RCMApplies --> |No| BlockRCM["Disallow RCM accounts"]
RCMApplies --> |Yes| ValidateRows["Validate tax rows and charge types"]
ValidateRows --> RCMPass["Proceed"]
ExpStart(["Export Validation"]) --> CheckOverseas["GST Category = Overseas?"]
CheckOverseas --> OverOK{"Enabled and valid?"}
OverOK --> |No| BlockExp["Disallow or require settings"]
OverOK --> |Yes| CheckPoS["PoS within India vs shipping address"]
CheckPoS --> ExpPass["Proceed"]
```

**Diagram sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L366-L410)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L381-L410)
- [test_transaction.py](file://india_compliance/gst_india/overrides/test_transaction.py#L577-L602)

**Section sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L366-L410)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L381-L410)
- [test_transaction.py](file://india_compliance/gst_india/overrides/test_transaction.py#L577-L602)

### Client-Side Validation and User Feedback
- Client scripts provide applicability checks and messages before submission.
- Buttons appear conditionally based on applicability and status.
- Dialogs guide users through manual updates for IRN/e-Waybill and cancellation reasons.

```mermaid
sequenceDiagram
participant User as "User"
participant Client as "Client Script"
participant Sales as "Sales Invoice Override"
User->>Client : Open Sales Invoice
Client->>Client : Check e-invoice/e-waybill applicability
Client-->>User : Show "Applicability Status" and buttons
User->>Client : Click "Generate" / "Cancel"
Client->>Sales : Trigger server-side generation/cancellation
Sales-->>Client : Outcome
Client-->>User : Success/Failure message and updates
```

**Diagram sources**
- [e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js#L1-L154)
- [e_waybill_applicability.js](file://india_compliance/gst_india/client_scripts/e_waybill_applicability.js#L1-L141)
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L70-L108)

**Section sources**
- [e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js#L1-L154)
- [e_waybill_applicability.js](file://india_compliance/gst_india/client_scripts/e_waybill_applicability.js#L1-L141)
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L70-L108)

## Dependency Analysis
Key dependencies and relationships:
- Overrides depend on transaction data utilities for building transaction payloads and validating fields.
- e-Invoice and e-Waybill utilities depend on constants for GST categories, tax types, and state mappings.
- Client scripts trigger server-side utilities and display user feedback.

```mermaid
graph TB
OV_Sales["sales_invoice.py"] --> UT_EInvoice["e_invoice.py"]
OV_Sales --> UT_EWaybill["e_waybill.py"]
OV_Purchase --> UT_EWaybill
OV_Transaction --> UT_TransData["transaction_data.py"]
UT_EInvoice --> UT_TransData
UT_EWaybill --> UT_TransData
UT_TransData --> CONST["constants/__init__.py"]
JS_EINV["e_invoice_actions.js"] --> UT_EInvoice
JS_EWB["e_waybill_applicability.js"] --> UT_EWaybill
```

**Diagram sources**
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L1-L383)
- [purchase_invoice.py](file://india_compliance/gst_india/overrides/purchase_invoice.py#L1-L268)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L1-L800)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L1-L704)
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L1-L800)
- [e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py#L1-L800)
- [__init__.py](file://india_compliance/gst_india/constants/__init__.py#L1-L800)
- [e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js#L1-L422)
- [e_waybill_applicability.js](file://india_compliance/gst_india/client_scripts/e_waybill_applicability.js#L1-L141)

**Section sources**
- [sales_invoice.py](file://india_compliance/gst_india/overrides/sales_invoice.py#L1-L383)
- [purchase_invoice.py](file://india_compliance/gst_india/overrides/purchase_invoice.py#L1-L268)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L1-L800)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L1-L704)
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L1-L800)
- [e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py#L1-L800)
- [__init__.py](file://india_compliance/gst_india/constants/__init__.py#L1-L800)
- [e_invoice_actions.js](file://india_compliance/gst_india/client_scripts/e_invoice_actions.js#L1-L422)
- [e_waybill_applicability.js](file://india_compliance/gst_india/client_scripts/e_waybill_applicability.js#L1-L141)

## Performance Considerations
- Batch operations for e-invoice/e-waybill generation use job queues with timeouts proportional to document counts.
- Validation functions short-circuit on failure to minimize unnecessary processing.
- Logging and status updates are asynchronous to avoid blocking UI.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common validation failures and resolutions:
- Duplicate IRN with mismatched buyer GSTIN or invoice amount:
  - System compares previous IRN details and throws a structured error with corrective steps.
- Invalid GSTIN or inactive status:
  - System syncs GSTIN status and retries generation if status is active.
- Item-level HSN/SAC errors:
  - Missing or invalid lengths trigger targeted messages; fix per valid lengths and re-save.
- Place of supply or overseas category mismatch:
  - Ensure shipping address and category align with rules; update address or category accordingly.
- Reverse charge misuse:
  - Remove RCM accounts when not applicable; ensure correct charge types for cess accounts.
- e-Waybill transport details:
  - Set vehicle/LR details as required by mode of transport; ensure distance constraints.

Resolution procedures:
- Fix validation messages indicated by the system and re-run validation.
- For duplicate IRN, follow corrective steps to generate a new invoice or reconcile IRN details.
- For API errors, review GST portal status and retry after corrections.

**Section sources**
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L270-L375)
- [e_invoice.py](file://india_compliance/gst_india/utils/e_invoice.py#L166-L191)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L689-L704)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L691-L747)
- [e_waybill.py](file://india_compliance/gst_india/utils/e_waybill.py#L203-L232)

## Conclusion
The India Compliance module enforces robust GST validation and business rules across document lifecycle events. Client-side applicability checks improve user experience, while server-side utilities ensure strict compliance with e-Invoice/e-Waybill requirements and government mandates. Clear error messaging and logging facilitate troubleshooting and maintain audit trails.