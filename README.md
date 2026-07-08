# Sales A2 — Cambios realizados

Sistema de facturación/ventas en **Django 6** (app `billing`). Este documento resume
las funcionalidades añadidas al **listado de productos** (`ProductListView`):
búsqueda por columna, paginación y exportación a **PDF/Excel** mediante un mixin genérico.

---

## 1. Búsqueda por columna

Se añadió un panel de filtros sobre el listado de productos, con un control adecuado
para cada tipo de dato de la consulta.

**`ProductFilterForm`** — [billing/forms.py](billing/forms.py)

| Columna        | Tipo de dato        | Control                          | Filtro aplicado            |
|----------------|---------------------|----------------------------------|----------------------------|
| Nombre         | texto               | input de texto                   | `name__icontains`          |
| Marca          | FK                  | `<select>` desplegable           | `brand =`                  |
| Grupo          | FK                  | `<select>` desplegable           | `group =`                  |
| Proveedor      | M2M                 | `<select>` desplegable           | `suppliers =`              |
| Precio         | decimal             | rango min/máx (`number`, step .01)| `unit_price__gte / __lte` |
| Stock          | entero              | rango min/máx (`number`)         | `stock__gte / __lte`       |
| Estado         | booleano            | `<select>` (Todos/Activo/Inactivo)| `is_active =`             |

- Todos los campos son **opcionales** (`required=False`).
- `clean()` valida que el **mínimo no supere al máximo** en los rangos de precio y stock.
- El formulario conserva los valores seleccionados tras buscar.

## 2. Paginación

`ProductListView` usa `paginate_by` (configurable). La navegación (First / Prev /
Page X of Y / Next / Last) está en la plantilla y **conserva los filtros activos**
gracias a la variable `querystring` (los parámetros GET sin `page` ni `export`).

## 3. Exportación a PDF y Excel

Botones **PDF** y **Excel** que exportan **exactamente los registros filtrados**
de la consulta (respetan la búsqueda; no se limitan a la página actual).

**`ExportListMixin`** — [billing/mixins.py](billing/mixins.py) (genérico y reutilizable)

- Se activa con `?export=pdf` o `?export=excel` en la URL.
- Reutiliza el `get_queryset()` de la vista, por eso respeta los filtros.
- `export_fields` admite relaciones (`brand.name`), M2M (`suppliers`),
  propiedades/métodos y booleanos (se muestran como `Sí`/`No`).
- **Excel** (`openpyxl`): encabezados resaltados, anchos automáticos, panel congelado.
- **PDF** (`reportlab`): horizontal, título, fecha de generación, nº de registros y tabla con estilos.
- Nombre de archivo con marca de tiempo, p. ej. `Listado_de_Productos_20260615_1611.xlsx`.

Botones reutilizables en el partial [billing/templates/billing/_export_buttons.html](billing/templates/billing/_export_buttons.html).

---

## Archivos creados / modificados

**Nuevos**
- `billing/mixins.py` — `ExportListMixin` (exportación genérica PDF/Excel).
- `billing/templates/billing/_export_buttons.html` — botones reutilizables.

**Modificados**
- `billing/forms.py` — nuevo `ProductFilterForm` (un control por columna).
- `billing/views.py` — `ProductListView` con filtrado, `paginate_by` y `ExportListMixin`.
- `billing/templates/billing/product_list.html` — panel de filtros, columna *Estado*,
  paginación y botones de exportar.

## Dependencias añadidas

```bash
# Nota: este venv fue copiado de otra ruta; instalar con "python -m pip", no con pip.exe
.\ent_sales_a2\Scripts\python.exe -m pip install openpyxl reportlab
```

| Paquete    | Uso                  |
|------------|----------------------|
| `openpyxl` | Generación de `.xlsx`|
| `reportlab`| Generación de PDF    |

(Se instalan también sus dependencias: `et-xmlfile`, `pillow`, `charset-normalizer`.)

## Cómo ejecutar

```bash
.\ent_sales_a2\Scripts\python.exe manage.py runserver
```

Entra a `/products/`: arriba el panel de filtros y los botones PDF/Excel; abajo la paginación.

## Reutilizar la exportación en otros listados

El mixin es genérico. Para habilitar PDF/Excel en cualquier otro `ListView`:

```python
# 1) En la vista
class SupplierListView(ExportListMixin, LoginRequiredMixin, ListView):
    model = Supplier
    export_title = 'Listado de Proveedores'
    export_fields = ['name', 'email', 'phone', 'is_active']   # opcional
    export_headers = ['Empresa', 'Email', 'Teléfono', 'Estado']  # opcional
```

```django
{# 2) En su plantilla #}
{% include 'billing/_export_buttons.html' %}
```

Si no se define `export_fields`, exporta todos los campos del modelo.

