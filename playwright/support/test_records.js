import records from "../../india_compliance/tests/test_records.json";

const RECORDS_PATH = "india_compliance/tests/test_records.json";

const NAME_FIELD = { Item: "item_code" };

function docname(doctype, record) {
    const field = NAME_FIELD[doctype] || `${doctype.toLowerCase().replace(/ /g, "_")}_name`;

    return record.name || record[field];
}

function all(doctype) {
    return (records[doctype] || []).map((r) => ({ ...r, name: docname(doctype, r) }));
}

export function getRecord(doctype, name) {
    const record = all(doctype).find((r) => r.name === name);

    if (!record) {
        throw new Error(
            `No ${doctype} named "${name}" in ${RECORDS_PATH}. ` +
                "Has the record been renamed, or does before_tests need re-running?",
        );
    }

    return record;
}

export function findRecords(doctype, property, value) {
    return all(doctype).filter((r) => r[property] === value);
}

export function stateCode(gstin) {
    return gstin.slice(0, 2);
}

/** The state code half of a `place_of_supply` ("24-Gujarat" -> "24"). */
export function placeOfSupplyState(placeOfSupply) {
    return (placeOfSupply || "").split("-")[0];
}
