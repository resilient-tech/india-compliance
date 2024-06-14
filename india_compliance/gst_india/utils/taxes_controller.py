import json

import frappe


# common taxes controller class
class TaxesController:
    # TODO:
    @frappe.whitelist()
    def set_item_wise_tax_rates(self, item_name=None, tax_name=None):
        items, taxes = self.get_rows_to_update(item_name, tax_name)
        tax_accounts = {tax.account_head for tax in taxes}

        if not tax_accounts:
            return

        tax_templates = {item.item_tax_template for item in items}
        item_tax_map = self.get_item_tax_map(tax_templates, tax_accounts)

        for tax in taxes:

            item_wise_tax_rates = (
                json.loads(tax.item_wise_tax_rates) if tax.item_wise_tax_rates else {}
            )

            for item in items:
                key = (item.item_tax_template, tax.account_head)
                item_wise_tax_rates[item.name] = item_tax_map.get(key, tax.rate)

            tax.item_wise_tax_rates = json.dumps(item_wise_tax_rates)

    def get_item_tax_map(self, tax_templates, tax_accounts):
        """
        Parameters:
            tax_templates (list): List of item tax templates used in the items
            tax_accounts (list): List of tax accounts used in the taxes

        Returns:
            dict: A map of item_tax_template, tax_account and tax_rate

        Sample Output:
            {
                ('GST 18%', 'IGST - TC'): 18.0
                ('GST 28%', 'IGST - TC'): 28.0
            }
        """

        if not tax_templates:
            return {}

        tax_rates = frappe.get_all(
            "Item Tax Template Detail",
            fields=("parent", "tax_type", "tax_rate"),
            filters={
                "parent": ("in", tax_templates),
                "tax_type": ("in", tax_accounts),
            },
        )

        return {(d.parent, d.tax_type): d.tax_rate for d in tax_rates}

    def get_rows_to_update(self, item_name=None, tax_name=None):
        """
        Returns items and taxes to update based on item_name and tax_name passed.
        If item_name and tax_name are not passed, all items and taxes are returned.
        """

        items = self.get("items", {"name": item_name}) if item_name else self.items
        taxes = self.get("taxes", {"name": tax_name}) if tax_name else self.taxes

        return items, taxes
