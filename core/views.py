from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from .models import Invoice, Expense
from decimal import Decimal


def index(request):
    return render(request, 'core/index.html')


def dashboard(request):
    invoices = Invoice.objects.all()
    expenses = Expense.objects.all()
    total_income = invoices.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    profit = total_income - total_expenses
    return render(request, 'core/dashboard.html', {
        'invoices': invoices,
        'expenses': expenses,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'profit': profit,
    })


def create_invoice(request):
    if request.method == 'POST':
        Invoice.objects.create(
            client=request.POST['client'],
            description=request.POST['description'],
            amount=request.POST['amount'],
        )
        return redirect('dashboard')
    return render(request, 'core/invoice.html')


def mark_paid(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    invoice.status = 'Paid'
    invoice.save()
    return redirect('dashboard')


def add_expense(request):
    if request.method == 'POST':
        Expense.objects.create(
            description=request.POST['description'],
            amount=request.POST['amount'],
            category=request.POST['category'],
        )
        return redirect('dashboard')
    categories = Expense.CATEGORY_CHOICES
    return render(request, 'core/expense.html', {'categories': categories})


def tax_report(request):
    invoices = Invoice.objects.all()
    expenses = Expense.objects.all()
    total_income = invoices.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    profit = total_income - total_expenses
    tax_estimate = profit * Decimal('0.20')
    return render(request, 'core/tax_report.html', {
        'invoices': invoices,
        'expenses': expenses,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'profit': profit,
        'tax_estimate': tax_estimate,
    })
