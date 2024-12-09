# Copyright (c) 2022, Resilient Tech and Contributors
# See license.txt

# import frappe
<<<<<<< HEAD
from frappe.tests.utils import FrappeTestCase


class TesteInvoiceLog(FrappeTestCase):
=======
from frappe.tests import IntegrationTestCase


class TesteInvoiceLog(IntegrationTestCase):
>>>>>>> c95f60da (fix: use bulk insert to ignore validations)
    pass
