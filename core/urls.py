from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('invoice/', views.create_invoice, name='create_invoice'),
    path('invoice/mark-paid/<int:pk>/', views.mark_paid, name='mark_paid'),
    path('invoice/download/<int:pk>/', views.download_invoice_pdf, name='download_invoice_pdf'),
    path('expense/', views.add_expense, name='add_expense'),
    path('tax-report/', views.tax_report, name='tax_report'),
    path('tax-report/download/', views.download_tax_report_pdf, name='download_tax_report_pdf'),
]
