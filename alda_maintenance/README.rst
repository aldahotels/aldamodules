================
Alda Maintenance
================

.. |badge1| image:: https://img.shields.io/badge/licence-AGPL--3-blue.png
   :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
   :alt: License: AGPL-3

|badge1|

Adds a **Hotel** field (``pms.property``) to ``maintenance.equipment``,
so each piece of equipment can be linked to the corresponding hotel property.

The field is automatically populated with the user's active property
(``get_active_property_ids``).

**Table of contents**

.. contents::
   :local:

Usage
=====

Go to **Maintenance > Equipments**, open any equipment record and fill
in the **Hotel** field.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/aldahotels/aldamodules/issues>`_.

Credits
=======

Authors
~~~~~~~

* Alexandra Suarez Graterol (Alda hotels)