---

# App `purchasing` — Módulo de Compras

Nueva app que registra las **compras a proveedores** (lo opuesto a `Invoice`, que
registra ventas a clientes). Reutiliza `Supplier` y `Product` de `billing` en vez
de duplicarlos — ver la sección "Cómo `purchasing` reutiliza `billing`" más abajo.

Sobre esa base ya funcionando (`Purchase`, `PurchaseDetail`, CRUD completo con
`inlineformset_factory`), se implementaron los **4 retos opcionales**:

## Reto 1 — Actualizar stock al comprar

**Dónde:** [purchasing/views.py](purchasing/views.py) — función `purchase_create`.

Una venta (`billing.invoice_create`) **resta** stock; una compra debe **sumarlo**,
porque reabastece el inventario. Tras guardar el formset de líneas:

```python
from django.db.models import F
from billing.models import Product

for detail in saved_details:
    Product.objects.filter(pk=detail.product_id).update(
        stock=F('stock') + detail.quantity
    )
```

**¿Por qué `F('stock') + qty` y no `producto.stock += qty; producto.save()`?**
`F()` le dice a la base de datos "usa el valor que tienes tú ahora mismo", y hace el
`UPDATE` en una sola sentencia SQL (`UPDATE product SET stock = stock + 5 WHERE id = 1`).
Si dos compras del mismo producto llegaran casi al mismo tiempo, leer el valor en Python
y volver a guardarlo (`p.stock += qty; p.save()`) podría perder una de las dos sumas
(condición de carrera). Con `F()` no hay ese riesgo, porque la suma la hace la propia
base de datos, no Python.

## Reto 2 — Evitar document_number duplicado por proveedor

**Dónde:** [purchasing/models.py](purchasing/models.py) — `Purchase.Meta`.

```python
class Meta:
    ...
    constraints = [
        models.UniqueConstraint(
            fields=['supplier', 'document_number'],
            name='unique_supplier_document_number',
        )
    ]
```

Un mismo `document_number` (el número de factura física del proveedor) sí puede
repetirse entre **distintos** proveedores, pero no dos veces para el **mismo**
proveedor. Por eso el constraint es sobre la **pareja** de campos, no sobre uno solo.

Como `PurchaseForm` es un `ModelForm` que incluye ambos campos (`supplier` y
`document_number`), Django valida el constraint automáticamente al llamar a
`form.is_valid()` — no hace falta código extra en la vista. El error se muestra
como `form.non_field_errors` (afecta a la combinación de dos campos, no a uno
solo), por lo que se agregó su renderizado en
[purchase_form.html](purchasing/templates/purchasing/purchase_form.html).

Se generó la migración correspondiente:
```
purchasing/migrations/0002_purchase_unique_supplier_document_number.py
```

## Reto 3 — Filtrar compras por proveedor y por fecha

**Dónde:** [purchasing/forms.py](purchasing/forms.py) (`PurchaseFilterForm`) y
[purchasing/views.py](purchasing/views.py) (`purchase_list`).

Panel de filtros sobre el listado, igual en espíritu al de facturas
(`InvoiceFilterForm` en `billing`):

| Filtro       | Lookup usado                    | Ejemplo de traducción a SQL          |
|--------------|----------------------------------|---------------------------------------|
| Proveedor    | `supplier=`                      | `WHERE supplier_id = X`               |
| Desde + Hasta| `purchase_date__date__range=`    | `WHERE fecha BETWEEN X AND Y`         |
| Solo Desde   | `purchase_date__date__gte=`      | `WHERE fecha >= X`                    |
| Solo Hasta   | `purchase_date__date__lte=`      | `WHERE fecha <= X`                    |
| Año          | `purchase_date__year=`           | `WHERE YEAR(fecha) = X`               |

Todos los campos del formulario son opcionales (`required=False`), así que se
pueden combinar libremente o dejarlos todos vacíos para ver el listado completo.
El `__date` extra antes de `__range`/`__gte`/`__lte` es necesario porque
`purchase_date` es un `DateTimeField` (guarda hora), y se quiere comparar solo
la parte de fecha.

## Reto 4 — Reporte de costo promedio por producto

**Dónde:** [purchasing/views.py](purchasing/views.py) (`purchase_report`) y
[purchase_report.html](purchasing/templates/purchasing/purchase_report.html).

Nueva vista en `/purchases/report/` (botón "Avg. Cost Report" en el listado):

```python
report = (
    PurchaseDetail.objects
    .values('product__name')
    .annotate(avg_cost=Avg('unit_cost'), total_qty=Sum('quantity'))
    .order_by('product__name')
)
```

**Cómo se lee esta consulta:**
1. `values('product__name')` agrupa todas las líneas de compra por nombre de producto
   (equivalente a `GROUP BY product.name` en SQL).
