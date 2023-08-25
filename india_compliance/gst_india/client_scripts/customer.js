{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Customer";

validate_pan(DOCTYPE);
validate_gstin(DOCTYPE);
update_gstin_in_other_documents(DOCTYPE);
show_overseas_disabled_warning(DOCTYPE);
set_gstin_options_and_status(DOCTYPE);
set_gst_category(DOCTYPE);
