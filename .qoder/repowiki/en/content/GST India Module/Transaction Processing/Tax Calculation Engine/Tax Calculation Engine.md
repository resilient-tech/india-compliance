# Tax Calculation Engine

<cite>
**Referenced Files in This Document**
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py)
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py)
- [constants/__init__.py](file://india_compliance/gst_india/constants/__init__.py)
- [gst_account.py](file://india_compliance/gst_india/doctype/gst_account/gst_account.py)
- [payment_entry.py](file://india_compliance/gst_india/overrides/payment_entry.py)
- [gst_account_wise_summary.py](file://india_compliance/gst_india/report/gst_account_wise_summary/gst_account_wise_summary.py)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py)
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
This document explains the Tax Calculation Engine for India Compliance with a focus on:
- GST rate application and mapping
- Multi-state (inter-state vs intra-state) calculations
- ITC (Input Tax Credit) management and validation
- Taxes controller utility functions for tax computation logic
- Place of supply determination
- Proportional charges allocation and tax rounding
- GST account mapping by transaction type, place of supply, and reverse charge conditions
- Practical scenarios and common issues with resolutions

## Project Structure
The Tax Calculation Engine spans Python utilities, overrides, reports, and constants:
- taxes_controller.py: Centralized tax computation logic for item-level to document-level totals
- transaction.py: Place of supply, inter-state determination, tax template selection, validations, and GST account mapping
- ineligible_itc.py: ITC eligibility, proportionate reversal, and valuation adjustments
- utils/__init__.py: Place of supply helpers, GST account retrieval, and regional helpers
- constants/__init__.py: GST constants, state mappings, and tax type definitions
- Reports and utilities: Apportionment of charges and progressive tax amount handling

```mermaid
graph TB
subgraph "Tax Calculation Engine"
TC["taxes_controller.py"]
TR["transaction.py"]
II["ineligible_itc.py"]
UT["utils/__init__.py"]
CT["constants/__init__.py"]
GA["doctype/gst_account/gst_account.py"]
PE["overrides/payment_entry.py"]
RPT["report/gst_account_wise_summary/gst_account_wise_summary.py"]
TD["utils/transaction_data.py"]
end
TC --> TR
TR --> UT
TR --> CT
II --> TR
II --> UT
PE --> UT
RPT --> TR
TD --> TR
GA --> UT
```

**Diagram sources**
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L104-L275)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L212-L275)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L18-L140)
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py#L487-L646)
- [constants/__init__.py](file://india_compliance/gst_india/constants/__init__.py#L9-L23)
- [gst_account.py](file://india_compliance/gst_india/doctype/gst_account/gst_account.py#L1-L10)
- [payment_entry.py](file://india_compliance/gst_india/overrides/payment_entry.py#L276-L310)
- [gst_account_wise_summary.py](file://india_compliance/gst_india/report/gst_account_wise_summary/gst_account_wise_summary.py#L81-L158)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L386-L426)

**Section sources**
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L104-L275)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L212-L275)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L18-L140)
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py#L487-L646)
- [constants/__init__.py](file://india_compliance/gst_india/constants/__init__.py#L9-L23)
- [gst_account.py](file://india_compliance/gst_india/doctype/gst_account/gst_account.py#L1-L10)
- [payment_entry.py](file://india_compliance/gst_india/overrides/payment_entry.py#L276-L310)
- [gst_account_wise_summary.py](file://india_compliance/gst_india/report/gst_account_wise_summary/gst_account_wise_summary.py#L81-L158)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L386-L426)

## Core Components
- Taxes Controller (CustomTaxController): Computes item-wise tax rates, updates taxable values, computes tax amounts per row, and sets totals and grand totals. Handles actual vs percentage charge types and rounding for GST accounts.
- Place of Supply and Inter-State Determination: Determines POS based on party/address and compares with company GSTIN state to decide intra/inter-state.
- GST Account Mapping: Maps transaction type (sales/purchase), POS, and reverse charge to applicable GST accounts (CGST/SGST/IGST).
- ITC Management: Validates ITC eligibility, computes proportionate ineligible tax amounts, adjusts valuation rates, and books reversing entries.

**Section sources**
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L104-L275)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L402-L483)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L75-L140)
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py#L402-L484)

## Architecture Overview
The engine orchestrates tax computation across item and document levels, with validations and account mapping integrated into transaction processing.

```mermaid
sequenceDiagram
participant Doc as "Document"
participant TC as "CustomTaxController"
participant TR as "Transaction Utils"
participant UT as "GST Utils"
participant II as "Ineligible ITC"
Doc->>TC : set_taxes_and_totals()
TC->>TC : set_item_wise_tax_rates()
TC->>TR : update_item_taxable_value()
TC->>TC : update_tax_amount()
TC->>TC : update_base_grand_total()
TC->>UT : get_all_gst_accounts()
UT-->>TC : GST accounts list
TC->>II : validate ITC eligibility (per doc)
II-->>Doc : adjusted valuation rates/GL entries
```

**Diagram sources**
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L118-L183)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L402-L483)
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py#L627-L646)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L75-L140)

## Detailed Component Analysis

### Taxes Controller Utility Functions
- Purpose: Compute tax amounts per item and document totals, apply charge types, and manage rounding for GST accounts.
- Key responsibilities:
  - Item-wise tax rate mapping from templates/accounts
  - Taxable value updates with proportional charges
  - Tax amount computation by charge type (percentage vs quantity)
  - Round-off handling for GST accounts
  - Total and grand total updates

```mermaid
classDiagram
class CustomTaxController {
+set_taxes_and_totals()
+set_item_wise_tax_rates(item_name, tax_name)
+update_item_taxable_value()
+update_tax_amount()
+update_base_grand_total()
+get_item_tax_map(tax_templates, tax_accounts)
+get_tax_amount(item_wise_tax_rates, charge_type)
+calculate_total_taxable_value()
+get_value(field, doc, default)
+get_fieldname(field)
}
class CustomItemGSTDetails {
+tax_amount_field()
+tax_details_field()
+get_item_tax_rate(item, tax_row)
+set_temp_item_wise_tax_detail_object()
+build_item_wise_tax_detail_from_data()
}
CustomTaxController --> CustomItemGSTDetails : "uses"
```

**Diagram sources**
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L104-L275)