2. `annotate(...)` calcula, por cada grupo, el **promedio** (`Avg`) del costo unitario
   pagado y la **suma** (`Sum`) de las cantidades compradas.
3. El resultado es una tabla: producto → cantidad total comprada → costo promedio.

Sirve para responder: *"¿A cuánto me está costando en promedio comprar este producto,
considerando todas las compras históricas a distintos proveedores?"*

## Cómo `purchasing` reutiliza `billing`

```python
# purchasing/models.py
from billing.models import Supplier, Product
```

No se duplican los modelos `Supplier` ni `Product`: la app `purchasing` los
**importa** directamente desde `billing`. Así, una compra apunta exactamente al
mismo catálogo de proveedores y productos que usan las ventas — si se actualiza
el precio o el stock de un producto, se refleja igual en ambas apps, porque es
la misma tabla en la base de datos.

| Concepto en `billing` (venta)     | Concepto en `purchasing` (compra)  |
|------------------------------------|--------------------------------------|
| `Invoice` (cabecera, a un cliente) | `Purchase` (cabecera, a un proveedor)|
| `InvoiceDetail` (líneas)           | `PurchaseDetail` (líneas)            |
| `unit_price` (precio de venta)     | `unit_cost` (costo de compra)        |
| Venta → **resta** stock            | Compra → **suma** stock (Reto 1)     |

## Rutas de `purchasing`

```
/purchases/                    → purchase_list        (con filtros)
/purchases/create/             → purchase_create       (formset + suma de stock)
/purchases/report/             → purchase_report       (costo promedio por producto)
/purchases/<id>/                → purchase_detail
/purchases/<id>/delete/          → purchase_delete
/purchases/<id>/export/pdf/      → purchase_export_pdf
/purchases/<id>/export/excel/    → purchase_export_excel
```

## Exportación individual de una compra (PDF / Excel)

**Objetivo:** cada registro de `Purchase` (no el listado completo) puede
descargarse como comprobante en PDF o en Excel, con su cabecera (proveedor,
n° de factura, fecha) y todas sus líneas de detalle (producto, cantidad,
costo unitario, subtotal) más los totales (subtotal, IVA, total).

### Cómo se relaciona con `ExportListMixin` (sección 3, arriba)

Es un caso distinto al de `ExportListMixin` y por eso **no se reutiliza tal
cual**:

| | `ExportListMixin` (`billing`) | Exportación individual (`purchasing`) |
|---|---|---|
| Qué exporta | Un **listado** (N filas filtradas) | **Un** `Purchase` con sus líneas |
| Forma del documento | Tabla plana, una fila = un objeto | Documento tipo comprobante: cabecera + tabla de líneas + totales |
| Vistas base | `ListView` (CBV) | Funciones (`purchase_detail`, etc.) — `purchasing` usa FBV, no CBV |
| Se activa con | `?export=pdf`/`?export=excel` sobre la misma URL del listado | URL propia por registro: `/purchases/<id>/export/pdf/` |

Sí se mantiene el **mismo estándar visual y técnico** que `ExportListMixin`,
para que todos los documentos generados por el sistema se vean consistentes:

- Mismas librerías: **`openpyxl`** para `.xlsx` y **`reportlab`** para PDF.
- Mismo color de cabecera de tabla (`#343A40`, blanco y negrita) y mismas
  filas alternas grises en el PDF.
- Mismo criterio de nombre de archivo con marca de tiempo, p. ej.
  `Compra_3_20260706_1424.pdf`.
- Mismas fechas localizadas con `timezone.localtime()` y formato `d/m/Y H:i`.

### Cómo se implementó

**Nuevo:** [purchasing/exports.py](purchasing/exports.py)

- `export_purchase_pdf(purchase)` y `export_purchase_excel(purchase)`: reciben
  el objeto `Purchase` (ya resuelto con `select_related('supplier')` +
  `prefetch_related('details__product')` para evitar N+1) y devuelven un
  `HttpResponse` con el archivo listo para descargar.
- Son **funciones puras** (no un mixin de CBV) porque `purchasing` está
  construido con vistas basadas en función (FBV); así el patrón encaja con el
  resto de la app en vez de forzar una migración a CBV solo para exportar.

**Modificado:** [purchasing/views.py](purchasing/views.py)

```python
@login_required
def purchase_export_pdf(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier').prefetch_related('details__product'),
        pk=pk,
    )
    return export_purchase_pdf(purchase)
```

(`purchase_export_excel` es igual, solo cambia la función de `exports.py` que
llama al final.) Ambas vistas reutilizan el mismo patrón `get_object_or_404`
+ `select_related`/`prefetch_related` que ya usa `purchase_detail`.

