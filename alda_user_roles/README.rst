===============
Alda User Roles
===============

.. |badge1| image:: https://img.shields.io/badge/licence-AGPL--3-blue.png
   :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
   :alt: License: AGPL-3

|badge1|

Restricted user roles for Alda Hotels, built on ``pms_user_roles``.

**Table of contents**

.. contents::
   :local:

SMT (support team)
==================

The *SMT (support team)* role gives Helpdesk and Discuss, on the tickets of
every hotel, and nothing else:

* Internal user, Helpdesk user and Multi Companies.
* *PMS support read-only*: read access to properties, rooms, room types and
  amenities, which the ticket form needs to show, search and pick the hotel
  and the room of a ticket. It grants no PMS operation: folios, reservations,
  check-ins, prices and KPIs stay closed.
* Every active property and its company, through the *All properties* option
  of ``pms_user_roles``. New hotels are added when they are created; what the
  role added is removed when the user loses the role.

It is assignable by profile managers.

It never grants Settings, Access Rights, exports, contact creation, Helpdesk
administration, invoicing, accounting, payroll, sales or any PMS group. The
tests check the exact set of groups a holder ends up with.

Prerequisites before production
===============================

* The helpdesk fixes of ``alda_helpdesk_pms``, ``alda_helpdesk_pms_enterprise``
  and ``alda_pms_kpi`` (blocked-room refresh, PMS figures on tickets, KPI
  popup): without them a support user can read figures of rooms and hotels.
* Credentials stored on properties and rooms (traveller report accounts,
  door-code seeds, TV system accounts) are readable by anyone with read access
  to those models. They must be restricted with ``groups`` in the modules that
  declare them before this role goes live.
* Holders get every property. The Roomdoo app and API logins must refuse users
  without PMS rights, otherwise a support user could use the app, which works
  as superuser, on every hotel.

Known limitations
=================

* Price lists and products are readable by every internal user (core
  ``product`` access rights), so they are readable by this role too.
* The properties a user may pick on a ticket are fixed when the web client
  loads: after a new hotel is created, the user reloads the page to use it.
* The tickets shown also depend on the companies selected in the company
  switcher.

Deployment
==========

#. Remove any role or group created by hand to test this profile, and the
   role lines that use them.
#. Install ``pms_user_roles`` and this module.
#. Give the role to the support users through *Roles > Role assignments*.

Uninstalling the module deletes the role: its holders keep *Internal user*
thanks to the safety net of ``pms_user_roles`` and lose everything else.

Credits
=======

Authors
-------

* Alda Hotels

Contributors
------------

* Darío Lodeiros <dario@roomdoo.com>
