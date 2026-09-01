
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

export function get(doctype, name) {
    const record = all(doctype).find((r) => r.name === name);

    if (!record) {
        throw new Error(
            `No ${doctype} named "${name}" in ${RECORDS_PATH}. ` +
                `Has the record been renamed, or does before_tests need re-running?`,
        );
    }

    return record;
}

export function find(doctype, property, value) {
    return all(doctype).filter((r) => r[property] === value);
}

export function state_code(gstin) {
    return gstin.slice(0, 2);
}

/**
 * Matches a `place_of_supply` value ("24-Gujarat") against a GSTIN's state, s
 */
export function place_of_supply_pattern(gstin) {
    return new RegExp(`^${state_code(gstin)}-`);
}
