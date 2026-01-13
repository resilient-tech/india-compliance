
import frappe
import os
from frappe.utils import get_bench_path


def main():
    # Initialize frappe for the site
    bench_path = get_bench_path()
    sites_path = os.path.join(bench_path, "sites")
    frappe.init(site="test_site", sites_path=sites_path)
    frappe.connect()

    from india_compliance.tests import setup_post_install_test_data

    print("Running setup for India Company...")
    setup_post_install_test_data()
    print("Setup complete.")


if __name__ == "__main__":
    main()