**Section sources**
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L118-L246)

### Place of Supply and Inter-State Determination
- Place of Supply (POS) determination:
  - Uses party address and GSTIN to derive state code and name
  - Supports overseas exports and fallbacks for unregistered customers
- Inter-State determination:
  - Compares POS state code with company GSTIN state code
  - Treats SEZ as inter-state for output transactions

```mermaid
flowchart TD
Start(["Start"]) --> GetParty["Get party details<br/>and doctype"]
GetParty --> DeterminePOS["Determine Place of Supply"]
DeterminePOS --> IsOverseas{"Overseas?"}
IsOverseas --> |Yes| SetExportPOS["Set POS = Other Countries"]
IsOverseas --> |No| HasGSTIN{"Has GSTIN?"}
HasGSTIN --> |Yes| UseGSTINPOS["Use GSTIN state"]
HasGSTIN --> |No| UseAddressPOS["Use address state"]
UseGSTINPOS --> CompareState["Compare POS state with company GSTIN state"]
UseAddressPOS --> CompareState
SetExportPOS --> CompareState
CompareState --> IsInter{"Is Inter-State?"}
IsInter --> |Yes| ApplyIGST["Apply IGST"]
IsInter --> |No| ApplyCGSTSGST["Apply CGST + SGST"]
ApplyIGST --> End(["End"])
ApplyCGSTSGST --> End
```

**Diagram sources**
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py#L402-L484)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L615-L627)

**Section sources**
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py#L402-L484)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L615-L627)

### GST Account Mapping System
- Mapping by transaction type (sales vs purchase), intra/inter-state, and reverse charge:
  - Output: CGST + SGST for intra-state; IGST for inter-state
  - Input: CGST + SGST for intra-state; IGST for inter-state; RCM variants
