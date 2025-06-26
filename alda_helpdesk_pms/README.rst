PMS Property Helpdesk Alda🏨⚙️
=====================================

.. image:: https://img.shields.io/badge/license-LGPL--3-blue.svg
   :target: https://www.gnu.org/licenses/lgpl-3.0.html
   :alt: License

Módulo de integración entre Helpdesk y PMS Property para Alda Hotels
-------------------------------------------------------------------

Este módulo permite crear tickets de soporte técnico y atención al cliente 
en el entorno hotelero mediante un formulario web asociado a una propiedad específica (`pms.property`)
y desde un portal web para clientes (recepciones) y empleados (usuarios portal autorizados).
Su propósito es tomar un enlace generado desde Roomdoo, los parámetros requeridos y permitir
el acceso al formulario de creación de tickets de Alda Hotels.

Principales Características
---------------------------


Modelos Extendidos
------------------


Estructura del Módulo
---------------------

.. code-block:: text

    helpdesk_pms_enterprise/
    ├── models/
    │   ├── __init__.py
    │   ├── 
    ├── views/
    │   ├── 
    │  
    ├── static/
    │   └── src/
    │       └── js/
    ├── __manifest__.py                 # Metadata del módulo
    └── README.rst                      # Este archivo

Requisitos de Instalación
-------------------------

1. Tener instalado el módulo ``helpdesk`` (y helpdesk_pms_enterprise)
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