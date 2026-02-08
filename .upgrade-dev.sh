#!/bin/bash
source .env
set -x

click-odoo-update -c $ODOO_CONFIG -d $ODOO_DB --ignore-core-addons $@
notify-send -t 5000 -u low 'Upgrade finished' 'Upgrade finished'

