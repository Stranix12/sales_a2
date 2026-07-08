from django.urls import path 
from . import views 
app_name = 'billing' 
urlpatterns = [
# Home (Dashboard)
path('', views.home, name='home'),
# Brand (lista CBV + create/update/delete FBV)
path('brands/', views.BrandListView.as_view(), name='brand_list'),
path('brands/create/', views.brand_create, name='brand_create'),
path('brands/<int:pk>/', views.brand_detail, name='brand_detail'),
path('brands/<int:pk>/edit/', views.brand_update, name='brand_update'),
path('brands/<int:pk>/delete/', views.brand_delete, name='brand_delete'),
# ProductGroup 
path('groups/', views.ProductGroupListView.as_view(),
name='productgroup_list'),
path('groups/<int:pk>/', views.ProductGroupDetailView.as_view(),
name='productgroup_detail'),
path('groups/create/', views.ProductGroupCreateView.as_view(),
name='productgroup_create'),
path('groups/<int:pk>/edit/', views.ProductGroupUpdateView.as_view(), 
name='productgroup_update'), 
path('groups/<int:pk>/delete/', views.ProductGroupDeleteView.as_view(), 
name='productgroup_delete'), 
# Supplier 
path('suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
path('suppliers/<int:pk>/', views.SupplierDetailView.as_view(),
name='supplier_detail'),
path('suppliers/create/', views.SupplierCreateView.as_view(),
name='supplier_create'),
path('suppliers/<int:pk>/edit/', views.SupplierUpdateView.as_view(), 
name='supplier_update'), 
path('suppliers/<int:pk>/delete/', views.SupplierDeleteView.as_view(), 
name='supplier_delete'), 
# Product
path('products/', views.ProductListView.as_view(), name='product_list'),
path('products/<int:pk>/', views.ProductDetailView.as_view(),
name='product_detail'),
path('products/create/', views.ProductCreateView.as_view(),
name='product_create'),
path('products/<int:pk>/edit/', views.ProductUpdateView.as_view(), 
name='product_update'), 
path('products/<int:pk>/delete/', views.ProductDeleteView.as_view(), 
name='product_delete'), 
# Customer
path('customers/', views.CustomerListView.as_view(), name='customer_list'),
path('customers/<int:pk>/', views.CustomerDetailView.as_view(),
name='customer_detail'),
path('customers/create/', views.CustomerCreateView.as_view(),
name='customer_create'),
path('customers/<int:pk>/edit/', views.CustomerUpdateView.as_view(), 
name='customer_update'), 
path('customers/<int:pk>/delete/', views.CustomerDeleteView.as_view(), 
name='customer_delete'), 
# Invoice (lista CBV + create/detail/delete FBV)
path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
path('invoices/create/', views.invoice_create, name='invoice_create'),
path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
path('invoices/<int:pk>/delete/', views.invoice_delete, name='invoice_delete'),
]