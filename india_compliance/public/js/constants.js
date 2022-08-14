// Copied from india_compliance/gst_india/constants
const NORMAL = "^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z1-9ABD-J]{1}[0-9A-Z]{1}$";
const GOVT_DEPTID = "^[0-9]{2}[A-Z]{4}[0-9]{5}[A-Z]{1}[0-9]{1}[Z]{1}[0-9]{1}$";
export const REGISTERED_REGEX = new RegExp([NORMAL, GOVT_DEPTID].join("|"));

const NRI_ID = "^[0-9]{4}[A-Z]{3}[0-9]{5}[N][R][0-9A-Z]{1}$";
const OIDAR = "^[9][9][0-9]{2}[A-Z]{3}[0-9]{5}[O][S][0-9A-Z]{1}$";
export const OVERSEAS_REGEX = new RegExp([NRI_ID, OIDAR].join("|"));

const UNBODY = "^[0-9]{4}[A-Z]{3}[0-9]{5}[UO]{1}[N][A-Z0-9]{1}$";
export const UNBODY_REGEX = new RegExp(UNBODY);
export const TDS_REGEX =
    /^[0-9]{2}[A-Z]{4}[A-Z0-9]{1}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[D][0-9A-Z]$/;

// TDS is covered in Normal hence not included in the regex
export const GSTIN_REGEX = new RegExp(
    [NORMAL, GOVT_DEPTID, NRI_ID, OIDAR, UNBODY].join("|")
);