- Validation ensures only valid GST accounts are used for the transaction type and POS.

```mermaid
flowchart TD
A["Company + Transaction Type"] --> B{"Reverse Charge?"}
B --> |No| C{"Intra-State?"}
B --> |Yes| D["Add RCM account types"]
C --> |Yes| E["Use CGST + SGST"]
C --> |No| F["Use IGST"]
D --> G["Filter applicable accounts"]
E --> H["Validate accounts"]
F --> H
G --> H
```

**Diagram sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L212-L275)
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py#L509-L586)

**Section sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L212-L275)
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py#L509-L586)

### ITC Management and Validation
- Eligibility checks:
  - Restrictions due to POS rules
  - Composition dealers and unregistered suppliers
- Proportionate reversal:
  - Computes ineligible tax per item and per tax component
  - Adjusts valuation rates and books reversing entries
- Default GST expense account required for reversing entries

```mermaid
sequenceDiagram
participant Doc as "Document"
participant II as "IneligibleITC"
participant GL as "GL Entries"
Doc->>II : update_valuation_rate()
II->>II : update_item_ineligibility()
II->>II : update_ineligible_taxes(item)
II->>Doc : item._ineligible_tax_amount
II->>GL : reverse_input_taxes_entry(item)
GL-->>Doc : updated GL entries
```

**Diagram sources**
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L75-L140)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L106-L139)

**Section sources**
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L75-L140)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L106-L139)

### Tax Calculation Workflow: Item-Level to Document-Level
- Item-level:
  - Base net amount becomes taxable value
  - Proportional charges allocated based on total value (net or qty)
  - Item-wise tax computed using mapped rates and charge type
- Document-level:
  - Sum of item tax amounts equals total taxes
  - Grand total = total taxable value + total taxes
  - Rounding handled for GST accounts

```mermaid
flowchart TD
Start(["Start"]) --> NetAmt["Set item.taxable_value = base_net_amount"]
NetAmt --> HasCharges{"Has charges?"}
HasCharges --> |No| ComputeTax["Compute tax per item"]
HasCharges --> |Yes| Allocate["Allocate charges proportionally"]
Allocate --> ComputeTax
ComputeTax --> SumTaxes["Sum taxes across items"]
SumTaxes --> RoundOff{"Is round-off account?"}
RoundOff --> |Yes| Round["Round to whole number"]
RoundOff --> |No| Keep["Keep precise amount"]
Round --> GrandTotal["Grand Total = Sum of taxable values + Sum of taxes"]
Keep --> GrandTotal
GrandTotal --> End(["End"])
```

**Diagram sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L69-L133)
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L155-L183)

**Section sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L69-L133)
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L155-L183)

### Proportional Charges Allocation and Tax Rounding
- Charges allocation:
  - Uses total charges minus TDS and previous row totals
  - Allocates proportionally based on base_net_total or qty
- Rounding:
  - Applies rounding for GST accounts via round-off accounts
  - Ensures final tax amount matches computed value

**Section sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L69-L133)
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L162-L176)

### Reverse Charge and Payment Entry Reversal
- Reverse charge:
  - Validates positive/negative amounts depending on RCM vs non-RCM
  - Ensures net GST plus reverse charge equals zero
- Payment entry:
  - Calculates proportionate taxes for reference allocations
  - Balances taxes on final allocation

**Section sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L1040-L1104)
- [payment_entry.py](file://india_compliance/gst_india/overrides/payment_entry.py#L276-L310)

### Practical Examples

- Example 1: Multi-state sale (intra-state)
  - POS: Maharashtra (27)
  - Company GSTIN: 27... (same state)
  - Apply: CGST + SGST
  - ITC: Available if conditions met

- Example 2: Multi-state sale (inter-state)
  - POS: Gujarat (24)
  - Company GSTIN: 27...
  - Apply: IGST
  - ITC: Available depending on recipient’s eligibility

- Example 3: ITC eligibility validation
  - Scenario: Supplies to unregistered person in another state
  - Rule: ITC restricted due to POS rules
  - Outcome: Ineligible ITC computed and reversed

- Example 4: Proportional charges allocation
  - Document has shipping and discount
  - Charges allocated proportionally to items based on base_net_amount or qty

**Section sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L615-L627)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L277-L306)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L69-L133)

