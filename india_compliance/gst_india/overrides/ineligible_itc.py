from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form
from erpnext.assets.doctype.asset.asset import (
    get_asset_account,
    is_cwip_accounting_enabled,
)
from erpnext.stock import get_warehouse_account_map

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
)


class IneligibleITC:
    def __init__(self, doc):
        self.doc = doc

        self.warehouse_account_map = get_warehouse_account_map(doc.company)
        self.company = frappe.get_cached_doc("Company", doc.company)
        self.is_perpetual = self.company.enable_perpetual_inventory
        self.cost_center = doc.cost_center or self.company.cost_center

        self.dr_or_cr = "credit" if doc.get("is_return") else "debit"
        self.cr_or_dr = "debit" if doc.get("is_return") else "credit"

    def update_valuation_rate(self):
        """
        Updates Valuation Rate for each item row

        - Only updates if its a stock item or fixed asset
        - No updates for expense items
        """

        self.update_item_ineligibility()

        if not self.doc.get("_has_ineligible_itc_items"):
            return

        for item in self.doc.items:
            if not item.get("_ineligible_tax_amount"):
                continue

            if item.get("_is_stock_item") or item.get("is_fixed_asset"):
                ineligible_tax_amount = item._ineligible_tax_amount
                if self.doc.get("is_return"):
                    ineligible_tax_amount = -ineligible_tax_amount

                self.update_item_valuation_rate(item, ineligible_tax_amount)

    def update_gl_entries(self, gl_entries):
        self.gl_entries = gl_entries

        self.update_item_ineligibility()

        if not self.doc.get("_has_ineligible_itc_items"):
            return gl_entries

        if not self.company.default_gst_expense_account:
            frappe.throw(
                _(
                    "Please set <strong>Default GST Expense Account</strong> in Company {0}"
                ).format(get_link_to_form("Company", self.company.name))
            )

        for item in self.doc.items:
            if not item.get("_ineligible_tax_amount"):
                continue

            self.update_item_gl_entries(item)

    def update_item_ineligibility(self):
        self.doc._has_ineligible_itc_items = False
        stock_items = self.doc.get_stock_items()

        self.tax_account_dict = {
            row.gst_tax_type: row.account_head
            for row in self.doc.taxes
            if row.gst_tax_type
        }

        if not self.tax_account_dict:
            return

        for item in self.doc.items:
            if (
                not self.is_eligibility_restricted_due_to_pos()
                and not item.is_ineligible_for_itc
            ):
                continue

            self.update_ineligible_taxes(item)

            if item._ineligible_tax_amount:
                self.doc._has_ineligible_itc_items = True

            if item.item_code in stock_items and self.is_perpetual:
                item._is_stock_item = True

    def update_item_gl_entries(self, item):
        return

    def reverse_input_taxes_entry(self, item):
        """
        Reverse Proportionate ITC for each tax component
        and book GST Expense for same

        eg: GST Expense Dr 100
            Input CGST Cr 50
            Input SGST Cr 50
        """
        # Auto handled for returns as -ve amount
        ineligible_item_tax_amount = item.get("_ineligible_tax_amount", 0)
        self.gl_entries.append(
            self.doc.get_gl_dict(
                {
                    "account": self.company.default_gst_expense_account,
                    self.dr_or_cr: ineligible_item_tax_amount,
                    f"{self.dr_or_cr}_in_account_currency": ineligible_item_tax_amount,
                    "cost_center": self.cost_center,
                }
            )
        )

        for account, amount in item.get("_ineligible_taxes", {}).items():
            self.gl_entries.append(
                self.doc.get_gl_dict(
                    {
                        "account": account,
                        self.cr_or_dr: amount,
                        f"{self.cr_or_dr}_in_account_currency": amount,
                        "cost_center": self.cost_center,
                    }
                )
            )

    def make_gst_expense_entry(self, item):
        """
        Reverse GST Expense and transfer it to respective
        Asset / Stock Account / Expense Account

        eg: Fixed Asset Dr 100
            GST Expense Cr 100
        """

        ineligible_item_tax_amount = item.get("_ineligible_tax_amount", 0)
        self.gl_entries.append(
            self.doc.get_gl_dict(
                {
                    "account": self.company.default_gst_expense_account,
                    self.cr_or_dr: ineligible_item_tax_amount,
                    f"{self.cr_or_dr}_in_account_currency": ineligible_item_tax_amount,
                    "cost_center": self.cost_center,
                }
            )
        )

        if not self.is_debit_entry_required(item):
            return

        expense_account = self.get_item_expense_account(item)
        if not expense_account:
            return

        against_account = self.get_against_account(item)
        remarks = item.get("_remarks")

        self.gl_entries.append(
            self.doc.get_gl_dict(
                args={
                    "account": expense_account,
                    self.dr_or_cr: ineligible_item_tax_amount,
                    f"{self.dr_or_cr}_in_account_currency": ineligible_item_tax_amount,
                    "cost_center": item.cost_center or self.cost_center,
                    "against": against_account,
                    "remarks": remarks,
                },
                item=item,
            )
        )

    def reverse_stock_adjustment_entry(self, item):
        """
        Stock Adjustment Entry for returned items is booked in ERPNext
        Steps as Followed by ERPNext:
        - Identify Stock Value for each item from Purchase Invoice
        - Book SLE accordingly as per original Purchase Invoice
        - Identify Stock Value difference and book it against default expense account

        Reference:
        - Purchase Invoice: erpnext.accounts.doctype.purchase_invoice.purchase_invoice.PurchaseInvoice.make_stock_adjustment_entry
        - Purchase Receipt: erpnext.stock.doctype.purchase_receipt.purchase_receipt.PurchaseReceipt.make_item_gl_entries.make_divisional_loss_gl_entry

        This method reverses the Stock Adjustment Entry
        """
        stock_account = self.get_item_expense_account(item)
        cogs_account = (
            self.company.default_expense_account
            or self.company.stock_received_but_not_billed
        )

        ineligible_item_tax_amount = item.get("_ineligible_tax_amount", 0)

        for entry in self.gl_entries:
            if (
                entry.get("account") != stock_account
                or entry.get("cost_center") != item.cost_center
            ):
                continue

            entry[self.dr_or_cr] -= ineligible_item_tax_amount
            entry[f"{self.dr_or_cr}_in_account_currency"] -= ineligible_item_tax_amount
            break

        else:
            # FALLBACK: If Stock Account not found in GL Entries
            self.gl_entries.append(
                self.doc.get_gl_dict(
                    {
                        "account": stock_account,
                        self.cr_or_dr: ineligible_item_tax_amount,
                        f"{self.cr_or_dr}_in_account_currency": ineligible_item_tax_amount,
                        "cost_center": item.cost_center or self.cost_center,
                        "remarks": item.get("_remarks"),
                    }
                )
            )

        for entry in self.gl_entries:
            if (
                entry.get("account") != cogs_account
                or entry.get("cost_center") != item.cost_center
            ):
                continue

            entry[self.dr_or_cr] += ineligible_item_tax_amount
            entry[f"{self.dr_or_cr}_in_account_currency"] += ineligible_item_tax_amount
            break

        else:
            # FALLBACK: If COGS Account not found in GL Entries
            self.gl_entries.append(
                self.doc.get_gl_dict(
                    {
                        "account": cogs_account,
                        self.dr_or_cr: ineligible_item_tax_amount,
                        f"{self.dr_or_cr}_in_account_currency": ineligible_item_tax_amount,
                        "cost_center": item.cost_center or self.cost_center,
                        "against": stock_account,
                        "remarks": item.get("_remarks"),
                    }
                )
            )

    def get_item_expense_account(self, item):
        if item.get("is_fixed_asset"):
            expense_account = _get_asset_account(item.asset_category, self.doc.company)
            item.expense_account = expense_account
            self.update_asset_valuation_rate(item)

        elif item.get("_is_stock_item") and self.warehouse_account_map.get(
            item.warehouse
        ):
            expense_account = self.warehouse_account_map[item.warehouse]["account"]

        else:
            expense_account = item.expense_account

        return expense_account

    def get_against_account(self, item):
        return

    def update_ineligible_taxes(self, item):
        """
        Returns proportionate Ineligible ITC for each tax component

        :param item: Item Row
        :return: dict

        Example:
        {
            "Input IGST - FC": 100,
            "Input CGST - FC": 50,
            "Input SGST - FC": 50,
        }
        """
        ineligible_taxes = defaultdict(float)
        ineligible_tax_amount = 0

        for tax_type in GST_TAX_TYPES:
            tax_amount = abs(flt(item.get(f"{tax_type}_amount")))
            tax_account = self.tax_account_dict.get(tax_type)

            if not tax_amount:
                continue

            ineligible_taxes[tax_account] += tax_amount
            ineligible_tax_amount += tax_amount

        item._ineligible_taxes = ineligible_taxes
        item._ineligible_tax_amount = ineligible_tax_amount

    def update_item_valuation_rate(self, item, ineligible_tax_amount):
        item.valuation_rate += flt(ineligible_tax_amount / item.stock_qty, 2)

    def is_debit_entry_required(self, item):
        return True

    def update_asset_valuation_rate(self, item):
        frappe.db.set_value(
            "Asset",
            {
                "item_code": item.item_code,
                frappe.scrub(self.doc.doctype): self.doc.name,
            },
            {
                "gross_purchase_amount": flt(item.valuation_rate),
                "purchase_amount": flt(item.valuation_rate),
            },
        )

    def is_eligibility_restricted_due_to_pos(self):
        return self.doc.get("ineligibility_reason") == "ITC restricted due to PoS rules"


