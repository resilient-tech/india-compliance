#!/bin/bash

set -e

# Check for merge conflicts before proceeding
python -m compileall -f "${GITHUB_WORKSPACE}"
if grep -lr --exclude-dir=node_modules "^<<<<<<< " "${GITHUB_WORKSPACE}"
    then echo "Found merge conflicts"
    exit 1
fi

cd ~ || exit

DB="${DB:-mariadb}"

echo "Setting Up System Dependencies..."

sudo apt update

sudo apt remove mysql-server mysql-client
sudo apt install libcups2-dev redis-server mariadb-client
if [ "$DB" == "postgres" ]; then
    sudo apt install postgresql-client
fi

install_whktml() {
    wget -O /tmp/wkhtmltox.deb https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.jammy_amd64.deb
    sudo apt install /tmp/wkhtmltox.deb
}
install_whktml &
wkpid=$!

pip install frappe-bench

FRAPPE_REMOTE=${FRAPPE_REMOTE:-https://github.com/frappe/frappe.git}
FRAPPE_BRANCH=${FRAPPE_BRANCH:-$BRANCH_TO_CLONE}

git clone "$FRAPPE_REMOTE" --branch "$FRAPPE_BRANCH" --depth 1 ~/frappe
bench init --skip-assets --frappe-path ~/frappe --python "$(which python)" frappe-bench

mkdir ~/frappe-bench/sites/test_site

# DB-specific site config
if [ "$DB" == "postgres" ]; then
    site_config="site_config_postgres.json"

    export PGPASSWORD=travis
    psql \
        -h 127.0.0.1 \
        -p 5432 \
        -U postgres \
        -c "ALTER SYSTEM SET synchronous_commit = 'off'" \
        -c "ALTER SYSTEM SET fsync = 'off'" \
        -c "ALTER SYSTEM SET full_page_writes = 'off'" \
        -c "SELECT pg_reload_conf()"
else
    site_config="site_config.json"

    mariadb \
        --host 127.0.0.1 \
        --port 3306 \
        -u root \
        -ptravis \
        -e "SET GLOBAL character_set_server = 'utf8mb4'; SET GLOBAL collation_server = 'utf8mb4_unicode_ci';"
fi

cp -r "${GITHUB_WORKSPACE}/.github/helper/${site_config}" ~/frappe-bench/sites/test_site/site_config.json

cd ~/frappe-bench || exit

sed -i 's/watch:/# watch:/g' Procfile
sed -i 's/schedule:/# schedule:/g' Procfile
sed -i 's/socketio:/# socketio:/g' Procfile
sed -i 's/redis_socketio:/# redis_socketio:/g' Procfile

ERPNEXT_REMOTE=${ERPNEXT_REMOTE:-https://github.com/frappe/erpnext.git}
ERPNEXT_BRANCH=${ERPNEXT_BRANCH:-$BRANCH_TO_CLONE}

bench get-app "$ERPNEXT_REMOTE" --branch "$ERPNEXT_BRANCH" --resolve-deps
bench get-app india_compliance "${GITHUB_WORKSPACE}"
bench setup requirements --dev

wait $wkpid

bench use test_site
bench start &
bench reinstall --yes

bench --verbose install-app india_compliance
bench --site test_site add-to-hosts
