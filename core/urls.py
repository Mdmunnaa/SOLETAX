from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('invoice/', views.create_invoice, name='create_invoice'),
    path('invoice/mark-paid/<int:pk>/', views.mark_paid, name='mark_paid'),
    path('expense/', views.add_expense, name='add_expense'),
    path('tax-report/', views.tax_report, name='tax_report'),
]