**Modificado:** [purchasing/urls.py](purchasing/urls.py) — dos rutas nuevas,
anidadas bajo el `pk` del registro (igual que `purchase_delete`):

```python
path('<int:pk>/export/pdf/', views.purchase_export_pdf, name='purchase_export_pdf'),
path('<int:pk>/export/excel/', views.purchase_export_excel, name='purchase_export_excel'),
```

**Modificado:** botones "PDF"/"Excel" en dos plantillas —
[purchase_list.html](purchasing/templates/purchasing/purchase_list.html)
(un ícono por fila, junto a Ver/Eliminar) y
[purchase_detail.html](purchasing/templates/purchasing/purchase_detail.html)
(botones en el pie de la tarjeta) — cada uno apunta directo a
`{% url 'purchasing:purchase_export_pdf' purchase.pk %}` /
`..._export_excel`, sin parámetros extra (a diferencia de
`_export_buttons.html`, aquí no hay filtros ni columnas que conservar porque
el documento es siempre el mismo registro completo).

No se agregaron dependencias nuevas: `openpyxl` y `reportlab` ya estaban
instaladas para `ExportListMixin`.

## Validación: no aceptar valores negativos en compras

**Bug reportado:** el formulario de líneas de compra aceptaba cantidades y
costos unitarios negativos, generando compras con `subtotal`/`tax`/`total`
negativos (se detectó una Purchase real con total `$-0.08`, ya eliminada).

**Causa:** [purchasing/models.py](purchasing/models.py) —
`PurchaseDetail.quantity` era `PositiveIntegerField` **sin** validador
adicional (Django solo garantiza `>= 0`, es decir el `0` pasaba) y
`unit_cost` era un `DecimalField` **sin ningún validador**, así que
aceptaba cualquier número, incluido negativo.

**Corrección** — [purchasing/models.py](purchasing/models.py):

```python
from django.core.validators import MinValueValidator

quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
unit_cost = models.DecimalField(
    max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))]
)
```

`PurchaseDetailFormSet` (en [purchasing/forms.py](purchasing/forms.py)) es un
`inlineformset_factory` que genera sus campos a partir del modelo, así que
estos validadores se heredan automáticamente en el formulario — no hace
falta tocar `forms.py`. Se generó y aplicó la migración
`purchasing/migrations/0003_alter_purchasedetail_quantity_and_more.py`.

Con esto, `formset.is_valid()` ahora rechaza cantidad `<= 0` o costo
unitario `<= 0` antes de guardar, y el error se muestra por línea en
[purchase_form.html](purchasing/templates/purchasing/purchase_form.html)
(igual que cualquier otro error de campo del formset).

---

# Consola de Roles y Permisos (`security`)

**Objetivo:** la pantalla de "Roles" (`Group` de `django.contrib.auth`) ya no
es una tabla + un formulario aparte. Ahora es **un solo panel dividido**:
la lista de roles a la izquierda y la grilla de permisos del rol
seleccionado a la derecha. Al hacer clic en otro rol (p. ej.
"Administrador"), el panel derecho cambia para mostrar/editar los permisos
de ese rol — sin salir de la pantalla ni abrir un formulario distinto.

Antes de tocar código se hizo un mockup en HTML puro (con datos de ejemplo
y JS sin backend) para acordar el diseño; una vez aprobado, se implementó
sobre los modelos reales del proyecto.

## Cómo se relaciona con el resto del proyecto

No se creó ningún modelo nuevo — todo se apoya en lo que Django ya trae:

| Concepto de la UI | Modelo real |
|---|---|
| "Rol" | `django.contrib.auth.models.Group` |
| "Permiso" (Ver/Crear/Editar/Eliminar) | `django.contrib.auth.models.Permission` |
| Módulo (p. ej. "Producto") | `django.contrib.contenttypes.models.ContentType` |
| Nombre del módulo en pantalla | `content_type.model_class()._meta.verbose_name` — el mismo `verbose_name` ya definido en cada modelo de `billing`/`purchasing` (p. ej. `Product Group`, `Purchase Detail`), no se inventó ningún texto nuevo |

Los 3 roles del sistema (`Administrador`, `Vendedor`, `Analista de Compras`)
y sus permisos siguen creándose igual, con
`security/management/commands/setup_roles.py`. La consola simplemente da
una forma más rápida de **verlos y ajustarlos** después.

## Cómo se implementó

**Rutas:** no se agregó ninguna — se reutilizan las 4 que ya existían en
[security/urls.py](security/urls.py) (`roles/`, `roles/create/`,
`roles/<pk>/edit/`, `roles/<pk>/delete/`).

**[security/views.py](security/views.py):**

- `GroupListView` ya no lista en tabla: `/roles/` redirige directo a editar
  el primer rol (o a crear uno si no existe ninguno). La "lista" ahora vive
  siempre visible en el rail de la propia consola.
