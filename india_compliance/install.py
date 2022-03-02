import frappe

from .gst_india.setup import after_install as setup_gst_india
from .income_tax_india.setup import after_install as setup_income_tax_india


def after_install():
    setup_income_tax_india()
    setup_gst_india()
