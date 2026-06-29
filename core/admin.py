from django.contrib import admin
from .models import Invoice, Expense

admin.site.register(Invoice)
admin.site.register(Expense)