- `_permission_matrix(selected_ids)` — agrupa `Permission.objects` por
  `content_type` (modelo) y por acción (`view`/`add`/`change`/`delete`),
  marcando cada permiso como seleccionado o no. Excluye `admin`,
  `contenttypes` y `sessions` (infraestructura de Django sin pantallas de
  negocio en este sistema) y ordena primero `billing`/`purchasing` (lo que
  el Administrador ajusta más seguido) y `auth` al final.
- `_roles_with_colors()` — trae todos los roles con `annotate(Count(...))`
  para el conteo de usuarios/permisos del rail, y les asigna un color
  determinístico (por posición) para diferenciarlos visualmente.
- `GroupConsoleMixin` — contexto compartido por crear y editar: arma
  `all_groups` (rail) y `permission_matrix` (grilla). Si el formulario viene
  con errores (`form.is_bound`), reconstruye la selección desde
  `form['permissions'].value()` en vez de la base de datos, para no perder
  las casillas que el usuario acababa de marcar.
- `GroupCreateView`/`GroupUpdateView` reutilizan el `GroupForm` que ya
  existía (sin cambios en `forms.py`) y ahora redirigen de vuelta a la
  consola del rol (`group_update`) tras guardar, en vez de a una lista.

**Plantilla nueva:** [security/group_console.html](security/templates/security/group_console.html)
(reemplaza a `group_list.html` + `group_form.html`, eliminados).

- La grilla de permisos **no usa el widget por defecto** de
  `CheckboxSelectMultiple` (`{{ form.permissions }}`) porque no se puede
  agrupar por módulo con columnas de color; en su lugar se pintan los
  checkboxes a mano con `name="permissions" value="{{ perm.id }}"`. Esto es
  un patrón estándar de Django: como el `name` y los `value` coinciden con
  lo que espera `ModelMultipleChoiceField`, el `POST` se valida y guarda
  igual que si se hubiera usado el widget automático — no se tocó
  `GroupForm`.
- El campo `name` del rol se muestra como un input de texto integrado en el
  encabezado (en vez de un `<label>` + `<input>` separados), pero sigue
  siendo el mismo campo del formulario.
- Sin JavaScript de estado paralelo: los filtros de rol/módulo y el botón
  "Seleccionar todos" operan directo sobre los checkboxes reales del DOM;
  el contador "N de M permisos" se recalcula escuchando el evento `change`
  del formulario. Cambiar de rol es una navegación normal (`<a href=...>`),
  no una llamada AJAX — no hizo falta ningún endpoint nuevo.
- Colores por acción (Ver=azul, Crear=verde, Editar=ámbar, Eliminar=rojo)
  para distinguir de un vistazo qué tan invasivo es cada permiso.

## Estándar seguido

Mismo patrón que el resto de `security` y `billing`: CBVs (`CreateView`/
`UpdateView`) protegidas con el mixin ya existente `AdminOnlyMixin` (solo
rol Administrador o superusuario), mensajes con `django.contrib.messages`
igual que en `billing_create`/`purchase_create`, y reutilización de
`GroupForm`/`Group`/`Permission`/`ContentType` sin duplicar modelos ni
lógica de validación. No se agregó ninguna dependencia nueva.

---

# PostgreSQL en Docker (antes SQLite)

**Objetivo:** cambiar el motor de base de datos de SQLite a PostgreSQL,
corriendo en un contenedor Docker local. Así el entorno de desarrollo queda
igual al de producción (Render usa PostgreSQL), sin instalar PostgreSQL
directamente en Windows.

## Cómo se hizo

```bash
docker run --name sales_postgres \
  -e POSTGRES_DB=sales_a2 \
  -e POSTGRES_USER=django_user \
  -e POSTGRES_PASSWORD=sales_password \
  -p 5432:5432 \
  -d postgres:15

pip install psycopg2-binary
```

**[config/settings.py](config/settings.py)** — `DATABASES['default']` apunta
al contenedor (`ENGINE: postgresql`, `HOST: localhost`, `PORT: 5432`).

## El problema del "shampoo" de migraciones (y cómo se evitó)

Al limpiar `*/migrations/` para partir con una base ordenada, se borraron por
error migraciones que ya estaban aplicadas en SQLite (`0003_product_image`,
`0004_alter_customer_dni`, etc.) pero se dejó el `0001_initial` **viejo**,
que no incluía esos cambios. Resultado: `models.py` tenía campos
(`Product.image`, `Customer.dni`) que la migración conservada no creaba →
`ProgrammingError: column billing_product.image does not exist`.

**Corrección:** en vez de reconciliar migraciones a mano, se regeneró todo
desde el estado *actual* del código, que es la fuente de verdad:

