import { validate_pan, validate_gstin, update_gstin_in_other_documents } from "./party";

const DOCTYPE = "Customer";

validate_pan(DOCTYPE);
validate_gstin(DOCTYPE);
update_gstin_in_other_documents(DOCTYPE);
