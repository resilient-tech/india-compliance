#!/bin/bash

set -e

# Check for merge conflicts before proceeding
python -m compileall -f "${GITHUB_WORKSPACE}"
if grep -lr --exclude-dir=node_modules "^<<<<<<< " "${GITHUB_WORKSPACE}"
    then echo "Found merge conflicts"
    exit 1
fi

cd ~ || exit

sudo apt update && sudo apt install redis-server

pip install frappe-bench

git clone "https://github.com/frappe/frappe" --branch "$BRANCH_TO_CLONE" --depth 1
bench init --skip-assets --frappe-path ~/frappe --python "$(which python)" frappe-bench

mkdir ~/frappe-bench/sites/test_site

cp -r "${GITHUB_WORKSPACE}/.github/helper/site_config.json" ~/frappe-bench/sites/test_site/


mysql --host 127.0.0.1 --port 3306 -u root -e "
SET GLOBAL character_set_server = 'utf8mb4';
SET GLOBAL collation_server = 'utf8mb4_unicode_ci';

CREATE USER 'test_resilient'@'localhost' IDENTIFIED BY 'test_resilient';
CREATE DATABASE test_resilient;
GRANT ALL PRIVILEGES ON \`test_resilient\`.* TO 'test_resilient'@'localhost';

UPDATE mysql.user SET Password=PASSWORD('travis') WHERE User='root';
FLUSH PRIVILEGES;
"

wget https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox_0.12.6-1.focal_amd64.deb
sudo apt install ./wkhtmltox_0.12.6-1.focal_amd64.deb

cd ~/frappe-bench || exit

sed -i 's/watch:/# watch:/g' Procfile
sed -i 's/schedule:/# schedule:/g' Procfile
sed -i 's/socketio:/# socketio:/g' Procfile
sed -i 's/redis_socketio:/# redis_socketio:/g' Procfile

bench get-app erpnext --branch "$BRANCH_TO_CLONE" --resolve-deps
bench get-app india_compliance "${GITHUB_WORKSPACE}"
bench setup requirements --dev

bench use test_site
bench start &
bench reinstall --yes

bench --verbose install-app india_compliance
