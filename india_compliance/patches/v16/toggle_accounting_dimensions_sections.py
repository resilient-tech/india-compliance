# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from india_compliance.gst_india.setup import toggle_accounting_dimensions_sections


def execute():
    # Existing sites don't re-run `after_install`, so sync the current
    # `enable_accounting_dimensions` setting onto India Compliance doctypes.
    toggle_accounting_dimensions_sections()
