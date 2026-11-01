# Copyright 2026 Alda Hotels
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Alda User Roles",
    "summary": "Restricted user roles for Alda Hotels: support team (SMT)",
    "version": "16.0.1.0.0",
    "category": "PMS",
    "author": "Alda Hotels",
    "website": "https://github.com/aldahotels/aldamodules",
    "license": "AGPL-3",
    "depends": [
        "pms_user_roles",
        "alda_helpdesk_pms",
        "alda_helpdesk_pms_enterprise",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.model.access.csv",
        "security/res_users_role.xml",
    ],
    "installable": True,
}
