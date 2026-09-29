# Copyright 2026 Alda Hotels
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Alda Security Baseline",
    "summary": "Instance-wide security hygiene: technical features, "
    "new-user template and export measurement",
    "version": "16.0.1.0.0",
    "category": "Tools",
    "author": "Alda Hotels",
    "website": "https://github.com/aldahotels/aldamodules",
    "license": "AGPL-3",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter_data.xml",
        "data/security_baseline_data.xml",
        "views/alda_security_export_log_views.xml",
    ],
    "installable": True,
}
