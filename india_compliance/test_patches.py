import frappe
from frappe.tests.utils import FrappeTestCase

from india_compliance.install import POST_INSTALL_PATCHES


class TestPatches(FrappeTestCase):
    def test_post_install_patch_exists(self):
        for patch in POST_INSTALL_PATCHES:
            self.assertTrue(
                frappe.get_attr(
                    f"india_compliance.patches.post_install.{patch}.execute"
                )
            )
