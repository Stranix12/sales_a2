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
/purchases/            → purchase_list   (con filtros)
/purchases/create/     → purchase_create (formset + suma de stock)
/purchases/report/     → purchase_report (costo promedio por producto)
/purchases/<id>/       → purchase_detail
/purchases/<id>/delete/→ purchase_delete
```
