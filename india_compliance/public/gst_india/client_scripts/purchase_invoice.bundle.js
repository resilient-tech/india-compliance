import { setup_auto_gst_taxation, fetch_gst_category } from "./taxes";
import { update_export_type } from "./invoice";

const DOCTYPE = "Purchase Invoice";

setup_auto_gst_taxation(DOCTYPE);
fetch_gst_category(DOCTYPE);
update_export_type(DOCTYPE);
