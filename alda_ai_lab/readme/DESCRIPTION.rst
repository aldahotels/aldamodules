Demo AI tools for staging, served over MCP with the guardrails of
``pms_ai_tool``. They show what an assistant can do when it is allowed to
change data in bulk, and they are **not meant for production**:

* ``lab_group_booking_create``: a group booking (folio and reservations) from
  one sentence, with availability and prices checked first.
* ``lab_reservations_bulk_update``: a discount or a board change on many
  reservations at once, with the impact in money before confirming.
* ``lab_reactivation_campaign``: a draft email campaign for the companies of a
  salesperson that are cooling down. The tool never sends it.
* ``lab_mail_template_create``: a mail template for folios or reservations,
  rendered with a real record before it is saved.
* ``lab_report_schedule``, ``lab_report_schedules`` and
  ``lab_report_schedule_manage``: reports of the catalogue sent every day, week
  or month to the chat with OdooBot.

Every tool previews first and only changes data after an explicit
confirmation. The tools refuse to run outside staging: the container must say
it is not production and the database must have the lab switched on.
