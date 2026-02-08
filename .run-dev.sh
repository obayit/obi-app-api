#!/bin/bash
source .env
set -ex
# --log-level error
odoo --dev=all -c $ODOO_CONFIG -d $ODOO_DB $@

