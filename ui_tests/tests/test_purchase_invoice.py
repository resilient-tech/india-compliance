import frappe
import pytest

from ui_tests.utils import dismiss_modals
from ui_tests.utils.transaction import (
    fill_items_table,
    verify_autofilled_values,
    verify_taxes_table,
)


class TestPurchaseInvoice:
    @pytest.fixture(scope="class", autouse=True)
    @staticmethod
    def setup(request, site):
        from india_compliance.gst_india.constants import STATE_NUMBERS

        request.cls.company = frappe.get_doc("Company", "_Test Indian Registered Company")
        request.cls.supplier = frappe.get_doc("Supplier", "_Test Registered Supplier")
        request.cls.item = frappe.get_doc("Item", "_Test Trading Goods 1")
        request.cls.state = request.cls.company.gstin[:2]
        request.cls.place_of_supply = next(
            f"{number}-{name}" for name, number in STATE_NUMBERS.items() if number == request.cls.state
        )

    def test_in_state_supplier_gets_cgst_and_sgst(self):
        assert self.supplier.gstin[:2] == self.state

        form = self.form_page("Purchase Invoice")
        form.fill_fields({"supplier": self.supplier.name, "bill_no": "UI-TEST-001"})

        fill_items_table(form, [{"item_code": self.item.name, "qty": 1, "rate": 100}])

        verify_autofilled_values(form, {"place_of_supply": self.place_of_supply})

        form.save()

        assert form.get_status() == "Draft"

        verify_taxes_table(
            form,
            [
                {"account_head": "CGST", "rate": 9},
                {"account_head": "SGST", "rate": 9},
            ],
        )

        # "Expense Head Changed" sits over the Submit button.
        dismiss_modals(form)

        form.submit()

        assert form.get_status() == "Unpaid"
