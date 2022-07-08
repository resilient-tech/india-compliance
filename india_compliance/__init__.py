from __future__ import unicode_literals

import importlib
import os

import frappe

__version__ = "0.0.1"

app_name = "india_compliance"
patches_loaded = False


def load_monkey_patches():
    """
    Loads all modules present in monkey_patches to override some logic
    in Frappe / ERPNext. Returns if patches have already been loaded earlier.
    """
    global patches_loaded

    if patches_loaded or app_name not in frappe.get_installed_apps():
        return

    patches_loaded = True

    for module_name in os.listdir(frappe.get_app_path(app_name, "monkey_patches")):
        if not module_name.endswith(".py") or module_name == "__init__.py":
            continue

        importlib.import_module(f"{app_name}.monkey_patches." + module_name[:-3])


old_get_hooks = frappe.get_hooks


def get_hooks(*args, **kwargs):
    load_monkey_patches()
    return old_get_hooks(*args, **kwargs)


frappe.get_hooks = get_hooks

old_connect = frappe.connect


def connect(*args, **kwargs):
    """
    Patches frappe.connect to load monkey patches once a connection is
    established with the database.
    """

    old_connect(*args, **kwargs)
    load_monkey_patches()


frappe.connect = connect
