export const getReadableNumber = function (num, precision = 2) {
    return num.toLocaleString(undefined, {
        minimumFractionDigits: precision,
        maximumFractionDigits: precision,
    });
};
