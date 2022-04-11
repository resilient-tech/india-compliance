{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Customer";

validate_pan(DOCTYPE);
validate_gstin(DOCTYPE);
update_gstin_in_other_documents(DOCTYPE);
overseas_gst_category_alert(DOCTYPE);
