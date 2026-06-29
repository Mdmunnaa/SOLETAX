from django.db import models
from django.contrib.auth.models import User

class Invoice(models.Model):
    STATUS_CHOICES = [('Unpaid', 'Unpaid'), ('Paid', 'Paid')]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    client = models.CharField(max_length=200)
    description = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Unpaid')

    def __str__(self):
        return f"Invoice #{self.id} - {self.client}"

    class Meta:
        ordering = ['-date']


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('Office costs', 'Office costs'),
        ('Travel & transport', 'Travel & transport'),
        ('Clothing (uniform/protective)', 'Clothing'),
        ('Staff costs', 'Staff costs'),
        ('Legal & financial costs', 'Legal & financial costs'),
        ('Marketing & advertising', 'Marketing & advertising'),
        ('Training courses', 'Training courses'),
        ('Software & subscriptions', 'Software & subscriptions'),
        ('Phone & internet', 'Phone & internet'),
        ('Other allowable expenses', 'Other allowable expenses'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=100, choices=CATEGORY_CHOICES)
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} - £{self.amount}"

    class Meta:
        ordering = ['-date']
