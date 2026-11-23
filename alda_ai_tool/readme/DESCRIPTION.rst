AI tools specific to Alda Hotels, served over MCP with the guardrails of
``pms_ai_tool``:

* ``alda_payroll_465_preview`` and ``alda_payroll_465_reconcile``: matching and
  reconciliation of the payroll accounts 465 by the 7-digit employee number.
* ``alda_bank_pending_lines``, ``alda_bank_match_candidates``,
  ``alda_bank_notify_taz`` and ``alda_bank_reconcile``: reconciliation of the
  CaixaBank statements of each hotel against the grouped TPV entries (``TB``)
  and the transfer collections (``CB``), the notice to the hotel's TAZ and the
  write-off of cents differences to 678/778.
* ``alda_bank_reconcile_all_preview`` and ``alda_bank_reconcile_all``: the
  whole CaixaBank account of a hotel in one request, as a numbered table bank
  against Odoo the user can leave lines out of: TPV settlements and transfers
  with a single exact match, and charges with the single vendor bill of the
  hotel's ``FR`` journal whose amount due is exactly the charge, checking the
  supplier's payment term (draft notice for the TAZ when paid late).

The write tools need a preview and an explicit confirmation, a list of allowed
users and the switches of ``pms_ai_tool`` turned on.
