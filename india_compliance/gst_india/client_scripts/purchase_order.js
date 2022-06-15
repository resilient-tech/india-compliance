{% include "india_compliance/gst_india/client_scripts/transaction.js" %}

DOCTYPE = "Purchase Order";
setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);
validate_overseas_gst_category(DOCTYPE);
