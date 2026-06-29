from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
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
def download_invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="SoleTax_Invoice_{invoice.id:04d}.pdf"'
    p = canvas.Canvas(response, pagesize=A4)
    w, h = A4

    # Dark header bar
    p.setFillColor(colors.HexColor('#1a1a2e'))
    p.rect(0, h - 80*mm, w, 80*mm, fill=1, stroke=0)

    # Brand
    p.setFillColor(colors.HexColor('#4cc9f0'))
    p.setFont("Helvetica-Bold", 32)
    p.drawString(15*mm, h - 28*mm, "SoleTax")
    p.setFillColor(colors.white)
    p.setFont("Helvetica", 11)
    p.drawString(15*mm, h - 38*mm, "Tax Invoice · UK Sole Trader Tool")

    # Invoice badge
    p.setFillColor(colors.HexColor('#4cc9f0'))
    p.roundRect(w - 75*mm, h - 38*mm, 60*mm, 18*mm, 4*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#1a1a2e'))
    p.setFont("Helvetica-Bold", 13)
    p.drawCentredString(w - 45*mm, h - 27*mm, f"INVOICE #{invoice.id:04d}")

    # Info row below header
    p.setFillColor(colors.HexColor('#f0f4ff'))
    p.rect(0, h - 100*mm, w, 20*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#555'))
    p.setFont("Helvetica", 10)
    p.drawString(15*mm, h - 88*mm, f"Date: {invoice.date}")
    p.drawString(70*mm, h - 88*mm, f"Status: {invoice.status}")
    p.drawString(130*mm, h - 88*mm, f"Issued to: {invoice.client}")

    # Bill To section
    p.setFillColor(colors.HexColor('#1a1a2e'))
    p.setFont("Helvetica-Bold", 10)
    p.drawString(15*mm, h - 115*mm, "BILL TO")
    p.setFillColor(colors.HexColor('#333'))
    p.setFont("Helvetica-Bold", 14)
    p.drawString(15*mm, h - 125*mm, invoice.client)

    # Table header
    p.setFillColor(colors.HexColor('#1a1a2e'))
    p.rect(15*mm, h - 152*mm, w - 30*mm, 12*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(20*mm, h - 145*mm, "DESCRIPTION")
    p.drawRightString(w - 20*mm, h - 145*mm, "AMOUNT")

    # Table row
    p.setFillColor(colors.HexColor('#f9f9f9'))
    p.rect(15*mm, h - 172*mm, w - 30*mm, 18*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#333'))
    p.setFont("Helvetica", 11)
    desc = invoice.description[:65] + '...' if len(invoice.description) > 65 else invoice.description
    p.drawString(20*mm, h - 162*mm, desc)
    p.setFont("Helvetica-Bold", 11)
    p.drawRightString(w - 20*mm, h - 162*mm, f"£{invoice.amount}")

    # Total box
    p.setFillColor(colors.HexColor('#4cc9f0'))
    p.roundRect(w - 75*mm, h - 200*mm, 60*mm, 22*mm, 3*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#1a1a2e'))
    p.setFont("Helvetica-Bold", 10)
    p.drawCentredString(w - 45*mm, h - 188*mm, "TOTAL DUE")
    p.setFont("Helvetica-Bold", 18)
    p.drawCentredString(w - 45*mm, h - 200*mm, f"£{invoice.amount}")

    # Note
    p.setFillColor(colors.HexColor('#888'))
    p.setFont("Helvetica", 9)
    p.drawString(15*mm, h - 220*mm, "Thank you for your business. Please make payment within 30 days.")

    # Footer
    p.setFillColor(colors.HexColor('#1a1a2e'))
    p.rect(0, 0, w, 18*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#aaa'))
    p.setFont("Helvetica", 8)
    p.drawCentredString(w/2, 8*mm, "Generated by SoleTax · soletax.pythonanywhere.com · Simple Tax Tool for UK Freelancers")

    p.showPage()
    p.save()
    return response


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


@login_required(login_url='/login/')
def download_tax_report_pdf(request):
    invoices = Invoice.objects.filter(user=request.user)
    expenses = Expense.objects.filter(user=request.user)
    total_income = invoices.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    profit = total_income - total_expenses
    tax_estimate = profit * Decimal('0.20')

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="SoleTax_Tax_Report.pdf"'
    p = canvas.Canvas(response, pagesize=A4)
    w, h = A4

    # Header
    p.setFillColor(colors.HexColor('#1a1a2e'))
    p.rect(0, h - 70*mm, w, 70*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#4cc9f0'))
    p.setFont("Helvetica-Bold", 28)
    p.drawString(15*mm, h - 28*mm, "SoleTax")
    p.setFillColor(colors.white)
    p.setFont("Helvetica", 11)
    p.drawString(15*mm, h - 38*mm, "HMRC MTD Tax Report · UK Sole Trader")
    p.setFont("Helvetica", 10)
    p.drawString(15*mm, h - 50*mm, f"Prepared for: {request.user.username}")

    # Summary cards
    card_y = h - 105*mm
    card_w = 52*mm
    cards = [
        ('#0f6e56', 'TOTAL INCOME', f'£{total_income}'),
        ('#c0392b', 'TOTAL EXPENSES', f'£{total_expenses}'),
        ('#1a1a2e', 'NET PROFIT', f'£{profit}'),
        ('#b7860b', 'EST. TAX (20%)', f'£{tax_estimate}'),
    ]
    for i, (color, label, value) in enumerate(cards):
        x = 15*mm + i * (card_w + 3*mm)
        p.setFillColor(colors.HexColor(color))
        p.roundRect(x, card_y, card_w, 22*mm, 3*mm, fill=1, stroke=0)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 8)
        p.drawCentredString(x + card_w/2, card_y + 17*mm, label)
        p.setFont("Helvetica-Bold", 14)
        p.drawCentredString(x + card_w/2, card_y + 7*mm, value)

    # Income table
    y = h - 140*mm
    p.setFillColor(colors.HexColor('#1a1a2e'))
    p.rect(15*mm, y, w - 30*mm, 10*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(20*mm, y + 3*mm, "INCOME (Invoices)")
    p.drawRightString(w - 20*mm, y + 3*mm, "AMOUNT")
    y -= 2*mm

    for inv in invoices:
        y -= 9*mm
        if y < 60*mm:
            break
        bg = colors.HexColor('#f9f9f9') if invoices.filter(pk=inv.pk).exists() else colors.white
        p.setFillColor(colors.HexColor('#f9f9f9'))
        p.rect(15*mm, y, w - 30*mm, 8*mm, fill=1, stroke=0)
        p.setFillColor(colors.HexColor('#333'))
        p.setFont("Helvetica", 9)
        p.drawString(20*mm, y + 2*mm, f"{inv.client} — {inv.description[:45]}")
        p.drawRightString(w - 20*mm, y + 2*mm, f"£{inv.amount}")

    # Expense table
    y -= 15*mm
    if y > 60*mm:
        p.setFillColor(colors.HexColor('#1a1a2e'))
        p.rect(15*mm, y, w - 30*mm, 10*mm, fill=1, stroke=0)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 10)
        p.drawString(20*mm, y + 3*mm, "EXPENSES")
        p.drawRightString(w - 20*mm, y + 3*mm, "AMOUNT")
        y -= 2*mm

        for exp in expenses:
            y -= 9*mm
            if y < 30*mm:
                break
            p.setFillColor(colors.HexColor('#fff5f5'))
            p.rect(15*mm, y, w - 30*mm, 8*mm, fill=1, stroke=0)
            p.setFillColor(colors.HexColor('#333'))
            p.setFont("Helvetica", 9)
            p.drawString(20*mm, y + 2*mm, f"{exp.description} — {exp.category}")
            p.drawRightString(w - 20*mm, y + 2*mm, f"£{exp.amount}")

    # Footer
    p.setFillColor(colors.HexColor('#1a1a2e'))
    p.rect(0, 0, w, 18*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#aaa'))
    p.setFont("Helvetica", 8)
    p.drawCentredString(w/2, 8*mm, "Generated by SoleTax · soletax.pythonanywhere.com · HMRC MTD Ready")

    p.showPage()
    p.save()
    return response
