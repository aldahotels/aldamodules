AI tools for the helpdesk of Alda Hotels, served over MCP with the guardrails
of ``pms_ai_tool``. The number of a ticket is always its ``ticket_ref``, the
one users see, never the internal id.

Read only:

* ``alda_helpdesk_ticket_search``: tickets by text, number, hotel, team and
  open or closed.
* ``alda_helpdesk_ticket_detail``: one ticket with its customer (masked), hotel
  and room, SLA status and last messages.
* ``alda_helpdesk_backlog``: open tickets by team, stage and hotel, by age and
  unassigned.

They change data and need a preview and an explicit confirmation, a list of
allowed users and the switches of ``pms_ai_tool`` turned on:

* ``alda_helpdesk_ticket_add_note``: internal note on a ticket, without
  notifying anyone by name.
* ``alda_helpdesk_activity_schedule``: To-Do activity on a ticket for a user,
  who receives the assignment email of Odoo.
