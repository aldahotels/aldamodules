On staging only:

#. Set the system parameter ``alda_ai_lab.enabled`` to ``True``. The tools also
   need the Doodba environment ``test`` (staging) or ``devel``: in production
   they are neither listed nor run.
#. Turn on the writes of ``pms_ai_tool`` (``pms_ai_tool.write_enabled``) and,
   in *Settings > Technical > AI > Tools*, give each lab tool its allowed users
   and enable its writes.
#. Add the tools to the MCP server.

A deploy to staging neutralizes the database and switches every scheduled
action off. Scheduling or resuming a report turns the scheduled action *AI
lab: send the scheduled reports* back on; it can also be done by hand.
