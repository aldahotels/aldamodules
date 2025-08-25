ALDA PMS KPI's 🏨⚙️
=====================================

.. image:: https://img.shields.io/badge/license-LGPL--3-blue.svg
   :target: https://www.gnu.org/licenses/lgpl-3.0.html
   :alt: License

Module for calculating Performance Indicators for Alda Hotels
-------------------------------------------------------------

Overview
---------

The Alda PMS KPIs module is designed to help hotel managers track and analyze critical Key Performance Indicators (KPIs) for their properties. 
This module provides detailed insights into various metrics such as occupancy rates, room revenue, and blocked room usage, aiding in better decision-making and operational efficiency.

Main Features
-------------

- Automatic calculation of daily KPIs per property
- Historical KPI generation
- Wizard to generate multiple KPIs in batch
- Integration with the `pms.property` model

Key Features
------------

- 📅 Daily KPI computation per property
- 📈 Historical KPI generation via wizard
- 🧮 Metrics include:
  - Occupancy Rate
  - Block Rate
  - Available Rooms
  - Pax (Guests)
  - Room Revenue
  - ADR (Average Daily Rate)
  - RevPAR (Revenue per Available Room)
- 🧠 KPI mixin for reusable logic
- 🪄 Wizard for batch KPI generation
- 🔒 Access control via security groups
- 🖼️ Tree and form views for KPI visualization
- 📎 Integration with `pms.property` model

Dependencies
-------------------------
This module depends on the following Odoo modules:

- ``pms``: Core Property Management System module required for hotel property and reservation management.
- ``mail``: Enables chatter and messaging features for KPI records.


Créditos y Contacto
-------------------

**Authors:**

* Irlui Ramírez - `irlui@aldahotels.com`_
* Jose Luis Algara Toledo - `osotranquilo@gmail.com`_

**Companies:**

* `Alda Hotels <https://www.aldahotels.es>`_
* `Commitsun <https://www.commitsun.com>`_

.. _irlui@aldahotels.com: mailto:irlui@aldahotels.com
.. _osotranquilo@gmail.com: mailto:osotranquilo@gmail.com