```bash
# 1) Borrar TODAS las migraciones de billing/purchasing (no solo las nuevas)
rm billing/migrations/0001_initial.py purchasing/migrations/0001_initial.py

# 2) Regenerar migraciones que sí coinciden con models.py tal como está hoy
python manage.py makemigrations billing purchasing

# 3) Base de datos limpia (no había datos reales que perder en Postgres)
#    y aplicar las migraciones nuevas
python manage.py migrate
```

**Regla para el futuro:** nunca dejar un `0001_initial` de una versión
anterior del modelo. O se conservan **todas** las migraciones intermedias,
o se borran **todas** y se regeneran con `makemigrations` contra el
`models.py` actual — nunca una mezcla de las dos cosas.

## Datos de prueba

Al recrear la base de datos se perdieron los datos de prueba (productos,
clientes, facturas de SQLite) — no tenían la misma estructura que el
`models.py` actual, así que no se pudieron migrar directo con
`loaddata`. Se recrearon con:

```bash
python manage.py createsuperuser   # admin_dav
python manage.py setup_roles       # Administrador, Vendedor, Analista de Compras
```

---

# Envío de Correos (bienvenida + factura)

**Objetivo:** enviar un correo automático en dos momentos: (1) cuando se
registra un usuario, y (2) cuando se crea una factura de cliente.

## Cómo se relaciona con el resto del proyecto

- No se creó ningún modelo nuevo — se reutiliza `User.email` y
  `Customer.email` (ya existían).
- Se reutiliza el patrón de `shared/` (igual que `shared/mixins.py`,
  `shared/decorators.py`, `shared/validators.py`): un módulo de utilidades
  sin estado, importado por las apps que lo necesitan, sin duplicar lógica.
- Se llama explícitamente desde la vista, igual que el resto del proyecto
  llama a `messages.success(...)` después de guardar — no se usaron
  *signals* de Django para mantener el flujo explícito y fácil de seguir
  (ver "Por qué no signals" más abajo).

## Cómo se implementó

**Nuevo:** [shared/emails.py](shared/emails.py)

- `send_welcome_email(user)` — arma el correo con el rol asignado
  (`user.groups.all()`) y lo envía a `user.email`.
- `send_invoice_email(invoice)` — arma el correo con las líneas de la
  factura (`invoice.details.select_related('product')`) y los totales, lo
  envía a `invoice.customer.email`.
- Ambas funciones son defensivas: si el destinatario no tiene email
  registrado, o si el envío falla, se registra en el logger `emails` y se
  retorna `False` **sin lanzar excepción** — un problema de correo nunca
  debe tumbar el registro de un usuario ni la creación de una factura.

**Nuevas plantillas** (texto plano, un correo transaccional simple no
necesita HTML):
[templates/emails/user_welcome.txt](templates/emails/user_welcome.txt),
[templates/emails/invoice_created.txt](templates/emails/invoice_created.txt).
Los montos usan `|floatformat:2` porque el objeto `Invoice` recién guardado
guarda en memoria el `Decimal` con más de 2 decimales
(`Decimal('20.00') * Decimal('0.15')` = `Decimal('3.0000')`) hasta que se
vuelve a leer de la base de datos.

**Modificado:**
- [security/views.py](security/views.py) — `RegisterView.form_valid()`
  llama a `send_welcome_email(self.object)` justo después de `login()`.
- [billing/views.py](billing/views.py) — `invoice_create` llama a
  `send_invoice_email(invoice)` justo después de guardar los totales
  finales, antes del `messages.success(...)` y el `redirect`.

**Configuración** — [config/settings.py](config/settings.py):

```python
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'Sales System <noreply@salessystem.local>'
```

En desarrollo los correos se **imprimen en la terminal** donde corre
`runserver` (no hace falta SMTP real para probar el flujo). Para producción
(Render), cambiar a SMTP real, por ejemplo con Gmail y variables de entorno:

```python
if not DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.gmail.com'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.environ['EMAIL_USER']
    EMAIL_HOST_PASSWORD = os.environ['EMAIL_PASSWORD']  # contraseña de aplicación de Gmail
```

## Por qué no *signals*

Se evaluaron dos estándares: `signals` (Django dispara el correo solo, al
guardar el modelo) contra llamada explícita en la vista. Se eligió la
llamada explícita porque:

- El proyecto no usa signals en ningún otro lado — la auditoría
  (`shared/decorators.py::audit_action`) y el descuento de stock en
  compras/ventas ya se hacen con llamadas explícitas en la vista, no con
  hooks implícitos. Mantener un solo estilo hace el código más predecible.
- Es más fácil de explicar y depurar: la línea `send_invoice_email(invoice)`
  está justo al lado de donde se calculan los totales, no "escondida" en
  otro archivo que se dispara automáticamente.

## Verificación

