import frappe
from frappe.modules.patch_handler import get_patches_from_app
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

    def test_patches_exists(self):
        patches = get_patches_from_app("india_compliance")

        for patch in patches:
            if patch.startswith("execute:"):
                import_path = patch.split("execute:")[1]

                if not import_path.startswith("from"):
                    continue

                components = import_path.split("from")[1].split()
                module = components[0]
                function_name = components[2].replace(";", "").replace(",", "")
                patch_path = module + "." + function_name
            else:
                patch_path = f"{patch.split(maxsplit=1)[0]}.execute"

            frappe.get_attr(patch_path)