## Dependency Analysis
- Taxes Controller depends on:
  - Item-level tax templates and account mappings
  - Place of supply and inter-state determination
  - GST account lists and validation
- ITC module depends on:
  - Document taxes and tax components
  - Company settings for default GST expense account
  - Valuation and warehouse/account mappings

```mermaid
graph TB
TC["CustomTaxController"] --> TR["Place of Supply & Inter-State"]
TC --> UT["GST Account Retrieval"]
TR --> CT["Constants & State Mappings"]
II["Ineligible ITC"] --> TR
II --> UT
PE["Payment Entry"] --> UT
```

**Diagram sources**
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L104-L275)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L212-L275)
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py#L487-L646)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L18-L140)
- [payment_entry.py](file://india_compliance/gst_india/overrides/payment_entry.py#L276-L310)

**Section sources**
- [taxes_controller.py](file://india_compliance/gst_india/utils/taxes_controller.py#L104-L275)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L212-L275)
- [__init__.py](file://india_compliance/gst_india/utils/__init__.py#L487-L646)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L18-L140)
- [payment_entry.py](file://india_compliance/gst_india/overrides/payment_entry.py#L276-L310)

## Performance Considerations
- Efficient item-wise tax rate mapping using pre-fetched templates and tax accounts
- Minimal database queries for GST account retrieval and state mappings
- Rounding only for GST accounts to reduce floating-point drift
- Batch processing of items and taxes to avoid repeated computations

## Troubleshooting Guide
Common issues and resolutions:
- Incorrect tax rates
  - Symptom: Item GST details mismatch
  - Resolution: Recompute using mapped rates and charge type; validate differences within allowable tolerance

- Missing place of supply
  - Symptom: Validation failure for POS
  - Resolution: Ensure party address/GSTIN is set; POS derived from GSTIN or address state

- Validation failures
  - Symptom: Invalid GST accounts or charge types
  - Resolution: Use only valid accounts for transaction type and POS; ensure charge type compliance for cess/non-advol

- ITC restriction due to POS
  - Symptom: Ineligible ITC flagged
  - Resolution: Confirm recipient category and POS; adjust valuation rates and reverse entries accordingly

- Reverse charge mismatch
  - Symptom: Non-zero net GST + reverse charge
  - Resolution: Ensure correct sign and amounts for RCM rows; verify total equals zero

**Section sources**
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L1338-L1370)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L581-L613)
- [transaction.py](file://india_compliance/gst_india/overrides/transaction.py#L1040-L1104)
- [ineligible_itc.py](file://india_compliance/gst_india/overrides/ineligible_itc.py#L277-L306)

## Conclusion
The Tax Calculation Engine integrates place of supply determination, GST account mapping, and robust tax computation with proportional charges and rounding. It enforces ITC eligibility and validates reverse charge logic, ensuring accurate tax reporting and compliance across intra-state and inter-state transactions.

## Appendices

### GST Account Types and Fields
- Account types: CGST, SGST, IGST, CESS, CESS Non-Advol
- Tax types: cgst, sgst, igst, cess, cess_non_advol
- Constants define state mappings and valid UOMs

**Section sources**
- [constants/__init__.py](file://india_compliance/gst_india/constants/__init__.py#L9-L23)
- [constants/__init__.py](file://india_compliance/gst_india/constants/__init__.py#L66-L105)

### Report-Level Apportionment and Progressive Tax Amounts
- Reports allocate additional charges proportionally and compute progressive tax amounts to minimize rounding errors
- Handles before/after GST tax rows and TDS adjustments

**Section sources**
- [gst_account_wise_summary.py](file://india_compliance/gst_india/report/gst_account_wise_summary/gst_account_wise_summary.py#L81-L158)
- [transaction_data.py](file://india_compliance/gst_india/utils/transaction_data.py#L386-L426)