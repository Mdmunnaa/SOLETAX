from django.urls import path
from . import views

urlpatterns = [
    path('',                                    views.index,                name='index'),
    path('about/',                              views.about,                name='about'),
    path('contact/',                            views.contact,              name='contact'),
    path('terms/',                              views.terms,                name='terms'),
    path('privacy/',                            views.privacy,              name='privacy'),
    path('refund/',                             views.refund,               name='refund'),
    path('signup/',                             views.signup_view,          name='signup'),
    path('login/',                              views.login_view,           name='login'),
    path('logout/',                             views.logout_view,          name='logout'),
    path('accounts/google/login/',              views.google_login,         name='google_login'),
    path('accounts/google/login/callback/',     views.google_callback,      name='google_callback'),
    path('dashboard/',                          views.dashboard,            name='dashboard'),
    path('profile/',                            views.profile_view,         name='profile'),
    path('invoice/',                            views.create_invoice,       name='create_invoice'),
    path('invoice/mark-paid/<int:pk>/',         views.mark_paid,            name='mark_paid'),
    path('invoice/edit/<int:pk>/',              views.edit_invoice,         name='edit_invoice'),
    path('invoice/delete/<int:pk>/',            views.delete_invoice,       name='delete_invoice'),
    path('invoice/download/<int:pk>/',          views.download_invoice_pdf, name='download_invoice_pdf'),
    path('expense/',                            views.add_expense,          name='add_expense'),
    path('expense/edit/<int:pk>/',              views.edit_expense,         name='edit_expense'),
    path('expense/delete/<int:pk>/',            views.delete_expense,       name='delete_expense'),
    path('tax-report/',                         views.tax_report,           name='tax_report'),
    path('tax-report/download/',                views.download_tax_report_pdf, name='download_tax_report_pdf'),
]
