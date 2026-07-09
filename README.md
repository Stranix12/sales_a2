# Sales A2 — Cambios realizados

Sistema de facturación/ventas en **Django 6** (app `billing`). Este documento resume
las funcionalidades añadidas al **listado de productos** (`ProductListView`):
búsqueda por columna, paginación y exportación a **PDF/Excel** mediante un mixin genérico.

---

## Estado actual del proyecto (leer esto primero)

Para orientarse rápido sin tener que leer todo el documento. El resto del
README está organizado **cronológicamente por feature**, cada uno con su
"por qué" — esta sección es solo el resumen ejecutivo.

**Desplegado y funcionando en producción:**
- App en Render: `https://sales-a2.onrender.com` (Blueprint: `render.yaml`,
  repo: `https://github.com/Stranix12/sales_a2`)
- Base de datos: **PostgreSQL** (local: contenedor Docker `sales_postgres`;
  producción: addon de Postgres de Render, conectado vía `DATABASE_URL`)
- Correo transaccional real vía **Brevo** (API HTTP, no SMTP — ver por qué
  en "Envío de Correos" más abajo), a un correo real, confirmado funcionando
- Roles y permisos: consola de un panel (`security/group_console.html`)
- Registro de usuarios: **solo el Administrador** puede crear cuentas,
  con contraseña automática opcional + obligación de cambiarla al primer login
- Exportación PDF/Excel: listados (`billing`, mixin genérico) y compras
  individuales (`purchasing/exports.py`)

**Pendiente / no empezado todavía** (visto en conversaciones pero sin código):
- **Facturación Electrónica** (Ecuador, sin conexión real al SRI): agregar
  `payment_status`/`payment_date`/`payment_method`/`numero_factura` a
  `Invoice`, campos `cedula_ruc`/`direccion` a `Customer`, modelos nuevos
  `ElectronicReceipt` y `PaymentLog`, vista "Marcar como Pagado", generar
  PDF de factura (reutilizar el patrón de `purchasing/exports.py`) y
  enviarlo por correo al pagar.
- **PayPal** (bonus/puntos extra): se conectaría al flujo de "Marcar como
  Pagado" de arriba.
- Cargar datos de prueba reales (productos/clientes) — la base quedó vacía
  tras la migración a Postgres.

**Solo en local, todavía SIN subir a GitHub/Render** (a propósito, por
instrucción del usuario — se subirá cuando haya más cambios):
- **Rediseño visual completo**: se eliminó Bootstrap por completo y se
  reemplazó por un **design system propio** (`billing/static/billing/app.css`
  + `app.js`). Menú agrupado en desplegables (Compras / Ventas / Security),
  notificaciones tipo *toast* animadas, y modales/dropdowns con JS vanilla
  propio. Ver la sección "Rediseño: design system propio (sin Bootstrap)"
  al final de este README.

**Gotchas / cosas raras que le pasaron a este proyecto** (por si se repiten):
- **Dos copias del proyecto en el disco**: `C:\Users\Davis\Documents\sales_a2`
  (venv viejo) y `C:\Users\Davis\Pictures\sales_a2` (el real, donde se
  trabaja). Si un `python manage.py runserver` falla con
  `ModuleNotFoundError` mencionando rutas de `Documents\...`, es que el
  venv activo es el equivocado. Solución más confiable: ejecutar con la
  ruta completa, `C:\Users\Davis\Pictures\sales_a2\ent_sales_a2\Scripts\python.exe manage.py runserver`,
  en vez de depender de `activate`.
- El venv (`ent_sales_a2`) fue copiado/movido de ruta alguna vez: instalar
  paquetes con `python -m pip install ...`, **no** con `pip.exe` directo
  (puede apuntar a la ruta vieja).
- **Render bloquea SMTP saliente** (puerto 587/465) — por eso el envío de
  correos en producción usa la API HTTP de Brevo (`django-anymail`), no
  `smtplib`. Ver la sección "Envío de Correos" para el detalle completo.
- El plan **free de Render no incluye Shell interactivo** — el superusuario
  se crea automáticamente en cada build vía variables de entorno
  (`DJANGO_SUPERUSER_*`), no a mano.

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

# Despliegue en Render

**Objetivo:** publicar el proyecto en `https://sales-a2.onrender.com` desde
el repo de GitHub (`https://github.com/Stranix12/sales_a2`), con
PostgreSQL real (no la de Docker local) y correo real (no consola).

## El Blueprint (`render.yaml`)

En vez de crear el Web Service y la base de datos a mano en el dashboard,
[render.yaml](render.yaml) los declara juntos — Render los lee al conectar
el repo (**New → Blueprint Instance**) y los crea/conecta solos:

