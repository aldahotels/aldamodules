System parameters, all optional:

* ``alda_ai_tool.bank_journal_prefix`` (``CB``) and
  ``alda_ai_tool.tpv_journal_prefix`` (``TB``): codes of the hotel's bank and
  TPV journals; the digits after the prefix are the hotel code.
* ``alda_ai_tool.cents_threshold`` (``0.05``): largest difference written off.
* ``alda_ai_tool.writeoff_expense_account_code`` (``67800000000``) and
  ``alda_ai_tool.writeoff_income_account_code`` (``77800000000``).
* ``alda_ai_tool.taz_job_ids``: jobs that make an employee the TAZ of a hotel.
  By default, the jobs whose name contains "TAZ".

The hotel of an employee comes from the employee's properties
(``pms_hr_property``); the analytic account of the write-off, from the
property.
