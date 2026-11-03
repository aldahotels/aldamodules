# Private repository: the author does not include the OCA on purpose.
# pylint: disable=manifest-required-author
{
    "name": "Alda AI Tool",
    "summary": "AI tools of Alda Hotels: payroll 465 and bank reconciliation",
    "version": "16.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Commit [Sun]",
    "website": "https://github.com/OCA/pms",
    "license": "AGPL-3",
    "depends": [
        "account_accountant",
        "account_reconcile_lock_date",
        "pms_ai_tool",
        "pms_hr_property",
    ],
    "data": [
        "data/ai_tools.xml",
    ],
    "installable": True,
    "application": False,
}
