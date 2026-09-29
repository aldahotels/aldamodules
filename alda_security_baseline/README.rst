======================
Alda Security Baseline
======================

.. |badge1| image:: https://img.shields.io/badge/licence-AGPL--3-blue.png
   :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
   :alt: License: AGPL-3

|badge1|

Instance-wide security hygiene for the Alda Hotels database. It is kept apart
from the role modules because it touches every user.

It does three things:

#. Stops granting **Technical Features** (``base.group_no_one``) to every
   internal user.
#. Removes administrator-level groups from the **template user**
   (``base.default_user``).
#. Records who exports what, as data for a later decision on
   ``base.group_allow_export``.

It never removes groups from existing users: which users keep
``base.group_system``, ``base.group_erp_manager`` or
``base.group_allow_export`` is a management decision.

**Table of contents**

.. contents::
   :local:

Technical Features
==================

In the core, **Internal User** (``base.group_user``) implies **Technical
Features** (``base.group_no_one``), so every internal user sees the technical
menus, fields and actions as soon as they turn on debug mode. This module:

* makes **Access Rights** (``base.group_erp_manager``) imply Technical
  Features. **Settings** (``base.group_system``) implies Access Rights, so
  administrators and user administrators keep it;
* removes the implication from Internal User;
* removes Technical Features from every user (the template user included) who
  does not get it through another group.

This is mostly UI hygiene in debug mode. It is not an access control layer, but
it has side effects:

* the fuzzy search indexes (``trgm.index``, module ``base_search_fuzzy``) can
  only be managed by users who keep Technical Features. Creating or deleting
  one runs ``CREATE INDEX`` or ``DROP INDEX``, so this is an improvement;
* on new purchase requests (module ``purchase_request``) the reference can
  only be edited by users who keep Technical Features;
* non-administrator users lose the debug-only menus and actions, for example
  the accounting configuration menus (account tags, account groups, tax groups,
  report configuration) and the *Resequence* action on journal entries. Tell
  the accounting team before deploying, and decide per person whether someone
  who needs them gets the **Technical Features (w/o debug mode)** group instead;
* access errors on fields show the generic message instead of the detailed
  one;
* any module installed later that grants access rights to
  ``base.group_no_one`` makes that model available only to the users who keep
  Technical Features.

**Technical features group** (module ``base_technical_features``): its group
implies Technical Features, so its members keep it and see the technical menus
even without debug mode. A user who unticks *Technical Features* in their
preferences loses ``base.group_no_one`` on the next run of the baseline. A user
without ``base.group_no_one`` cannot tick that checkbox by themselves.

**Explicit grants are not supported**: ticking Technical Features on a single
user is reverted on every run. To give it to someone, use the Technical
Features (w/o debug mode) group, or a group or role that implies
``base.group_no_one``.

New-user template
=================

The groups of the template user are the default groups of every new internal
user created from the user form, or by code that does not set its groups.
Users made by duplicating another user do not use the template. The module
removes these groups from the template, when their module is installed:

* ``account.group_account_manager``
* ``hr.group_hr_manager``
* ``hr_contract.group_hr_contract_manager``
* ``purchase.group_purchase_manager``
* ``stock.group_stock_manager``
* ``point_of_sale.group_pos_manager``
* ``project.group_project_manager``
* ``sales_team.group_sale_manager``
* ``website.group_website_designer``
* ``helpdesk.group_helpdesk_manager``
* ``base.group_allow_export``
* ``base.group_partner_manager``
* ``sql_request_abstract.group_sql_request_user``
* ``sql_request_abstract.group_sql_request_manager``
* ``base.group_system``
* ``base.group_erp_manager``

Existing users keep these groups: the core only propagates the groups *added*
to the template.

Only the listed groups are removed. It demotes each app from administrator to
user level in the template; it does not remove app access. The groups implied
by the removed ones stay, as do the other groups of the template, so new users
may still, for example, create and edit contacts or post journal entries
through their app user groups. A listed group that another template group
implies is kept, with a warning in the server log: new users would get it back
through the implication anyway.

The template gets contaminated again when:

* **a new module is installed**: its groups are added to the template *and* to
  every active internal user. The baseline cleans the template on its next run
  but does not undo the latter;
* **an administrator edits the template groups** (General Settings >
  Permissions > Default Access Rights): every group added there is also given
  to every active internal user;
* **the template has roles** (module ``base_user_role``): its groups are then
  rewritten from the roles. The baseline logs a warning; sanitize the roles
  instead.

Export log
==========

Every successful call to ``export_data`` is recorded in an **Export Log**
(Settings > Technical > Security > Export Log, administrators only, in debug
mode): user, model, number of records, number of fields, import-compatible
mode and date. A grouped spreadsheet export is recorded as one row. A denied
export (user without ``base.group_allow_export``) is not recorded. Logging
never makes an export fail.

Scope: only the ORM export (the *Export* dialog of list views, in CSV and XLSX,
and ``export_data`` over RPC). These bypass both ``base.group_allow_export``
and this log:

* the *Download xlsx* button of pivot views;
* spreadsheets;
* ``sql_export``, ``report_xlsx`` reports and PDF prints;
* the PMS APIs;
* models that override ``export_data`` without calling ``super()`` (the
  ``channel.*`` connector bindings).

The core already writes an ``INFO`` line for each export made from the Export
dialog (``User <id> exported <n> <model> records ...``). The existing server
logs give historical data without waiting for this log to fill up.

Rows older than the retention period are deleted by the daily autovacuum job.
The period, in days, is the system parameter
``alda_security_baseline.export_log_retention_days`` (default ``180``; ``0``
keeps every row).

Logging exports is monitoring of employee activity: make sure staff are
informed, as data protection rules require, before installing this module in
production.

Usage
=====

The baseline is applied when the module is installed and again on every update
of the module. An administrator can also re-apply it at any time: Settings >
Technical > Actions > Server Actions > *Apply Alda security baseline* > *Run*.
Every run is idempotent.

Updating ``base`` (or all modules) does **not** undo the baseline: the core
records of the Internal User group and of the template user are ``noupdate``.

These can undo it, and require a new run:

* installing any new module (template groups);
* adding Technical Features back to the inherited groups of Internal User;
* restoring an older database backup.

Before installing or updating the module, check that no user holds more than
one user type (internal, portal, public). The core validates this on every
change of group members, and one such user aborts the whole run::

    SELECT r.uid
      FROM res_groups_users_rel r
      JOIN res_groups g ON g.id = r.gid
      JOIN ir_model_data d
        ON d.model = 'ir.module.category' AND d.res_id = g.category_id
     WHERE d.module = 'base' AND d.name = 'module_category_user_type'
     GROUP BY r.uid
    HAVING count(*) > 1;

Uninstalling the module keeps the hygiene in place. To restore the core
behaviour, add Technical Features to the inherited groups of Internal User,
which gives it back to every internal user.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/aldahotels/aldamodules/issues>`_.

Credits
=======

Authors
~~~~~~~

* Alda Hotels