```yaml
databases:
  - name: sales-a2-db          # crea el Postgres administrado de Render
    databaseName: sales_a2
    user: django_user
    plan: free

services:
  - type: web
    name: sales-a2
    env: python
    buildCommand: "pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate && python manage.py setup_roles && (python manage.py createsuperuser --noinput || true)"
    startCommand: "gunicorn config.wsgi:application"
    envVars:
      - key: DATABASE_URL
        fromDatabase: {name: sales-a2-db, property: connectionString}  # conecta sola la BD de arriba
      - key: SECRET_KEY
        generateValue: true       # Render genera uno real, no el de desarrollo
      - key: DEBUG
        value: "False"
      # BREVO_API_KEY, DEFAULT_FROM_EMAIL, DJANGO_SUPERUSER_* : sync: false
      # (secretos — Render los pide al aplicar el Blueprint, no viven en el yaml)
```

## Por qué el superusuario se crea en el `buildCommand`, no a mano

El plan **free de Render no incluye Shell interactivo** (es función de
pago). La alternativa: Django's `createsuperuser --noinput` ya sabe leer
`DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` de variables de
entorno. Se agregó al `buildCommand`, que sí corre gratis en cada deploy.

Problema: en el **segundo** deploy en adelante, el usuario ya existe y el
comando falla (`CommandError: ... already taken`), lo que tumbaría *todo*
el build. Por eso va envuelto así: `(python manage.py createsuperuser --noinput || true)`
— el paréntesis limita el `|| true` a *solo* ese comando (si `pip install`
o `migrate` fallan, el build sí debe fallar de verdad; solo el "ya existe"
de `createsuperuser` se ignora). Se probó explícitamente corriendo el
comando dos veces seguidas en local: la 1ª crea el usuario, la 2ª falla
con exit code 1 tal como se esperaba.

`setup_roles` va antes que `createsuperuser` en la misma cadena porque ya
es idempotente (`get_or_create` en
[security/management/commands/setup_roles.py](security/management/commands/setup_roles.py)),
así que no necesita ningún truco para poder correr en cada build.

## Variables de entorno que hay que llenar a mano en el dashboard

Las marcadas `sync: false` en el yaml no tienen valor por defecto —
Render las pide como texto en blanco al aplicar el Blueprint, o se
agregan después en **Environment**:

| Variable | De dónde sale |
|---|---|
| `BREVO_API_KEY` | Brevo → SMTP & API → pestaña **API Keys** (no la de SMTP) |
| `DEFAULT_FROM_EMAIL` | Un remitente **verificado** en Brevo → Senders (formato `Nombre <correo@dominio.com>`) |
| `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | Los que se quieran para el admin de producción |

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

- `send_welcome_email(user, temp_password=None, login_url=None)` — arma el
  correo con el rol asignado (`user.groups.all()`) y lo envía a
  `user.email`. Los parámetros `temp_password`/`login_url` se agregaron
  después, cuando se implementó la contraseña temporal — ver la sección
  "Contraseña temporal al crear usuario" más abajo para el detalle completo.
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
- [security/views.py](security/views.py) — `UserCreateView.form_valid()`
  llama a `send_welcome_email(...)` después de guardar (originalmente esto
  vivía en `RegisterView`, la vista de autorregistro pública que ya no
  existe — ver "Registro restringido" más abajo).
- [billing/views.py](billing/views.py) — `invoice_create` llama a
  `send_invoice_email(invoice)` justo después de guardar los totales
  finales, antes del `messages.success(...)` y el `redirect`.

**Configuración** — [config/settings.py](config/settings.py):

```python
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'Sales System <noreply@salessystem.local>'
```

En desarrollo los correos se **imprimen en la terminal** donde corre
`runserver` (no hace falta SMTP real para probar el flujo).

## Producción: Brevo por API HTTP, no por SMTP (y no Gmail)

La primera versión de este proyecto planeaba usar SMTP real en producción
(Gmail, o Brevo por SMTP) — **ninguna de las dos funcionó**, por dos
motivos completamente distintos, en este orden:

1. **Gmail rechazó las contraseñas de aplicación** en la cuenta usada para
   pruebas (`"La opción de configuración que buscas no está disponible
   para tu cuenta"` al entrar a myaccount.google.com/apppasswords) — pasa
   en cuentas nuevas o sin la verificación en 2 pasos activada. Se cambió
   a Brevo (300 correos/día gratis, sin ese requisito).
