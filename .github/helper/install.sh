#!/bin/bash

set -e

# Check for merge conflicts before proceeding
python -m compileall -f "${GITHUB_WORKSPACE}"
if grep -lr --exclude-dir=node_modules "^<<<<<<< " "${GITHUB_WORKSPACE}"
    then echo "Found merge conflicts"
    exit 1
fi

cd ~ || exit

echo "Setting Up System Dependencies..."

sudo apt update

sudo apt remove mysql-server mysql-client
sudo apt install libcups2-dev redis-server mariadb-client-10.6

install_whktml() {
    if [ "$(lsb_release -rs)" = "22.04" ]; then
        wget -O /tmp/wkhtmltox.deb https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.jammy_amd64.deb
        sudo apt install /tmp/wkhtmltox.deb
    else
        echo "Please update this script to support wkhtmltopdf for $(lsb_release -ds)"
        exit 1
    fi
}
install_whktml &
wkpid=$!

pip install frappe-bench

git clone "https://github.com/frappe/frappe" --branch "$BRANCH_TO_CLONE" --depth 1
bench init --skip-assets --frappe-path ~/frappe --python "$(which python)" frappe-bench

mkdir ~/frappe-bench/sites/test_site

cp -r "${GITHUB_WORKSPACE}/.github/helper/site_config.json" ~/frappe-bench/sites/test_site/


mariadb --host 127.0.0.1 --port 3306 -u root -ptravis -e "
SET GLOBAL character_set_server = 'utf8mb4';
SET GLOBAL collation_server = 'utf8mb4_unicode_ci';

CREATE USER 'test_resilient'@'localhost' IDENTIFIED BY 'test_resilient';
CREATE DATABASE test_resilient;
GRANT ALL PRIVILEGES ON \`test_resilient\`.* TO 'test_resilient'@'localhost';

FLUSH PRIVILEGES;
"

cd ~/frappe-bench || exit

sed -i 's/watch:/# watch:/g' Procfile
sed -i 's/schedule:/# schedule:/g' Procfile
sed -i 's/socketio:/# socketio:/g' Procfile
sed -i 's/redis_socketio:/# redis_socketio:/g' Procfile

bench get-app erpnext --branch "$BRANCH_TO_CLONE" --resolve-deps
bench get-app india_compliance "${GITHUB_WORKSPACE}"
bench setup requirements --dev

wait $wkpid

bench use test_site
bench start &
bench reinstall --yes

bench --verbose install-app india_compliance
bench --site test_site add-to-hosts

