================
Connector Agora
================

.. |badge1| image:: https://img.shields.io/badge/licence-AGPL--3-blue.png
    :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
    :alt: License: AGPL-3

.. |badge2| image:: https://img.shields.io/badge/version-16.0.1.0.0-blue.png
    :alt: Version: 16.0.1.0.0

|badge1| |badge2|

Connector for **Agora POS** — imports sales invoices from Agora into Odoo
``account.move``, supporting both file-based XML/JSON export and HTTP API modes.

**Table of contents**

.. contents::
   :local:

Features
========

* Configure one or more Agora POS backends per company.
* Two connection modes:

  * **File-based** (recommended): monitors an export folder where Agora's
    ``ais.exe`` drops XML or JSON files automatically.
  * **HTTP API**: polls the Agora HTTP API directly using a URL and token.

* Imports sales invoices (``account.move`` of type ``out_invoice``) with full
  line detail, taxes, journal and partner resolution.
* Tracks each imported invoice through a binding model (``agora.account.move``)
  that stores the original Agora metadata: series, number, workplace, business
  day, POS ID and source file.
* Computed fields on ``account.move``: **Agora Invoice** (series + number) and
  **Agora Origin** (workplace name), visible directly on the invoice form.
* Duplicate detection — re-importing the same Agora invoice ID is a no-op.
* **Workplace → PMS property** mapping table.
* **Agora payment method → Odoo payment mode** mapping table.
* Smart button on each backend showing the total count of imported invoices.
* Manual **Import Invoices Now** button and **Test Connection** button on the
  backend form.

Installation
============

#. Make sure the following modules are installed:

   * ``account``
   * ``connector``
   * ``pms``
   * ``account_payment_partner``

Configuration
=============

#. Go to **Connector Agora → Configuration → Backends** and create a new backend.
#. Choose the **connection type**:

   * *File-based*: set the local path where Agora exports files
     (e.g. ``/srv/agora/export``) and choose the file format (XML or JSON).
   * *HTTP API*: set the Agora server URL and the API token.

#. Set the **Import Options** (invoices, POS closeouts, system closeouts).
#. Configure **Property Mapping** to link each Agora workplace to a PMS property.
#. Configure **Payment Mode Mapping** to link Agora payment methods to Odoo
   payment modes.
#. Set the **Execution User** that will be used for background jobs.

Usage
=====

* Click **Test Connection** to verify that Odoo can reach the Agora export
  folder or API endpoint.
* Click **Import Invoices Now** to trigger a manual import immediately.
* The **Invoices** smart button shows all invoices imported from this backend.
* On any imported ``account.move``, the **Agora Invoice** and **Agora Origin**
  fields identify the source document from Agora.

Credits
=======

Authors
-------

* Alexandra Suarez — Aldamodules
* Jose Luis Algara — Aldamodules

Based on the structure of ``connector_docuware`` by Comunitea.

Maintainers
-----------

This module is maintained by **Aldamodules**.

.. image:: https://img.shields.io/badge/maintained%20by-Aldamodules-informational
   :alt: Maintained by Aldamodules