Se probó el flujo completo (no solo import/sintaxis): se registró un
usuario de prueba con rol "Vendedor" y se generó una factura de prueba vía
`Client()` de Django, confirmando que ambos correos se imprimen en consola
con el asunto, destinatario y cuerpo esperados, y luego se limpiaron los
datos de prueba de la base de datos.

---

# Registro restringido: solo el Administrador crea usuarios

**Objetivo:** eliminar el autorregistro público. Antes, cualquier
visitante podía crearse una cuenta (y elegir su propio rol) desde
`/security/register/` o desde `/signup/`. Ahora solo un usuario con rol
Administrador puede crear cuentas nuevas.

## Lo que había que arreglar (dos rutas públicas, no una)

El proyecto tenía **dos** formularios de registro coexistiendo, uno de una
versión anterior del proyecto (antes de que existiera la app `security`):

| Ruta | Vista | Problema |
|---|---|---|
| `/signup/` | `billing.SignUpView` | Sin selección de rol, sin correo de bienvenida, quedó huérfana tras crear `security` |
| `/security/register/` | `security.RegisterView` | Pública, con rol, era la usada desde el navbar |

Dejar cualquiera de las dos abiertas habría dejado una puerta trasera para
crear cuentas sin pasar por el Administrador. Se eliminaron **ambas**.

## Cómo se implementó

**Eliminado por completo** (código muerto tras el cambio):
`billing.SignUpView`, `billing.SignUpForm`, la ruta `signup/` en
[billing/urls.py](billing/urls.py), y
`templates/registration/signup.html`.

**[security/views.py](security/views.py)** — `RegisterView` (pública) se
convirtió en `UserCreateView`, protegida con el mismo `AdminOnlyMixin` que
ya usan `GroupCreateView`/`PermissionCreateView`. Dos detalles importantes:

- **Ya no llama a `login(self.request, self.object)`.** La vista vieja
  iniciaba sesión automáticamente como el usuario recién creado porque
  asumía que la persona se estaba registrando a sí misma. Ahora quien
  llama a esta vista es el Administrador creando una cuenta *para otra
  persona* — si se dejaba el `login()`, el Administrador habría perdido su
  propia sesión y quedado logueado como el usuario nuevo. Se verificó con
  una prueba explícita que la sesión del admin no cambia tras crear un
  usuario.
- Sigue llamando a `send_welcome_email(self.object)` — el correo de
  bienvenida no depende de quién creó la cuenta.

**[security/forms.py](security/forms.py)** — `UserRegisterForm` se renombró
a `UserCreateForm` (ya no es de "registro", es de "creación" por el admin);
el formulario en sí no cambió.

**[security/urls.py](security/urls.py)** — se quitó `register/` y se agregó
`users/create/` (`user_create`), agrupada junto a `user_list`/`user_update`/
`user_delete` en vez de junto a login/logout, porque ahora es una operación
de gestión de usuarios, no de autenticación.

**Plantillas:**
- `security/register.html` se eliminó — `UserCreateView` reutiliza
  [security/user_form.html](security/templates/security/user_form.html)
  (el mismo que ya usaba `UserUpdateView`), genericizado con una variable
  `{{ title }}` (vía `extra_context`) para mostrar "Create User" o "Edit
  User" según corresponda, en vez de duplicar el formulario en dos
  archivos casi idénticos.
- [security/user_list.html](security/templates/security/user_list.html) —
  se agregó el botón **"+ New User"** (antes no existía ninguna forma de
  crear un usuario desde la lista, porque se dependía del registro
  público).
- [billing/templates/billing/base.html](billing/templates/billing/base.html)
  — se quitó el link "Sign Up" del navbar para anónimos.
- [templates/registration/login.html](templates/registration/login.html) —
  se cambió "¿No tienes cuenta? Regístrate" por un texto que indica que hay
  que pedírsela al Administrador.

## Verificación

Se probaron los 4 casos relevantes con `Client()` de Django (no solo que
compile):
1. `/security/register/` y `/signup/` devuelven **404** (ya no existen).
2. Un visitante anónimo que intenta `/security/users/create/` es
   redirigido a login.
3. Un usuario logueado **sin** rol Administrador (probado con "Vendedor")
   es redirigido — no puede crear usuarios.
4. Un Administrador sí puede: el usuario se crea con el rol correcto, le
   llega el correo de bienvenida, **la sesión del admin no cambia**
   (verificado comparando el `_auth_user_id` de la sesión antes y después),
   y redirige a la lista de usuarios.

---

# Contraseña temporal al crear usuario (obligación de cambiarla)

