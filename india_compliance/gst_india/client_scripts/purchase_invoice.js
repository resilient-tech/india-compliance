{% include "india_compliance/gst_india/client_scripts/taxes.js" %}
{% include "india_compliance/gst_india/client_scripts/invoice.js" %}


const DOCTYPE = "Purchase Invoice";

setup_auto_gst_taxation(DOCTYPE);
get_gst_category(DOCTYPE);
update_export_type(DOCTYPE);