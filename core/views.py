from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.conf import settings
import requests
import urllib.parse
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


def google_login(request):
    """Redirect user to Google's OAuth consent screen."""
    params = {
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'online',
        'prompt': 'select_account',
    }
    google_auth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)
    return redirect(google_auth_url)


def google_callback(request):
    """Handle the redirect back from Google, exchange code for token, log user in."""
    code = request.GET.get('code')
    error = request.GET.get('error')

    if error or not code:
        return render(request, 'core/login.html', {
            'form': AuthenticationForm(),
            'google_error': 'Google sign-in was cancelled or failed. Please try again.'
        })

    # Exchange authorization code for access token
    token_url = 'https://oauth2.googleapis.com/token'
    token_data = {
        'code': code,
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
        'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }
    token_response = requests.post(token_url, data=token_data, timeout=10)

    if token_response.status_code != 200:
        return render(request, 'core/login.html', {
            'form': AuthenticationForm(),
            'google_error': 'Could not verify your Google account. Please try again.'
        })

    token_json = token_response.json()
    access_token = token_json.get('access_token')

    # Fetch user info from Google
    userinfo_response = requests.get(
        'https://www.googleapis.com/oauth2/v2/userinfo',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10
    )
    userinfo = userinfo_response.json()

    email = userinfo.get('email')
    first_name = userinfo.get('given_name', '')
    last_name = userinfo.get('family_name', '')

    if not email:
        return render(request, 'core/login.html', {
            'form': AuthenticationForm(),
            'google_error': 'Could not get your email from Google. Please try again.'
        })

    # Find or create the user — username is the email itself
    user, created = User.objects.get_or_create(
        username=email,
        defaults={
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
        }
    )
    if created:
        user.set_unusable_password()  # they log in via Google only
        user.save()

    login(request, user)
    return redirect('dashboard')


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

    # White background
    p.setFillColor(colors.white)
    p.rect(0, 0, w, h, fill=1, stroke=0)

    # Top accent bar
    p.setFillColor(colors.HexColor('#3b82f6'))
    p.rect(0, h - 6*mm, w, 6*mm, fill=1, stroke=0)

    # Header area
    p.setFillColor(colors.HexColor('#f8fafc'))
    p.rect(0, h - 50*mm, w, 44*mm, fill=1, stroke=0)

    # Brand
    p.setFillColor(colors.HexColor('#1e293b'))
    p.setFont("Helvetica-Bold", 26)
    p.drawString(15*mm, h - 28*mm, "SoleTax")
    p.setFillColor(colors.HexColor('#3b82f6'))
    p.setFont("Helvetica", 10)
    p.drawString(15*mm, h - 36*mm, "Tax Invoice  ·  UK Sole Trader Tool")

    # Invoice number badge
    p.setFillColor(colors.HexColor('#3b82f6'))
    p.roundRect(w - 65*mm, h - 40*mm, 50*mm, 20*mm, 3*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 9)
    p.drawCentredString(w - 40*mm, h - 26*mm, "INVOICE")
    p.setFont("Helvetica-Bold", 15)
    p.drawCentredString(w - 40*mm, h - 36*mm, f"#{invoice.id:04d}")

    # Divider line
    p.setStrokeColor(colors.HexColor('#e2e8f0'))
    p.setLineWidth(1)
    p.line(15*mm, h - 52*mm, w - 15*mm, h - 52*mm)

    # Two column info
    p.setFillColor(colors.HexColor('#64748b'))
    p.setFont("Helvetica-Bold", 8)
    p.drawString(15*mm, h - 62*mm, "DATE")
    p.drawString(70*mm, h - 62*mm, "STATUS")
    p.drawString(130*mm, h - 62*mm, "ISSUED TO")

    p.setFillColor(colors.HexColor('#1e293b'))
    p.setFont("Helvetica", 11)
    p.drawString(15*mm, h - 71*mm, str(invoice.date))
    status_color = colors.HexColor('#16a34a') if invoice.status == 'Paid' else colors.HexColor('#dc2626')
    p.setFillColor(status_color)
    p.drawString(70*mm, h - 71*mm, invoice.status)
    p.setFillColor(colors.HexColor('#1e293b'))
    p.drawString(130*mm, h - 71*mm, invoice.client)

    # Bill To
    p.setFillColor(colors.HexColor('#f8fafc'))
    p.roundRect(15*mm, h - 100*mm, 80*mm, 22*mm, 3*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#64748b'))
    p.setFont("Helvetica-Bold", 8)
    p.drawString(20*mm, h - 85*mm, "BILL TO")
    p.setFillColor(colors.HexColor('#1e293b'))
    p.setFont("Helvetica-Bold", 13)
    p.drawString(20*mm, h - 95*mm, invoice.client)

    # Table
    p.setFillColor(colors.HexColor('#1e293b'))
    p.rect(15*mm, h - 122*mm, w - 30*mm, 10*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 9)
    p.drawString(20*mm, h - 115*mm, "DESCRIPTION")
    p.drawRightString(w - 20*mm, h - 115*mm, "AMOUNT")

    # Row
    p.setFillColor(colors.HexColor('#f8fafc'))
    p.rect(15*mm, h - 140*mm, w - 30*mm, 17*mm, fill=1, stroke=0)
    p.setStrokeColor(colors.HexColor('#e2e8f0'))
    p.rect(15*mm, h - 140*mm, w - 30*mm, 17*mm, fill=0, stroke=1)
    p.setFillColor(colors.HexColor('#334155'))
    p.setFont("Helvetica", 10)
    desc = invoice.description[:70] + '...' if len(invoice.description) > 70 else invoice.description
    p.drawString(20*mm, h - 130*mm, desc)
    p.setFont("Helvetica-Bold", 10)
    p.drawRightString(w - 20*mm, h - 130*mm, f"£{invoice.amount}")

    # Subtotal row
    p.setFillColor(colors.HexColor('#f1f5f9'))
    p.rect(15*mm, h - 150*mm, w - 30*mm, 9*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#64748b'))
    p.setFont("Helvetica", 9)
    p.drawRightString(w - 65*mm, h - 143*mm, "Subtotal:")
    p.setFillColor(colors.HexColor('#1e293b'))
    p.drawRightString(w - 20*mm, h - 143*mm, f"£{invoice.amount}")

    # Total box
    p.setFillColor(colors.HexColor('#3b82f6'))
    p.roundRect(w - 75*mm, h - 175*mm, 60*mm, 20*mm, 3*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 9)
    p.drawCentredString(w - 45*mm, h - 162*mm, "TOTAL DUE")
    p.setFont("Helvetica-Bold", 17)
    p.drawCentredString(w - 45*mm, h - 173*mm, f"£{invoice.amount}")

    # Thank you note
    p.setFillColor(colors.HexColor('#94a3b8'))
    p.setFont("Helvetica", 9)
    p.drawString(15*mm, h - 190*mm, "Thank you for your business. Please make payment within 30 days.")

    # Footer
    p.setFillColor(colors.HexColor('#f8fafc'))
    p.rect(0, 0, w, 20*mm, fill=1, stroke=0)
    p.setStrokeColor(colors.HexColor('#e2e8f0'))
    p.line(0, 20*mm, w, 20*mm)
    p.setFillColor(colors.HexColor('#94a3b8'))
    p.setFont("Helvetica", 8)
    p.drawCentredString(w/2, 8*mm, "Generated by SoleTax  ·  soletax.pythonanywhere.com  ·  Simple Tax Tool for UK Freelancers")

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

    # White bg
    p.setFillColor(colors.white)
    p.rect(0, 0, w, h, fill=1, stroke=0)

    # Top bar
    p.setFillColor(colors.HexColor('#3b82f6'))
    p.rect(0, h - 6*mm, w, 6*mm, fill=1, stroke=0)

    # Header
    p.setFillColor(colors.HexColor('#f8fafc'))
    p.rect(0, h - 48*mm, w, 42*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#1e293b'))
    p.setFont("Helvetica-Bold", 24)
    p.drawString(15*mm, h - 26*mm, "SoleTax")
    p.setFillColor(colors.HexColor('#3b82f6'))
    p.setFont("Helvetica", 10)
    p.drawString(15*mm, h - 34*mm, "HMRC MTD Tax Report  ·  UK Sole Trader")
    p.setFillColor(colors.HexColor('#94a3b8'))
    p.setFont("Helvetica", 9)
    p.drawString(15*mm, h - 42*mm, f"Prepared for: {request.user.username}")
    p.setStrokeColor(colors.HexColor('#e2e8f0'))
    p.line(15*mm, h - 50*mm, w - 15*mm, h - 50*mm)

    # Summary cards (4 boxes)
    box_w = (w - 30*mm - 9*mm) / 4
    summaries = [
        ('#f0fdf4', '#166534', '#15803d', 'TOTAL INCOME', f'£{total_income}'),
        ('#fff1f2', '#9f1239', '#be123c', 'TOTAL EXPENSES', f'£{total_expenses}'),
        ('#eff6ff', '#1e40af', '#1d4ed8', 'NET PROFIT', f'£{profit}'),
        ('#fefce8', '#854d0e', '#a16207', 'EST. TAX (20%)', f'£{tax_estimate}'),
    ]
    for i, (bg, val_color, lbl_color, label, value) in enumerate(summaries):
        x = 15*mm + i * (box_w + 3*mm)
        y = h - 80*mm
        p.setFillColor(colors.HexColor(bg))
        p.roundRect(x, y, box_w, 22*mm, 3*mm, fill=1, stroke=0)
        p.setFillColor(colors.HexColor(lbl_color))
        p.setFont("Helvetica-Bold", 7)
        p.drawCentredString(x + box_w/2, y + 17*mm, label)
        p.setFillColor(colors.HexColor(val_color))
        p.setFont("Helvetica-Bold", 13)
        p.drawCentredString(x + box_w/2, y + 7*mm, value)

    # Income table
    y = h - 100*mm
    p.setFillColor(colors.HexColor('#1e293b'))
    p.rect(15*mm, y, w - 30*mm, 9*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 8)
    p.drawString(20*mm, y + 3*mm, "INCOME — INVOICES")
    p.drawRightString(w - 20*mm, y + 3*mm, "AMOUNT")

    row_y = y - 1*mm
    for inv in invoices:
        row_y -= 8*mm
        if row_y < 60*mm:
            break
        c = colors.HexColor('#f8fafc') if list(invoices).index(inv) % 2 == 0 else colors.white
        p.setFillColor(c)
        p.rect(15*mm, row_y, w - 30*mm, 7.5*mm, fill=1, stroke=0)
        p.setFillColor(colors.HexColor('#334155'))
        p.setFont("Helvetica", 8.5)
        p.drawString(20*mm, row_y + 2*mm, f"{inv.client}  —  {inv.description[:50]}")
        p.setFont("Helvetica-Bold", 8.5)
        p.drawRightString(w - 20*mm, row_y + 2*mm, f"£{inv.amount}")

    # Expense table
    row_y -= 12*mm
    if row_y > 55*mm:
        p.setFillColor(colors.HexColor('#1e293b'))
        p.rect(15*mm, row_y, w - 30*mm, 9*mm, fill=1, stroke=0)
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 8)
        p.drawString(20*mm, row_y + 3*mm, "EXPENSES")
        p.drawRightString(w - 20*mm, row_y + 3*mm, "AMOUNT")

        exp_y = row_y - 1*mm
        for exp in expenses:
            exp_y -= 8*mm
            if exp_y < 25*mm:
                break
            c = colors.HexColor('#fff1f2') if list(expenses).index(exp) % 2 == 0 else colors.white
            p.setFillColor(c)
            p.rect(15*mm, exp_y, w - 30*mm, 7.5*mm, fill=1, stroke=0)
            p.setFillColor(colors.HexColor('#334155'))
            p.setFont("Helvetica", 8.5)
            p.drawString(20*mm, exp_y + 2*mm, f"{exp.description}  —  {exp.category}")
            p.setFont("Helvetica-Bold", 8.5)
            p.drawRightString(w - 20*mm, exp_y + 2*mm, f"£{exp.amount}")

    # Footer
    p.setFillColor(colors.HexColor('#f8fafc'))
    p.rect(0, 0, w, 18*mm, fill=1, stroke=0)
    p.setStrokeColor(colors.HexColor('#e2e8f0'))
    p.line(0, 18*mm, w, 18*mm)
    p.setFillColor(colors.HexColor('#94a3b8'))
    p.setFont("Helvetica", 8)
    p.drawCentredString(w/2, 7*mm, "Generated by SoleTax  ·  soletax.pythonanywhere.com  ·  HMRC MTD Ready")

    p.showPage()
    p.save()
    return response


def about(request):
    return render(request, 'core/about.html')

def contact(request):
    return render(request, 'core/contact.html')

def terms(request):
    return render(request, 'core/terms.html')

def privacy(request):
    return render(request, 'core/privacy.html')

def refund(request):
    return render(request, 'core/refund.html')
