Alda Helpdesk PMS🏨⚙️
=====================================

.. image:: https://img.shields.io/badge/license-LGPL--3-blue.svg
   :target: https://www.gnu.org/licenses/lgpl-3.0.html
   :alt: License

Módulo de integración de Indicadores del PMS Property a los tickets para Alda Hotels
-------------------------------------------------------------------

Este módulo extiende la funcionalidad del sistema de helpdesk de Odoo para gestionar
tickets relacionados con propiedades (PMS - Property Management System). Proporciona 
características especializadas para el sector hotelero, permitiendo gestionar 
incidencias de habitaciones, calcular prioridades automáticas basadas en métricas 
del hotel, y ofrecer una interfaz web para la creación de tickets.

Principales Características
---------------------------
1. Gestión de Etiquetas Detalladas
- Sistema de etiquetas personalizadas para clasificar tickets
- Etiquetas predefinidas: Habitación, Habitación Bloqueada, Baño, Compañía Externa
- Colores automáticos para mejor visualización

2. Gestión de Habitaciones y Propiedades
- Vinculación de tickets con habitaciones específicas y propiedades (hoteles)
- Detección automática de habitaciones bloqueadas
- Cálculo de días acumulados de bloqueo
- Cálculo de pérdida económica por habitaciones bloqueadas (ADR Acumulado)

3. Sistema de Prioridades Inteligente
Cálculo automático de prioridad basado en múltiples factores:
- Ocupación del hotel (Occupancy Rate)
- Tasa de habitaciones bloqueadas (Block Rate)
- Temporada (Alta/Baja)
- Estado operativo de la propiedad y habitación
- Días acumulados de bloqueo

4. Métricas y KPIs en Tiempo Real
- Integración con el sistema de KPIs diarios
- Visualización de tasa de ocupación
- Conteo de habitaciones bloqueadas
- Información contextual sobre el estado del hotel

5. Interfaz Web para Creación de Tickets
- Formulario web accesible para usuarios públicos/portal
- Selección inteligente de habitaciones y propiedades
- Cálculo automático de prioridad al crear tickets
- Confirmación y seguimiento de tickets creados

6. Sistema de Alertas
Niveles de alerta basados en ocupación:
- Sin alerta
- Ocupación baja (<30%)
- Ocupación media (30-70%)
- Ocupación crítica (>70%)

Modelos Extendidos
------------------
- Heldesk Tickets (`helpdesk.ticket`)
- Alda PMS KPI

Estructura del Módulo
---------------------

.. code-block:: text

    alda_helpdesk_pms/
    ├── models/
    │   ├── __init__.py
    │   ├── helpdesk_ticket.py          # Extensiones del modelo Helpdesk
    │   └── helpdesk_ticket_type.py     # Asociar un tipo a un Equipo
    |   └── helpdesk_ticket_priority.py    # Lógica de prioridad basada en reglas
    |   └── helpdesk_priority_rule.py      # Definición de reglas de prioridad
    ├── views/
    │   ├── helpdesk_pms_form_template.xml  # Vista del formulario Web de tickets 
    │   ├── helpdesk_ticket_views.xml       # Vistas de tickets
    │   ├── helpdesk_ticket_type_views.xml     # Vistas de tipos de ticket
    │   └── helpdesk_priority_rule_views.xml    # Vistas de reglas de prioridad
    │   └── menu_item.xml
    │
    ├── static/
    │   └── src/
    │       └── js/ticket_form.js      # Lógica JS para el formulario Web
    ├── controllers/
    │   ├── __init__.py
    │   └── main.py                    # Controlador para el formulario Web
    ├── security/
    │   ├── ir.model.access.csv        # Permisos de acceso a modelos
    │   └── helpdesk_pms_security.xml  # Reglas de acceso
    ├── data/
    │   ├── ir_cron.xml
    │   └── locatin_data.json   # Lista de lugares (implementación temporal)
    ├── __manifest__.py                 # Metadata del módulo
    └── README.rst                      # Este archivo

Requisitos de Instalación
-------------------------

- Odoo 16.0: "website", "helpdesk", "alda_helpdesk_pms_enterprise", "alda_pms_kpi"


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