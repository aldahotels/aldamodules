rst
==========================
Document Spreadsheet Relations
==========================
Este modulo es una extensión del modulo de Documents, permite gestionar y sincronizar datos
entre documentos de tipo hoja de cálculo, designando un archivo central, al cual se le vincularán
los valores de las celdas de otros archivos.
==========================
- Almacenar una clave de relación para vincular documentos y hojas de cálculo.
- Identificar si un documento es una hoja de cálculo.
- Contar el número de hojas de cálculo relacionadas con un documento.
- Sincronizar valores de celdas específicas entre documentos y hojas de cálculo.
- Interfaz de usuario para gestionar relaciones y mapeos de celdas.

Instalación
==========================
1. Clonar el repositorio en el directorio
2. Instalar dependencias.
3. Reiniciar el servidor Odoo.
4. Activar el módulo desde la interfaz de Odoo.
Configuración
==========================
Requerimientos
- python
- pandas
- openpyxl
- Documents y spreadsheet deben estar previamente instalados en Odoo.

Uso
==========================
1. **Documentos**:
   - Puedes crear documentos en Odoo y marcar aquellos que son hojas de cálculo.
   - Al crear o editar un documento, puedes especificar una clave de relación para vincularlo con otros documentos.
2. **Sincronización**:
   - Utiliza la función "Buscar relacionados" en la vista de formulario de un documento para encontrar hojas de cálculo relacionadas.
   - Utiliza la función "Sincronizar" para actualizar los valores de las celdas en la hoja de cálculo central.
3. **Mapeo de Celdas**:
   - Crea un "Archivo Central" para almacenar y sincronizar datos de múltiples documentos.
   - Define mapeos de celdas entre documentos y el archivo central para la sincronización de valores.

==========================
Licencia LGPL-3"
==========================

Sayalex25
