lda Helpdesk HR 🏨⚙️
====================

.. image:: https://img.shields.io/badge/license-AGPL--3-blue.svg
   :target: https://www.gnu.org/licenses/agpl-3.0.html
   :alt: License

Módulo de Odoo que extiende el modelo ``hr.job`` para permitir la asociación
directa entre puestos de trabajo y equipos de Helpdesk, así como los tipos de tickets
específicos del equipo asociado. Facilita la configuración de perfiles de trabajo
relacionados con tareas de soporte técnico en contextos hoteleros (PMS).

Características
---------------
*   **Asociación Puesto-Equipo:** Relaciona un puesto de trabajo (``hr.job``) con un
    equipo de Helpdesk (``helpdesk.team``) específico mediante el campo ``ticket_team_id``.
*   **Asociación Puesto-Tipo de Ticket:** Relaciona un puesto de trabajo con uno o varios
    tipos de tickets (``helpdesk.ticket.type``) mediante el campo ``ticket_type_ids``.
    El dominio de selección se restringe automáticamente al equipo de Helpdesk asociado.
*   **Control de Coherencia:** Un ``@api.constrains`` asegura que los tipos de ticket
    seleccionados pertenezcan al equipo de Helpdesk asociado al puesto de trabajo.
*   **Filtrado en Formulario:** El widget Many2Many para seleccionar tipos de ticket
    en el formulario del puesto de trabajo se filtra dinámicamente según el equipo
    seleccionado usando un ``@api.onchange`` y un ``domain`` en la vista XML.
*   **Visualización en Vista Lista:** Añade los campos ``ticket_team_id`` y
    ``ticket_type_ids`` a la vista de lista (tree) de puestos de trabajo para una
    mejor visibilidad.
*   **Búsqueda y Agrupación:** Añade filtros y opciones de agrupación por equipo de
    Helpdesk y tipo de ticket en la vista de búsqueda de puestos de trabajo.
*   **Campo Computado (UI):** Incluye un campo booleano computado ``is_ticket_type_ids``
    para indicar visualmente si el equipo de Helpdesk asociado tiene tipos de ticket
    disponibles (usado para controlar visibilidad en la vista).
*   **Campo Computado (Lógica):** Incluye un campo Many2many computado ``type_avalible``
    que almacena dinámicamente los tipos de ticket disponibles para el equipo
    seleccionado (útil para lógica adicional en Python o vistas).

Modelos Extendidos
------------------
*   ``hr.job``: Se añaden los campos ``ticket_team_id``, ``ticket_type_ids``,
    ``is_ticket_type_ids`` y ``type_avalible``, junto con sus métodos de cálculo,
    onchange y constraints.

Vistas Extendidas
-----------------
*   ``hr.view_hr_job_form``: Se añade una nueva página "Helpdesk" con campos para
    asociar el equipo y los tipos de ticket.
*   ``hr.view_hr_job_tree``: Se añaden columnas para ``ticket_team_id`` y
    ``ticket_type_ids``.
*   ``hr.view_job_filter``: Se añaden campos de búsqueda y filtros de agrupación
    para ``ticket_team_id`` y ``ticket_type_ids``.

Requisitos de Instalación
-------------------------

*   ``helpdesk`` (Odoo Enterprise)
*   ``hr`` (Odoo Base)
*   ``alda_helpdesk_pms`` (crea la relación de tipos de tickets con equipos del helpdesk)

Estructura del Módulo
---------------------
- ``models/``
  - ``hr_job.py``: Contiene la extensión del modelo ``hr.job`` con los nuevos campos
    y lógica (onchange, compute, constrain).
- ``views/``
  - ``hr_job_views.xml``: Define las vistas heredadas para form, tree y search.

Créditos y Contacto
-------------------

**Desarrollado por:**

* Jose Luis Algara Toledo - `osotranquilo@gmail.com`_
* Irlui Ramírez - `irlui@aldahotels.com`_

**Empresas:**

* `Alda Hotels <https://www.aldahotels.es>`_
* `Commitsun <https://www.commitsun.com>`_

.. _osotranquilo@gmail.com: mailto:osotranquilo@gmail.com
.. _irlui@aldahotels.com: mailto:irlui@aldahotels.com

.. image:: https://www.gnu.org/graphics/lgplv3-88x31.png
   :target: https://www.gnu.org/licenses/lgpl-3.0.html
   :alt: LGPL-3.0-or-later