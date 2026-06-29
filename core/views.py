from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Invoice, Expense
from decimal import Decimal


def index(request):
    return render(request, 'core/index.html')


def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'core/signup.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'core/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('index')


@login_required(login_url='/login/')
def dashboard(request):
    invoices = Invoice.objects.filter(user=request.user)
    expenses = Expense.objects.filter(user=request.user)
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


@login_required(login_url='/login/')
def create_invoice(request):
    if request.method == 'POST':
        Invoice.objects.create(
            user=request.user,
            client=request.POST['client'],
            description=request.POST['description'],
            amount=request.POST['amount'],
        )
        return redirect('dashboard')
    return render(request, 'core/invoice.html')


@login_required(login_url='/login/')
def mark_paid(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    invoice.status = 'Paid'
    invoice.save()
    return redirect('dashboard')


@login_required(login_url='/login/')
def add_expense(request):
    if request.method == 'POST':
        Expense.objects.create(
            user=request.user,
            description=request.POST['description'],
            amount=request.POST['amount'],
            category=request.POST['category'],
        )
        return redirect('dashboard')
    categories = Expense.CATEGORY_CHOICES
    return render(request, 'core/expense.html', {'categories': categories})


@login_required(login_url='/login/')
def tax_report(request):
    invoices = Invoice.objects.filter(user=request.user)
    expenses = Expense.objects.filter(user=request.user)
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