class PurchaseReceipt(IneligibleITC):

    def __init__(self, doc):
        doc.run_method("onload")
        super().__init__(doc)

    def update_valuation_rate(self):
        for item in self.doc.items:
            item._remarks = self.doc.get("remarks") or _(
                "Accounting Entry for {0}"
            ).format("Asset" if item.is_fixed_asset else "Stock")

        super().update_valuation_rate()

    def update_item_gl_entries(self, item):
        if (item.get("_is_stock_item")) or item.get("is_fixed_asset"):
            self.make_gst_expense_entry(item)

        if item.get("_is_stock_item"):
            self.reverse_stock_adjustment_entry(item)

    def get_against_account(self, item):
        if item.is_fixed_asset:
            return self.doc.get_company_default("asset_received_but_not_billed")

        elif item.get("_is_stock_item"):
            return self.doc.get_company_default("stock_received_but_not_billed")


class PurchaseInvoice(IneligibleITC):

    def update_valuation_rate(self):
        for item in self.doc.items:
            item._remarks = self.doc.get("remarks") or _(
                "Accounting Entry for {0}"
            ).format("Asset" if item.is_fixed_asset else "Stock")

        super().update_valuation_rate()

    def update_item_gl_entries(self, item):
        if self.doc.update_stock or self.is_expense_item(item):
            self.make_gst_expense_entry(item)

        self.reverse_input_taxes_entry(item)

    def is_debit_entry_required(self, item):
        # For Stock Entry / Fixed Asset in PI, Additional Debit is accounted automatically from valuation rates
        return self.is_expense_item(item)

    def is_expense_item(self, item):
        """
        Returns False if item is Stock Item or Fixed Asset
        Else returns True

        :param item: Item Row
        :return: bool
        """
        if item.get("is_fixed_asset"):
            return False

        if item.get("_is_stock_item"):
            return False

        account_root = frappe.db.get_value("Account", item.expense_account, "root_type")
        if account_root in ["Asset", "Liability", "Equity"]:
            return False

        return True


