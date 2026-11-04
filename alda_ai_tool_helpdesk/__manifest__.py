# Private repository: the author does not include the OCA on purpose.
# pylint: disable=manifest-required-author
{
    "name": "Alda AI Tool Helpdesk",
    "summary": "AI tools of Alda Hotels: helpdesk tickets (search, detail, backlog, "
    "notes and activities)",
    "version": "16.0.1.0.0",
    "category": "Services/Helpdesk",
    "author": "Commit [Sun]",
    "website": "https://github.com/OCA/pms",
    "license": "AGPL-3",
    "depends": [
        "helpdesk",
        "alda_helpdesk_pms",
        "pms_ai_tool",
    ],
    "data": [
        "data/ai_tools.xml",
    ],
    "installable": True,
    "application": False,
}