2. **Render bloquea las conexiones salientes por SMTP** (puertos 587/465).
   Con Brevo por SMTP, el correo se veía "enviado" en la app (sin error),
   pero Brevo nunca recibía nada — el log de Render mostraba
   `[CRITICAL] WORKER TIMEOUT` y el proceso de Gunicorn moría a medio
   enviar: `smtplib` se quedaba colgado en `socket.connect()` esperando
   una conexión que Render nunca dejaba completarse, hasta que Gunicorn
   mataba el worker por timeout (30s). No fallaba rápido con un error
   claro — se colgaba, lo cual es la señal típica de un puerto bloqueado
   por firewall (el paquete SYN se descarta en silencio).

**La solución fue evitar el puerto SMTP por completo**, no alargar el
timeout: Brevo también ofrece una **API HTTP** (`api.brevo.com`, puerto
443 — el mismo que usa cualquier navegador, nunca bloqueado). Se instaló
[`django-anymail`](https://github.com/anymail/django-anymail) (lo estándar
en Django para mandar correo por la API de un proveedor en vez de SMTP):

```python
# config/settings.py
if not DEBUG:
    EMAIL_BACKEND = 'anymail.backends.brevo.EmailBackend'
    ANYMAIL = {'BREVO_API_KEY': os.environ.get('BREVO_API_KEY', '')}
```

Se verificó en local que, con una API key inválida a propósito, el fallo
es **inmediato** (0.7 segundos, con el error real `401 Unauthorized: Key
not found` devuelto por Brevo) en vez de colgarse — confirma que el
problema original era específicamente el puerto SMTP, no la lógica de
`shared/emails.py` (que no cambió: `send_mail()` de Django funciona igual
sin importar qué backend esté configurado).

**Además hace falta un remitente verificado en Brevo** (Senders, Domains &
Dedicated IPs → Senders): usar `noreply@algo-inventado.com` como
`DEFAULT_FROM_EMAIL` lo rechaza. Tiene que ser un correo real que se
pueda verificar ahí (ej. `Sales System <tucorreo@gmail.com>`).

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

## Ajuste 1: link de login en el correo

El correo de bienvenida decía "inicia sesión" pero no daba ningún link
para hacerlo. Se agregó uno absoluto, construido en la vista (no en
`shared/emails.py`, que no tiene acceso al `request`):

```python
# security/views.py — UserCreateView.form_valid()
login_url = self.request.build_absolute_uri(reverse('login'))
send_welcome_email(self.object, temp_password=temp_password, login_url=login_url)
```

`build_absolute_uri()` arma la URL completa (`http://127.0.0.1:8000/...`
en local, `https://sales-a2.onrender.com/...` en producción) usando el
dominio real de la request — funciona igual en ambos entornos sin
hardcodear ningún dominio. En Render, como `SECURE_PROXY_SSL_HEADER` ya
estaba configurado (ver sección de HTTPS en "Despliegue en Render" — en
realidad vive en la sección de PostgreSQL/settings de más arriba, junto a
`SECURE_SSL_REDIRECT`), la URL sale con `https://` correctamente aunque
Render hable con Gunicorn por HTTP puertas adentro.

## Ajuste 2: ocultar el navbar mientras falta cambiar la contraseña

`ForcePasswordChangeMiddleware` ya bloqueaba **entrar** a cualquier otra
página, pero [billing/templates/billing/base.html](billing/templates/billing/base.html)
seguía dibujando el navbar completo (Brands, Customers, Security, todo)
según el rol del usuario — confuso, porque cada link ahí simplemente
rebotaba de vuelta a la pantalla de cambio de contraseña.

Se envolvió **todo** el bloque de links autenticados (no cada uno por
separado) en una sola condición:

```django
{% if user.is_authenticated %}
  {% if user.security_profile.must_change_password %}
    <li class="nav-item"><span class="nav-link text-warning">Debes cambiar tu contraseña para continuar</span></li>
  {% else %}
    {# ... todos los links de siempre, sin cambios ... #}
  {% endif %}
{% endif %}
```

`user.security_profile` es un `OneToOneField` inverso — si el usuario no
tiene `UserSecurityProfile` (todos los usuarios creados antes de esta
feature, como `admin_dav`), Django lanza `RelatedObjectDoesNotExist`, pero
esa excepción hereda de `AttributeError` a propósito (para que
`{% if %}` en templates la trate como "no existe" en vez de reventar) —
por eso no hizo falta ningún `{% if %}` extra para usuarios viejos, el
navbar simplemente se muestra normal para ellos.

Probado con tres escenarios reales (`Client()` de Django): usuario sin
perfil ve el navbar completo (retrocompatible), usuario con
`must_change_password=True` no ve **ningún** link (solo el aviso), y ese
mismo usuario, tras cambiar la contraseña, vuelve a ver el navbar según su
rol real (probado con "Vendedor": ve Customers/Invoices, no ve
Brands/Security).

---

# Ajuste 3: la consola de roles quedaba encajonada

