# Private repository: the author does not include the OCA on purpose.
# pylint: disable=manifest-required-author
{
    "name": "Alda AI Lab",
    "summary": "Staging-only demo AI tools: group bookings, mass changes, "
    "campaigns, mail templates and scheduled reports",
    "version": "16.0.1.0.0",
    "category": "Generic Modules/Property Management System",
    "author": "Commit [Sun]",
    "website": "https://github.com/aldahotels/aldamodules",
    "license": "AGPL-3",
    "depends": [
        "base_automation",
        "mass_mailing",
        "pms_ai_tool",
        "pms_notifications",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/alda_ai_lab_security.xml",
        "data/ai_tools_report.xml",
        "data/ai_tools_group_booking.xml",
        "data/ai_tools_reservation_update.xml",
        "data/ai_tools_campaign.xml",
        "data/ai_tools_mail_template.xml",
        "data/ir_cron.xml",
        "views/alda_ai_lab_schedule_views.xml",
    ],
    "installable": True,
    "application": False,
}