**Objetivo:** cuando el Administrador crea una cuenta, puede elegir entre
escribir la contraseña él mismo o dejar que el sistema genere una
automática y fácil de recordar. En ambos casos, la contraseña la eligió
alguien que no es el dueño de la cuenta — así que el sistema obliga a
cambiarla la primera vez que esa persona inicia sesión, antes de dejarla
usar cualquier otra pantalla.

## La fórmula de la contraseña automática

Inicial del primer nombre + primer apellido completo + inicial del segundo
apellido, todo en minúsculas:

```
Davis Steven / Yanez Gualpa  →  d + yanez + g  →  "dyanezg"
```

Implementada en `generate_temp_password()` en
[security/forms.py](security/forms.py). Normaliza tildes/ñ (con
`unicodedata`) para que la contraseña no tenga caracteres raros.

## Por qué no pasa por el validador de fortaleza de Django

Django ya trae `AUTH_PASSWORD_VALIDATORS` (longitud mínima, no parecerse al
usuario, etc.) — y una contraseña como `"dyanezg"` los reprueba **todos**
a propósito (es corta y se parece al nombre). Eso es exactamente lo que se
pidió ("fácil"), así que en vez de bajar los estándares de seguridad para
*todas* las contraseñas del sistema, `UserCreateForm._post_clean()` se
salta esa validación **únicamente** cuando se usó la automática:

```python
def _post_clean(self):
    if self.cleaned_data.get('auto_password'):
        forms.ModelForm._post_clean(self)  # construye el modelo, sin validar fortaleza
    else:
        super()._post_clean()  # UserCreationForm: sí valida fortaleza
```

Si el admin escribe la contraseña a mano (checkbox destildado), sigue
pasando por la validación normal de Django — se probó explícitamente que
una contraseña manual débil (`"123"`) es rechazada, mientras que la
automática con ese mismo nivel de "debilidad" se acepta a propósito.

## Cómo se implementó el "debe cambiarla en el primer login"

Django no trae esto de fábrica — se necesitó una bandera persistida y algo
que la revise en cada request:

**[security/models.py](security/models.py)** (nuevo, la app `security` no
tenía modelos propios hasta ahora) — `UserSecurityProfile`, `OneToOne` con
`User`, con un solo campo: `must_change_password`.

**[security/middleware.py](security/middleware.py)** (nuevo) —
`ForcePasswordChangeMiddleware`: en cada request, si el usuario logueado
tiene `must_change_password=True`, lo redirige a
`security:force_password_change` sin importar a dónde intentaba ir
(excepto a esa misma página y a logout, para no dejarlo atrapado sin
salida). Registrado en `MIDDLEWARE` justo después de
`AuthenticationMiddleware` (necesita `request.user`, que ese middleware ya
resolvió) — [config/settings.py](config/settings.py).

**[security/views.py](security/views.py)**:
- `UserCreateView.form_valid()` ahora, después de guardar el usuario,
  hace `UserSecurityProfile.objects.update_or_create(user=..., must_change_password=True)`
  y pasa la contraseña usada (`form.cleaned_data['password1']`, automática
  o manual) a `send_welcome_email()`.
- `ForcePasswordChangeView` — extiende el `PasswordChangeView` que ya trae
  Django (pide la contraseña actual + la nueva dos veces, con la misma
  validación de fortaleza de siempre). Al guardar, apaga
  `must_change_password` para que el middleware deje de interceptarlo.

**[shared/emails.py](shared/emails.py)** — `send_welcome_email()` ahora
acepta un `temp_password` opcional; si viene, el correo
([templates/emails/user_welcome.txt](templates/emails/user_welcome.txt))
muestra la contraseña y el aviso de que hay que cambiarla al entrar.

**[security/templates/security/user_form.html](security/templates/security/user_form.html)**
— un poco de JS oculta los campos de contraseña manual cuando se marca
"Generar automáticamente" (mejora de UX; si el navegador no ejecuta el JS,
el formulario igual funciona server-side porque `clean()` sobrescribe
`password1`/`password2` cuando `auto_password` está marcado).

## Verificación

Probado end-to-end con `Client()` de Django (no solo que compile):
1. La fórmula genera exactamente `"dyanezg"` para el ejemplo dado, y maneja
   nombres con un solo apellido y con tildes/ñ.
2. Crear un usuario con contraseña automática: la contraseña real
   (`check_password('dyanezg')`) funciona, el correo la incluye, y queda
   `must_change_password=True`.
3. Ese usuario, al loguearse e intentar ir a **cualquier** URL (`/`,
   `/products/`), es redirigido siempre a la pantalla de cambio de
   contraseña — hasta que la cambia, después de lo cual navega con
   normalidad y `must_change_password` pasa a `False`.
4. Contraseña manual débil (`"123"`) es rechazada (Django sí valida en
   este camino); una manual válida se acepta con su propio valor exacto
   (no con la fórmula automática), y también exige cambio en el primer login.