Reportado en producción (Render) con capturas reales: la consola de
roles/permisos ([security/group_console.html](security/templates/security/group_console.html))
se veía metida en un recuadro angosto en vez de ocupar la pantalla — dos
problemas distintos, arreglados en dos pasos.

## Problema 1: ancho fijo (Bootstrap `.container`)

[billing/templates/billing/base.html](billing/templates/billing/base.html)
envuelve **todo** el contenido de **todas** las páginas en un
`<div class="container mt-4">` — Bootstrap limita `.container` a un ancho
máximo (~1200-1300px) sin importar qué tan ancha sea la pantalla. Bien
para formularios y tablas normales, mal para un panel de dos columnas
pensado para usar el espacio disponible.

**Arreglo:** se agregó un `{% block container_class %}container{% endblock %}`
en `base.html` (por defecto sigue siendo `"container"`, así que **ninguna
otra página cambia**), y `group_console.html` lo sobreescribe:

```django
{% block container_class %}container-fluid px-4{% endblock %}
```

Verificado que el resto de páginas (ej. `/purchases/`) siguen renderizando
`class="container mt-4"` sin cambios.

## Problema 2: hueco vertical enorme (número de píxeles adivinado)

El primer intento de que la consola llenara el alto de la pantalla usó
`height: calc(100vh - 185px)` — un número inventado a partir de una
suposición de cuánto miden el navbar + el título. En la pantalla real del
usuario esa suma no daba 185px, así que sobraba un hueco en blanco enorme
debajo de la consola.

**Arreglo:** flexbox real en vez de otro número adivinado. Se le agregó
`id="page-content"` al div contenedor en `base.html` (inofensivo para
las demás páginas), y en `group_console.html`:

```css
/* Todo esto scoped SOLO a esta página, vía :has(.rp-console) — el resto
   de páginas no se entera de este cambio. */
body:has(.rp-console) {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
body:has(.rp-console) > nav.navbar { flex: 0 0 auto; }
body:has(.rp-console) > #page-content {
  flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0;
}
.rp-console { flex: 1 1 auto; min-height: 460px; /* ...resto igual... */ }
```

Con esto, `.rp-console` siempre llena exactamente el espacio que sobra
bajo el navbar y el título — cualquiera que sea, en cualquier pantalla —
sin volver a depender de un cálculo en píxeles que se puede desincronizar
apenas cambie el tamaño de fuente, el navbar, o el zoom del navegador.

**Nota:** `:has()` es selector CSS relativamente nuevo pero con soporte
universal en navegadores modernos (Chrome, Edge, Safari, Firefox) a esta
fecha — no se agregó ningún fallback para navegadores muy viejos porque
no aplica a este proyecto.

Ambos arreglos (ancho y alto) ya están en GitHub/Render (commits
`3e3329f` y `d5a7ee7`). Esta actualización del README en sí es solo local
(a propósito, por instrucción explícita) — falta un `git push` de
`README.md` cuando se quiera sincronizar el repo remoto con esta
documentación.

---

# Rediseño: design system propio (sin Bootstrap)

