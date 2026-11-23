System parameters, all optional:

* ``alda_ai_tool.bank_journal_prefix`` (``CB``) and
  ``alda_ai_tool.tpv_journal_prefix`` (``TB``): codes of the hotel's bank and
  TPV journals; the digits after the prefix are the hotel code.
* ``alda_ai_tool.cents_threshold`` (``0.05``): largest difference written off.
* ``alda_ai_tool.writeoff_expense_account_code`` (``67800000000``) and
  ``alda_ai_tool.writeoff_income_account_code`` (``77800000000``).
* ``alda_ai_tool.taz_job_ids``: jobs that make an employee the TAZ of a hotel.
  By default, the jobs whose name contains "TAZ".
* ``alda_ai_tool.purchase_journal_prefix`` (``FR``): code of the hotel's
  purchase journal, where ``alda_bank_reconcile_all`` looks for the vendor
  bills of the charges. The journal must have the hotel among its properties
  or be coded prefix + hotel code.

The hotel of an employee comes from the employee's properties
(``pms_hr_property``); the analytic account of the write-off, from the
property.

Sabadell (``alda_bank_sabadell_pending``, ``alda_bank_sabadell_merchant``,
``alda_bank_reconcile_sabadell``):

* ``alda_ai_tool.sabadell_journal_prefix``, **no default**: code prefix of the
  hotels' Sabadell bank journals, where the statements are imported. Until it
  is set, the Sabadell tools only explain what to configure.
* ``alda_ai_tool.sabadell_transfer_prefix`` (``CA``),
  ``alda_ai_tool.sabadell_terminal_prefix`` (``TA``),
  ``alda_ai_tool.sabadell_provider_prefix`` (``VA``) and
  ``alda_ai_tool.sabadell_kiosk_prefix`` (``WA``): journals of transfers and
  cash, Sabadell card terminal, payment provider P&S and kiosk.
* ``alda_ai_tool.sabadell_pos_concept`` (``POS\s+SETTLEMENT\D*(\d+)``) and
  ``alda_ai_tool.sabadell_cash_concept`` (``CASH\s+DEPOSIT``): patterns, case
  insensitive, of the concept of a card settlement (the first group is the
  merchant number) and of a cash deposit. Check them against a real statement.
* ``alda_ai_tool.sabadell_cents_threshold``: tolerance shown for card
  settlements; by default, ``alda_ai_tool.cents_threshold``. Nothing is
  written off for Sabadell.

The merchant number is P&S (VA) when it is the merchant code of a Redsys
provider of the hotel (read with sudo, only that field). Other numbers are
stored per hotel with ``alda_bank_sabadell_merchant`` after the user confirms
them (model ``alda.bank.merchant``: read for accountants, changes for
accounting managers and the tool).

Write tools (``alda_bank_reconcile``, ``alda_bank_reconcile_all``,
``alda_bank_reconcile_sabadell``, ``alda_bank_sabadell_merchant``,
``alda_bank_notify_taz``...) are created with changes disabled: enable
``write_enabled`` and set the allowed users on each tool, and the system
parameter ``pms_ai_tool.write_enabled``.
