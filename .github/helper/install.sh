#!/bin/bash

set -e

# Check for merge conflicts before proceeding
python -m compileall -f "${GITHUB_WORKSPACE}"
if grep -lr --exclude-dir=node_modules "^<<<<<<< " "${GITHUB_WORKSPACE}"
    then echo "Found merge conflicts"
    exit 1
fi

cd ~ || exit

sudo apt update && sudo apt install redis-server libcups2-dev

pip install frappe-bench

git clone "https://github.com/frappe/frappe" --branch "$BRANCH" --depth 1
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


install_wkhtml() {
    wget -O /tmp/wkhtmltox.tar.xz https://github.com/frappe/wkhtmltopdf/raw/master/wkhtmltox-0.12.3_linux-generic-amd64.tar.xz
    tar -xf /tmp/wkhtmltox.tar.xz -C /tmp
    sudo mv /tmp/wkhtmltox/bin/wkhtmltopdf /usr/local/bin/wkhtmltopdf
    sudo chmod o+x /usr/local/bin/wkhtmltopdf
}
install_wkhtml &

cd ~/frappe-bench || exit

sed -i 's/watch:/# watch:/g' Procfile
sed -i 's/schedule:/# schedule:/g' Procfile
sed -i 's/socketio:/# socketio:/g' Procfile
sed -i 's/redis_socketio:/# redis_socketio:/g' Procfile

bench get-app erpnext --branch "$BRANCH"

bench start &
bench --site test_site reinstall --yes

bench --verbose --site test_site install-app erpnext

bench get-app india_compliance "${GITHUB_WORKSPACE}"
bench --verbose --site test_site install-app india_compliance
bench set-config ic_api_secret "$IC_API_SECRET"
bench show-config