> **Estado:** hecho y probado **solo en local**. **No** está en GitHub ni
> Render todavía (a propósito, por instrucción del usuario: "no subas ni al
> git ni a render hasta hacer más cambios"). Cuando se quiera desplegar, hay
> que hacer `git push` de los archivos nuevos/modificados listados abajo.

El objetivo fue un aspecto más profesional y "de producto", no de plantilla
Bootstrap genérica. Se hizo en tres pasos, en este orden.

## Paso 1: tema global + navbar + notificaciones animadas

Se creó un archivo CSS que se carga desde `base.html` y por lo tanto aplica a
**todas** las páginas sin editar plantilla por plantilla. Aportó:

- Paleta índigo (`#33459b`, la misma de la consola de roles, para que todo se
  sienta un solo producto), fondo gris azulado, tarjetas con sombras suaves.
- Navbar con logo (insignia), ícono por sección, **resaltado de la sección
  activa** (píldora), y chip de usuario con avatar (inicial del username).
- **Notificaciones tipo *toast***: los mensajes de Django (`messages`) ya no
  son una alerta estática. Ahora entran deslizándose desde la derecha arriba,
  muestran una barra de progreso y **se auto-descartan a los ~4.5 s** (hover
  las pausa; hay una × para cerrarlas antes). El markup lo genera `base.html`
  a partir de `messages`, el estilo y la animación están en el CSS, y el
  cierre lo maneja el JS. **Esto responde al pedido del usuario** de que la
  alerta de "se creó X correctamente" apareciera un momento y desapareciera
  sola, con animación.

> Nota: la duración es de **segundos**, no minutos. El usuario dijo "minutos"
> pero el estándar UX es unos segundos; si se quiere más largo, es cambiar el
> `4.5s` de `@keyframes toastBar` / `.app-toast-bar` en `app.css`.

## Paso 2: menú agrupado por rol (Compras / Ventas / Security)

El menú era una fila larga y plana (Home, Brands, Groups, Suppliers, Products,
Purchases, Customers, Invoices, Security). Se agrupó en **desplegables**, y se
eligió agrupar **por rol de negocio** (no por app de Django) para que coincida
con el gating de permisos que ya existía:

- **Compras** (Analista de Compras / Admin): Brands, Groups, Suppliers,
  Products y —tras un separador— Purchases.
- **Ventas** (Vendedor / Admin): Customers, Invoices.
- **Security** (solo Admin): Users, Roles, Permissions.

Cada `{% if user|has_group:... %}` que ya envolvía los links se conservó tal
cual: un usuario solo ve los desplegables de su rol. Solo cambió la
presentación (de `nav-link` sueltos a `dropdown-menu`).

## Paso 3: eliminar Bootstrap por completo → framework propio

Este fue el cambio grande. El usuario pidió "usa todo lo que sea necesario y
mejor que bootstrap"; se eligió (con confirmación suya) un **design system
propio en CSS**, en vez de Tailwind (que exigiría añadir Node/build al deploy
de Render) o cambiar a otro framework genérico.

**Archivos nuevos:**

- **`billing/static/billing/app.css`** — un solo archivo, sin dependencias ni
  build. Reimplementa, con estética propia, el subconjunto de Bootstrap que
  las plantillas realmente usaban:
  - *Tokens* (variables CSS): colores, escala de espaciado, radios, sombras,
    tipografía (stack de sistema, sin fuentes externas).
  - *Grid* propio de 12 columnas con breakpoints `sm/md/lg` y gutters
    (`.row`, `.col-*`, `.g-*`) — mismo comportamiento que Bootstrap.
  - *Utilidades* de flex, spacing (`m*/p*`), display, texto y color.
  - *Componentes*: cards, botones (sólidos, outline, y las "tintas suaves" de
    las acciones de tabla), badges, tablas, formularios (inputs, selects,
    checks y **switches dibujados a mano en SVG** vía `background-image`),
    paginación, breadcrumb, alertas, navbar, dropdowns, modales y toasts.
- **`billing/static/billing/app.js`** — reemplaza el bundle JS de Bootstrap en
  **JavaScript vanilla**, respetando **los mismos atributos `data-bs-*`** que
  ya traían las plantillas (por eso no hubo que editar las ~30 plantillas):
  desplegables, modales, menú hamburguesa móvil (`collapse`), cierre de
  alertas, más los toasts y el resaltado de sección activa.

**Cambios en `base.html`:** se quitaron los dos `<link>`/`<script>` del CDN de
Bootstrap y se enlazó `app.css` + `app.js`. (Se mantiene el CDN de
**bootstrap-icons** solo por los íconos `bi bi-*`; eso es una fuente de
íconos, no el framework CSS.)

**Clave del enfoque — por qué no se reescribieron las plantillas:** al
conservar los nombres de clase (`card`, `btn btn-primary`, `row`, `col-md-3`,
`table`, `badge`, `form-control`, …) y los atributos `data-bs-*`, solo cambió
el *motor* visual por debajo. El HTML de las páginas quedó intacto, pero ahora
el CSS es 100% propio y personalizable pixel a pixel.

Se eliminó el `theme.css` del Paso 1: todo quedó consolidado en `app.css`.

## Bugs del rediseño que se encontraron y arreglaron

1. **Títulos invisibles en cabeceras oscuras.** La regla base
   `h1..h6 { color: var(--ink) }` (oscuro) pisaba el `.text-white` heredado,
   así que el `<h5>` "Campos visibles" del modal —y los títulos de las
   tarjetas del Home con `bg-dark text-white`— salían texto oscuro sobre fondo
   oscuro (invisibles). **Arreglo:** `h1..h6 { color: inherit }`, para que el
   título tome el color del contexto (blanco dentro de `.bg-dark`/`.text-white`,
   oscuro por defecto).

2. **El modal "se quedaba opaco y no dejaba hacer nada".** Diagnóstico en dos
   partes:
   - La primera versión usaba un elemento `.modal-backdrop` separado por
     **debajo** del contenedor `.modal` (transparente, `position:fixed;
     inset:0`, z-index mayor). Ese contenedor transparente interceptaba los
     clics, y el cierre "clic afuera" estaba puesto en el backdrop → nunca se
     disparaba. Además el botón **Aplicar** del pie se cortaba en pantallas
     bajas.
   - **Arreglo (rediseño del modal):** se eliminó el backdrop aparte. Ahora
     **el propio `.modal` es la capa oscura** (`background: rgba(...,.55)`,
     `display:flex` para centrar el diálogo). El cierre "clic afuera" se
     escucha en el contenedor y dispara solo si `e.target === modal` (igual
     que hace Bootstrap). El `.modal-content` tiene
     `max-height: calc(100vh - 3rem)` con cabecera/pie fijos
     (`flex:0 0 auto`) y **cuerpo con scroll interno** (`flex:1 1 auto;
     overflow-y:auto`), así el pie (Aplicar) **nunca** se corta.
   - Cierre disponible por **×**, **clic en la zona oscura** o **Esc**.

> **Caché del navegador:** al probar cambios de `app.js`/`app.css` en local,
> usar **Ctrl+Shift+R** (recarga forzada). En una de las iteraciones el CSS
> nuevo sí se cargó (el título ya se veía) pero el JS venía cacheado, dando la
> impresión de que "seguía igual".

## Archivos tocados en este rediseño (para el `git add` futuro)

```
billing/static/billing/app.css     (nuevo)
billing/static/billing/app.js      (nuevo)
billing/static/billing/theme.css   (creado y luego ELIMINADO)
billing/templates/billing/base.html
billing/templates/billing/home.html
templates/registration/login.html
```

Las demás plantillas (listados, formularios, consola de roles) **no se
tocaron**: siguen usando las mismas clases, ahora servidas por `app.css`.

---

# Rediseño (2): listados premium, dashboard con gráficas y Security

> Continuación del rediseño anterior. Todo con el mismo design system propio
> (`app.css` + `app.js`), sin dependencias nuevas.

## Listados "premium"

Los listados se sentían muy "estándar" (tabla rayada + barra de botones). Se
elevó el patrón (por ahora en **Products**, y en **Users**/**Permissions** de
Security) con clases nuevas en `app.css`:

- **`.page-head`**: encabezado con ícono, título y un **chip de conteo**
  ("N registros"), más una toolbar de acciones.
- **`.filter-card`**: el panel de filtros como tarjeta limpia con cabecera.
- **`.data-table`**: contenedor con encabezado oscuro, filas con hover, y
  **acciones por fila como íconos** (`.act-btn` ver/editar/eliminar) que están
  tenues y se resaltan al pasar el mouse por la fila.
- **`.cell-thumb`** (miniatura) / **`.cell-avatar`** (avatar de iniciales para
  entidades sin imagen, como usuarios), **`.status-pill`** (estado con punto),
  y **`.empty-state`** (estado vacío con ícono).
- **Navbar fija** (`position:sticky`) para dar feel de app al hacer scroll.

## Dashboard con gráficas propias en SVG (sin librerías)

Se descartó React y Chart.js a propósito (ver la nota sobre React más abajo).
El dashboard (`home`) dibuja las gráficas con **SVG calculado en el servidor**,
reutilizando los modelos existentes (`Invoice`, `InvoiceDetail`, `Product`,
`Customer`) — cero endpoints o dependencias extra:

- **KPIs** (Ingresos, Facturas, Productos, Clientes) con **conteo animado**
  de 0 al valor real (JS en `app.js`, clase `.js-count`).
- **Ventas por mes** (últimos 6 meses): gráfica de área SVG. La geometría
  (polilínea + path del área) se calcula en `_area_chart()` dentro de la vista,
  así la plantilla solo pinta strings ya listos. La línea se "dibuja" al cargar.
- **Donut activos/inactivos**: arco SVG con `stroke-dasharray` calculado en la
  vista; se anima con `stroke-dashoffset`.
- **Top 5 productos más vendidos** (agregando `InvoiceDetail`): barras
  horizontales que crecen al cargar.
- **Stock bajo** y **Facturas recientes** con el estilo de tabla/lista premium.

> **Sobre React (decisión registrada):** se evaluó y se descartó para este
> proyecto. React exige un build de Node — meterlo al servicio Python de Render
> es frágil (la misma fricción por la que se descartó Tailwind), fractura la
> arquitectura server-rendered y obligaría a añadir una capa de API
> (serializers/endpoints/fetch = *más* código). Para un dashboard es
> sobredimensionado. Como aprendizaje conviene en un proyecto nuevo, no aquí.

## Consola de Roles: más aire + fix del conteo

- Las celdas de permiso (Ver/Crear/Editar/Eliminar) pasaron de una rejilla con
  bordes duros pegados ("todo montado") a **celdas-tarjeta separadas** que se
  **tiñen con el color de su acción cuando se marcan** (vía `:has(input:checked)`).
  Cada módulo es una tarjeta con sombra suave y un **distintivo con su inicial**.
- **Fix del conteo del rail**: antes el rail mostraba `Count('permissions')`
  = TODOS los permisos del rol (incluyendo apps internas de Django), mientras el
  panel contaba solo los visibles → "64" vs "56". Ahora el `perm_count` del rail
  filtra las apps excluidas
  (`filter=~Q(permissions__content_type__app_label__in=PERMISSION_EXCLUDED_APPS)`),
  así el rail cuadra con el panel (p. ej. Administrador: 52, no 64).

## Permisos: recuadros por módulo (no lista plana)

`PermissionListView.get_context_data()` agrupa los permisos por content type y
la plantilla los muestra como **tarjetas por módulo** (una por Brand, Customer,
Invoice, Product, User…), con distintivo, contador de permisos por módulo, y
cada permiso con sus botones de editar/eliminar. Incluye un **buscador** que
filtra los recuadros en vivo. Módulos de negocio primero; apps internas de
Django al final.

## Formularios de Compra y Factura: filas dinámicas + claridad

- **Encabezados legibles**: las tablas de detalle usan `thead.table-secondary`
  (fondo claro). El CSS global ponía el texto del encabezado en color claro
  (asumía fondo oscuro) → quedaba invisible. Fix en `app.css`:
  `.table > thead.table-secondary th { color: var(--ink) }`.
- **Botón "Agregar producto"**: ambos formsets pasaron de `extra=3` fijas a
  `extra=1` + un botón que crea filas dinámicamente y un botón 🗑 por fila para
  quitarlas. La técnica: se renderiza `{{ formset.empty_form }}` en un
  `<template>` (con `__prefix__`), y el JS clona la fila, **renumera**
  `name/id/for` a `0..n-1` y actualiza `TOTAL_FORMS`. Las filas vacías/no usadas
  se ignoran al guardar (Django las salta si no cambian respecto a su inicial;
  `quantity` tiene default=1, por eso una fila intacta manda `quantity=1`).
  En Factura se conservó el autocompletado de precio y la validación de stock.
- **Claridad del formulario de Compra**: traducido a español, con una guía que
  explica qué va en cada columna (Producto / Cantidad / Costo unitario /
  Subtotal) y ayudas bajo Proveedor y N.º de factura.

---

# Facturación Electrónica (simulada, sin SRI) + bitácora de pagos

Feature académica: da a las facturas apariencia de comprobante electrónico
ecuatoriano y un flujo de cobro, **sin ninguna conexión real al SRI**.

## Qué se reutilizó (para no duplicar)
- `Customer.dni` (ya tenía validación de cédula EC) y `Customer.address` — se
  usan como identificación y dirección del comprobante, en vez de crear campos
  `cedula_ruc`/`direccion` nuevos.
- El patrón de PDF de `purchasing/exports.py` (reportlab) para el comprobante.
- `shared/emails.py::send_invoice_email` — ahora adjunta el PDF.

## Modelos (migración `billing/0002`)
- `Invoice`: `numero_factura` (único), `clave_acceso`, `payment_status`
  (PENDIENTE/PAGADA/ANULADA), `payment_method`, `payment_date`.
- `PaymentLog` (bitácora): factura, usuario, método, monto, fecha, nota.

> **Migración segura en Render**: los campos nuevos son nullable / con default y
> `PaymentLog` es un modelo nuevo → aditiva. `numero_factura` es `unique` pero
> `null=True`; en PostgreSQL **múltiples NULL conviven** en un UNIQUE, así que
> las facturas ya existentes en producción (que quedan con número NULL) no
> chocan. Verificado en la Postgres local antes de desplegar.

## Generación (`billing/electronic.py`)
- `numero_factura`: `001-001-000000001` (establecimiento-punto emisión-secuencial).
- `clave_acceso`: 49 dígitos con la estructura del SRI (fecha+tipo+RUC+ambiente+
  serie+secuencial+código+tipo emisión) + **dígito verificador módulo 11**.
  Todo calculado localmente. Datos del emisor en `settings.EMPRESA`
  (configurables por variables de entorno `EMPRESA_*`).

## Flujo
1. Al crear una factura se asignan `numero_factura` y `clave_acceso`
   (`asignar_datos_electronicos`).
2. **PDF del comprobante** (`billing/invoice_export.py`): emisor, cliente
   (dni/dirección), líneas, IVA/total, estado y clave de acceso. Ruta
   `invoices/<pk>/pdf/`.
3. **"Marcar como pagado"** (`invoices/<pk>/mark-paid/`, POST): modal para elegir
   método (efectivo/transferencia/tarjeta) → estado PAGADA + fecha, registra un
   `PaymentLog` y reenvía el comprobante con el PDF adjunto. Bloquea doble pago.
4. Detalle: datos electrónicos, badge de estado y bitácora. Listado: columnas
   **N.º Factura** y **Pago** (pill de estado) + botón PDF por fila.

**PayPal** (bonus) se conectará aquí como un método de pago más en el flujo de
"Marcar como pagado".

---

# PayPal (Sandbox, simulado — sin dinero real)

Botón **"Pagar con PayPal"** en el detalle de factura, alternativo a "Marcar
como pagado" (que es manual: efectivo/transferencia/tarjeta). No se usa
``paypalrestsdk`` (deprecado por PayPal) sino la **Orders API v2** directa con
``requests`` — dos llamadas por operación (OAuth2 client-credentials + la
operación en sí).

## Configuración (Sandbox gratis, sin verificación de identidad)
1. Crear cuenta gratis en https://developer.paypal.com
2. Sandbox → Apps & Credentials → Create App
3. Copiar **Client ID** y **Secret** (Sandbox)
4. Definir en el entorno (local y/o Render): `PAYPAL_CLIENT_ID`,
   `PAYPAL_CLIENT_SECRET`, `PAYPAL_MODE=sandbox` (default).
5. Si faltan las credenciales, el botón se muestra **deshabilitado** con un
   tooltip ("PayPal no está configurado en este servidor") — la página nunca
   se rompe por no tener PayPal configurado.

> Pasar a producción real es **solo cambiar variables de entorno**
> (`PAYPAL_MODE=live` + credenciales Live) — `billing/paypal.py` no cambia.

## Flujo (`billing/paypal.py` + vistas en `billing/views.py`)
1. `invoice_paypal_start` (POST): crea la orden en PayPal por el total de la
   factura y redirige (302) al link de aprobación.
2. El usuario aprueba con una cuenta de prueba Sandbox (PayPal la genera
   junto con las credenciales del paso anterior, en *Sandbox → Accounts*).
3. PayPal redirige a `invoice_paypal_return` con `?token=<order_id>`; se
   captura el pago (`capture_order`). Si el estado es `COMPLETED`, se
   reutiliza `_apply_payment()` (la misma función que "Marcar como pagado")
   para poner la factura en PAGADA, registrar el `PaymentLog` (con el
   order/capture ID de PayPal en la nota) y reenviar el comprobante por
   correo.
4. Si el usuario cancela en PayPal, `invoice_paypal_cancel` no toca la
   factura (sigue PENDIENTE).
5. Doble pago bloqueado: si la factura ya está PAGADA, ninguna de las tres
   vistas vuelve a llamar a PayPal.

Verificado con pruebas E2E **mockeadas** (sin tocar la red real de PayPal):
sin configurar → botón deshabilitado y error amigable; con credenciales
falsas + `requests.post` mockeado → create→approve→capture→PAGADA con
bitácora correcta; cancelar → sin cambios; doble pago → bloqueado.

---

# Datos de prueba (`seed_demo_data`)

Comando de gestión para poblar el dashboard con datos realistas: catálogo
(marcas, grupos, proveedores, productos) + 10 clientes + facturas y compras
repartidas en los últimos 6 meses, para que las gráficas del dashboard
(ventas por mes, top productos, donut activos/inactivos, stock bajo) tengan
contenido real en vez de estar en cero.

```
python manage.py seed_demo_data              # últimos 6 meses (default)
python manage.py seed_demo_data --months 12   # opcional: repartir en más meses
```

## Diseño
- **Catálogo idempotente** (`get_or_create`): correr el comando varias veces
  no duplica marcas/grupos/proveedores/productos/clientes.
- **Facturas y compras: guard de "ya se sembró"**: si ya existe alguna
  factura de un cliente `@demo.local` (o alguna compra `DEMO-*`), el comando
  no genera más — evita duplicar el historial en una segunda corrida. (Se
  descubrió con una corrida de prueba doble: un umbral aproximado dejaba
  pasar una segunda tanda porque la semilla aleatoria fija generaba
  siempre el mismo conteo; se cambió a un guard exacto de existencia.)
- **3 productos con stock reservado** (Nesquik, Yogurt Toni, Chocolate
  Nestlé Crunch) quedan **excluidos** de ventas y compras generadas, para
  que el widget "Stock bajo" del dashboard siempre tenga contenido
  garantizado y predecible.
- Cédulas de clientes generadas con el mismo algoritmo módulo 10 que valida
  `shared/validators.py` (deterísticas y válidas).
- No envía correos (evita spamear las direcciones `@demo.local` ficticias).
- Requiere un superusuario ya creado (se usa como autor de los pagos en la
  bitácora).

Verificado: sin stock negativo, facturas con número/clave electrónica,
distribuidas en los últimos 6 meses, ~70% marcadas como pagadas con su
`PaymentLog`, y 3 corridas seguidas confirmando que la segunda y tercera no
agregan nada nuevo.
