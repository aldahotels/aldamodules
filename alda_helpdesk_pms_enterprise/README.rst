PMS Property Helpdesk Enterprise 🏨⚙️
=====================================

.. image:: https://img.shields.io/badge/license-LGPL--3-blue.svg
   :target: https://www.gnu.org/licenses/lgpl-3.0.html
   :alt: License

Módulo de integración entre Helpdesk y PMS Property para Alda Hotels
-------------------------------------------------------------------

Este módulo permite la gestión de tickets de soporte técnico y atención al cliente 
en el entorno hotelero, asociando cada ticket a una propiedad específica (`pms.property`) 
y opcionalmente a una habitación (`pms.room`).
Los clientes que pueden crear tickets sereán usuarios portal o usuarios interntos con Hoteles
asignados en la ficha del empleado en la sección Workplaces asigned.

Principales Características
---------------------------

✅ **Gestión de Tickets por Propiedad**
   - Campo obligatorio ``pms_property_id`` en todos los tickets y 
        con filtro sobre las "Workplaces asigned" en la ficha del empleado
   - Campo opcional ``pms_room_id`` filtrado por propiedad seleccionada

🔒 **Validaciones y Seguridad**
   - Validación de permisos por empleado
   - Limpieza automática de habitación al cambiar de hotel
   - Restricción: Habitación debe pertenecer al hotel seleccionado

📊 **Dashboard y Accesos Directos**
   - Contador de tickets por propiedad
   - Botón de acceso rápido a tickets desde la ficha del hotel
   - Integración con portal web para clientes

🚀 **Optimizaciones Técnicas**
   - Conteo en tiempo real de tickets
   - Filtro para listar tickets por hotel y por habitación en las vistas de Helpdesk
   - Agrupar tickets por hotel y habitación en las vistas
   - Vistas pivot a partir de los campos hotel y habitación

Modelos Extendidos
------------------

helpdesk.ticket
~~~~~~~~~~~~~~~

+-------------------------+-------------+---------------------------------------------------+-----------------+------------+
| Campo                   | Tipo        | Descripción                                       | Relación        | Requerido  |
+=========================+=============+===================================================+=================+============+
| pms_property_id         | Many2one    | Hotel asociado al ticket                          | pms.property    | ✔️ Sí      |
+-------------------------+-------------+---------------------------------------------------+-----------------+------------+
| pms_room_id             | Many2one    | Habitación específica relacionada                 | pms.room        | ❌ No      |
+-------------------------+-------------+---------------------------------------------------+-----------------+------------+

pms.property (Extensión)
~~~~~~~~~~~~~~~~~~~~~~~~

+-------------------------+-------------+---------------------------------------------------+-----------------------+
| Campo                   | Tipo        | Descripción                                       | Función               |
+=========================+=============+===================================================+=======================+
| ticket_count            | Integer     | Número de tickets asociados                       | Calculado automático  |
+-------------------------+-------------+---------------------------------------------------+-----------------------+
| helpdesk_ticket_ids     | One2many    | Lista completa de tickets vinculados              | helpdesk.ticket       |
+-------------------------+-------------+---------------------------------------------------+-----------------------+
| action_view_tickets()   | Método      | Abre vista filtrada de tickets                    | Retorna acción window |
+-------------------------+-------------+---------------------------------------------------+-----------------------+

Estructura del Módulo
---------------------

.. code-block:: text

    alda_helpdesk_pms_enterprise/
    ├── models/
    │   ├── __init__.py
    │   ├── helpdesk_ticket.py          # Extensiones del modelo Helpdesk
    │   └── pms_property.py             # Extensiones del modelo Property
    ├── views/
    │   ├── actions.xml                 # Abrir vista de tickets sobre el hotel
    │   ├── helpdesk_ticket_views.xml   # Vistas de tickets
    │   ├── pms_property_views.xml      # Vistas de Hoteles
    │  
    ├── static/
    │   └── src/
    │       └── js/
    ├── __manifest__.py                 # Metadata del módulo
    └── README.rst                      # Este archivo

Requisitos de Instalación
-------------------------

1. Tener instalado el módulo ``helpdesk``
2. Tener instalado el módulo ``pms`` (y pms_hr_property)
3. Tener instalado el módulo ``hr``
4. Permisos adecuados para los usuarios


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