class BillOfEntry(IneligibleITC):
    def update_valuation_rate(self):
        # Update fixed assets
        asset_items = self.doc.get_asset_items()
        expense_account = frappe.db.get_values(
            "Purchase Invoice Item",
            {"parent": self.doc.purchase_invoice},
            ["expense_account", "name"],
            as_dict=True,
        )
        expense_account = {d.name: d.expense_account for d in expense_account}

        for item in self.doc.items:
            if item.item_code in asset_items:
                item.is_fixed_asset = True

            if item.pi_detail in expense_account:
                item.expense_account = expense_account[item.pi_detail]

        super().update_valuation_rate()

    def update_item_valuation_rate(self, item, ineligible_tax_amount):
        item.valuation_rate = ineligible_tax_amount

    def update_asset_valuation_rate(self, item):
        return

    def update_item_gl_entries(self, item):
        if not ((item.get("_is_stock_item")) or item.get("is_fixed_asset")):
            self.make_gst_expense_entry(item)

        self.reverse_input_taxes_entry(item)

    def update_landed_cost_voucher(self, landed_cost_voucher):
        self.update_valuation_rate()
        boe_items = frappe._dict({item.name: item for item in self.doc.items})
        total_gst_expense = 0

        for item in landed_cost_voucher.items:
            if item.get("boe_detail") not in boe_items:
                continue

            gst_expense = boe_items[item.boe_detail].get("valuation_rate", 0)
            if not gst_expense:
                continue

            total_gst_expense += gst_expense
            item.applicable_charges += gst_expense / item.qty

        if total_gst_expense == 0:
            return

        landed_cost_voucher.append(
            "taxes",
            {
                "expense_account": self.company.default_gst_expense_account,
                "description": "Customs Duty",
                "amount": total_gst_expense,
            },
        )

    def is_eligibility_restricted_due_to_pos(self):
        return False


DOCTYPE_MAPPING = {
    "Purchase Invoice": PurchaseInvoice,
    "Purchase Receipt": PurchaseReceipt,
    "Bill of Entry": BillOfEntry,
}


def update_valuation_rate(doc, method=None):
    if doc.get("is_opening") == "Yes" or not is_indian_registered_company(doc):
        return

    if doc.doctype in DOCTYPE_MAPPING:
        DOCTYPE_MAPPING[doc.doctype](doc).update_valuation_rate()


def update_regional_gl_entries(gl_entries, doc):
    if doc.get("is_opening") == "Yes" or not is_indian_registered_company(doc):
        return gl_entries

    if doc.doctype in DOCTYPE_MAPPING:
        DOCTYPE_MAPPING[doc.doctype](doc).update_gl_entries(gl_entries)

    return gl_entries


def update_landed_cost_voucher_for_gst_expense(source, target):
    BillOfEntry(source).update_landed_cost_voucher(target)


def _get_asset_account(asset_category, company):
    fieldname = "fixed_asset_account"
    if is_cwip_accounting_enabled(asset_category):
        fieldname = "capital_work_in_progress_account"

    return get_asset_account(fieldname, asset_category=asset_category, company=company)
