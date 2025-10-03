Alda Helpdesk Autoassign 🏨⚙️
=====================================

.. image:: https://img.shields.io/badge/license-LGPL--3-blue.svg
   :target: https://www.gnu.org/licenses/lgpl-3.0.html
   :alt: License

Módulo de Odoo para la gestión automática de asignación de tickets en Helpdesk
basado en los puestos de trabajo de los empleados y su relación con hoteles (PMS).


Características
---------------
*   Asigna automáticamente nuevos tickets de Helpdesk a usuarios basándose en:
    *   El **hotel** asociado al ticket (`hotel_id`).
    *   El **tipo de ticket**, que se obtiene de la relación con  **equipo de Helpdesk**.
    *   El **puesto de trabajo** del empleado (`hr.job`), vinculado al equipo de Helpdesk.
    *   Los empleados deben tener el hotel asignado en su campo Centro asignado `center_assigned_ids`.
    *   El **Equipo del Helpdesk** tiene activa Asignación basada en Hoteles `assign_by_property`
    *   Los **Puestos de Trabajo** tiene la relación con el **Equipo del Helpdesk** y opcionalmente los **Tipos de Tickets**
    *   Los miembros del equipo con asignación basada en hoteles se asignan automáticamente y se pueden ajustar y serán los empleados que cumplan los criterios.
    *   Finalmente, los tickets cuyos criterios tengan relación con los miembros del equipo son asignados automáticamente según el método seleccionado **Balanceado** o **Aleatorio**.
    *   La autoasignación se ejecuta cuando se crea el ticket tanto desde el formulario del back como el formulario web. 
*   Extiende el método nativo `_determine_user_to_assign` de `helpdesk.team` para integrarse sin problemas con la lógica de asignación existente de Odoo.
*   Extiende el controlador web de **Alda Helpdesk PMS** para ejecutar la autoasignación desde el formulario web.

------------------
Modelos Extendidos
------------------
*   `helpdesk.team`: Se extiende el método `_determine_user_to_assign` y se añade una opción al campo `assign_method`.
*   `main.py` del controlador de **Alda Helpdesk PMS** agregando los valores para `user_id`.



Estructura del Módulo
---------------------
- models/
  - helpdesk_ticket.py: Se agregan métodos nuevos y se refactorizan los métodos del modelo base para el proceso de autoasignación a partir de los valores del ticket. 
  - helpdesk.py: Se extiende la estructura de datos del modelo padre y se reutilizan los métodos utilizando los nuevos campos y lógica de autoasignación basada en hoteles y empleados.
- views/
  - helpdesk_ticket.views.xml: Modificaciones en la vista del equipo de helpdesk para incluir el campo y métodos sobre `assign_by_property`.

Requisitos de Instalación
-------------------------

*   `helpdesk` (Odoo Enterprise)
*   `hr`
*   `alda_helpdesk_pms`


Créditos y Contacto
-------------------

**Desarrollado por:**

* Irlui Ramírez - `irlui@aldahotels.com`_
* Jose Luis Algara Toledo - `osotranquilo@gmail.com`_

**Empresas:**

* `Alda Hotels <https://www.aldahotels.es>`_
* `Commitsun <https://www.commitsun.com>`_

.. _irlui@aldahotels.com: mailto:irlui@aldahotels.com
.. _osotranquilo@gmail.com: mailto:osotranquilo@gmail.com