{% include "india_compliance/gst_india/client_scripts/taxes.js" %}

erpnext.setup_auto_gst_taxation('Sales Order');
validate_hsn_code('Sales Order');
