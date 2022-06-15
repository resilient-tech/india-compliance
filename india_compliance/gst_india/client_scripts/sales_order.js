{% include "india_compliance/gst_india/client_scripts/transaction.js" %}

const DOCTYPE = "Sales Order";
setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);
validate_overseas_gst_category(DOCTYPE);
