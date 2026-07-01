from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.conf import settings
from django.utils import timezone
import requests
import urllib.parse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from .models import Invoice, Expense, UserProfile
from .fraud_prevention import get_or_create_device_id
from decimal import Decimal


# ── Public pages ──────────────────────────────────────────────────

def index(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/index.html')

def about(request):   return render(request, 'core/about.html')
def contact(request): return render(request, 'core/contact.html')
def terms(request):   return render(request, 'core/terms.html')
def privacy(request): return render(request, 'core/privacy.html')
def refund(request):  return render(request, 'core/refund.html')


# ── Auth ──────────────────────────────────────────────────────────

def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user)
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


# ── Google OAuth ──────────────────────────────────────────────────

def google_login(request):
    params = {
        'client_id':     settings.GOOGLE_OAUTH_CLIENT_ID,
        'redirect_uri':  settings.GOOGLE_OAUTH_REDIRECT_URI,
        'response_type': 'code',
        'scope':         'openid email profile',
        'access_type':   'online',
        'prompt':        'select_account',
    }
    return redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params))


def google_callback(request):
    code  = request.GET.get('code')
    error = request.GET.get('error')
    if error or not code:
        return render(request, 'core/login.html', {
            'form': AuthenticationForm(),
            'google_error': 'Google sign-in was cancelled or failed. Please try again.',
        })

    token_response = requests.post('https://oauth2.googleapis.com/token', data={
        'code':          code,
        'client_id':     settings.GOOGLE_OAUTH_CLIENT_ID,
        'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
        'redirect_uri':  settings.GOOGLE_OAUTH_REDIRECT_URI,
        'grant_type':    'authorization_code',
    }, timeout=10)

    if token_response.status_code != 200:
        return render(request, 'core/login.html', {
            'form': AuthenticationForm(),
            'google_error': 'Could not verify your Google account. Please try again.',
        })

    access_token = token_response.json().get('access_token')
    userinfo = requests.get(
        'https://www.googleapis.com/oauth2/v2/userinfo',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    ).json()

    email      = userinfo.get('email')
    first_name = userinfo.get('given_name', '')
    last_name  = userinfo.get('family_name', '')

    if not email:
        return render(request, 'core/login.html', {
            'form': AuthenticationForm(),
            'google_error': 'Could not get your email from Google. Please try again.',
        })

    user, created = User.objects.get_or_create(
        username=email,
        defaults={'email': email, 'first_name': first_name, 'last_name': last_name},
    )
    if created:
        user.set_unusable_password()
        user.save()
        UserProfile.objects.create(user=user, full_name=f"{first_name} {last_name}".strip())
    else:
        UserProfile.objects.get_or_create(user=user)

    login(request, user)
    return redirect('dashboard')


# ── Dashboard ─────────────────────────────────────────────────────

@login_required(login_url='/login/')
def dashboard(request):
    invoices       = Invoice.objects.filter(user=request.user)
    expenses       = Expense.objects.filter(user=request.user)
    total_income   = invoices.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    profit         = total_income - total_expenses
    profile, _     = UserProfile.objects.get_or_create(user=request.user)

    response = render(request, 'core/dashboard.html', {
        'invoices':       invoices,
        'expenses':       expenses,
        'total_income':   total_income,
        'total_expenses': total_expenses,
        'profit':         profit,
        'profile':        profile,
    })

    # Persist HMRC fraud-prevention device ID as a long-lived cookie.
    device_id, created = get_or_create_device_id(request)
    if created:
        response.set_cookie(
            'soletax_device_id', device_id,
            max_age=60 * 60 * 24 * 365 * 2,
            httponly=True, samesite='Lax',
        )
    return response


# ── Profile ───────────────────────────────────────────────────────

@login_required(login_url='/login/')
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        profile.full_name     = request.POST.get('full_name', '').strip()
        profile.business_name = request.POST.get('business_name', '').strip()
        profile.phone         = request.POST.get('phone', '').strip()
        profile.utr           = request.POST.get('utr', '').strip()
        profile.ni_number     = request.POST.get('ni_number', '').strip().upper().replace(' ', '')
        profile.is_vat_registered = request.POST.get('is_vat_registered') == 'on'
        profile.vat_number    = request.POST.get('vat_number', '').strip()
        profile.address_line1 = request.POST.get('address_line1', '').strip()
        profile.address_line2 = request.POST.get('address_line2', '').strip()
        profile.city          = request.POST.get('city', '').strip()
        profile.postcode      = request.POST.get('postcode', '').strip().upper()
        profile.save()
        return redirect('profile')
    return render(request, 'core/profile.html', {'profile': profile})


# ── Invoice ───────────────────────────────────────────────────────

@login_required(login_url='/login/')
def create_invoice(request):
    if request.method == 'POST':
        txn_date = request.POST.get('transaction_date') or timezone.now().date()
        Invoice.objects.create(
            user=request.user,
            client=request.POST['client'],
            description=request.POST['description'],
            amount=request.POST['amount'],
            transaction_date=txn_date,
        )
        return redirect('dashboard')
    return render(request, 'core/invoice.html', {'today': timezone.now().date()})


@login_required(login_url='/login/')
def mark_paid(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    invoice.status = 'Paid'
    invoice.save()
    return redirect('dashboard')


@login_required(login_url='/login/')
def download_invoice_pdf(request, pk):
    invoice  = get_object_or_404(Invoice, pk=pk, user=request.user)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="SoleTax_Invoice_{invoice.id:04d}.pdf"'
    p = canvas.Canvas(response, pagesize=A4)
    w, h = A4

    p.setFillColor(colors.white)
    p.rect(0, 0, w, h, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#3b82f6'))
    p.rect(0, h - 6*mm, w, 6*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#f8fafc'))
    p.rect(0, h - 50*mm, w, 44*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#1e293b'))
    p.setFont("Helvetica-Bold", 26)
    p.drawString(15*mm, h - 28*mm, "SoleTax")
    p.setFillColor(colors.HexColor('#3b82f6'))
    p.setFont("Helvetica", 10)
    p.drawString(15*mm, h - 36*mm, "Tax Invoice  ·  UK Sole Trader Tool")
    p.setFillColor(colors.HexColor('#3b82f6'))
    p.roundRect(w - 65*mm, h - 40*mm, 50*mm, 20*mm, 3*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 9)
    p.drawCentredString(w - 40*mm, h - 26*mm, "INVOICE")
    p.setFont("Helvetica-Bold", 15)
    p.drawCentredString(w - 40*mm, h - 36*mm, f"#{invoice.id:04d}")
    p.setStrokeColor(colors.HexColor('#e2e8f0'))
    p.setLineWidth(1)
    p.line(15*mm, h - 52*mm, w - 15*mm, h - 52*mm)
    p.setFillColor(colors.HexColor('#64748b'))
    p.setFont("Helvetica-Bold", 8)
    p.drawString(15*mm, h - 62*mm, "DATE")
    p.drawString(70*mm, h - 62*mm, "STATUS")
    p.drawString(130*mm, h - 62*mm, "ISSUED TO")
    p.setFillColor(colors.HexColor('#1e293b'))
    p.setFont("Helvetica", 11)
    p.drawString(15*mm, h - 71*mm, str(invoice.transaction_date))
    status_color = colors.HexColor('#16a34a') if invoice.status == 'Paid' else colors.HexColor('#dc2626')
    p.setFillColor(status_color)
    p.drawString(70*mm, h - 71*mm, invoice.status)
    p.setFillColor(colors.HexColor('#1e293b'))
    p.drawString(130*mm, h - 71*mm, invoice.client)

    # Issuer address from profile (if available)
    if profile.address_line1:
        p.setFillColor(colors.HexColor('#64748b'))
        p.setFont("Helvetica", 8)
        addr_lines = [
            profile.full_name or request.user.username,
            profile.address_line1,
        ]
        if profile.address_line2: addr_lines.append(profile.address_line2)
        addr_lines += [profile.city, profile.postcode]
        for i, line in enumerate([l for l in addr_lines if l]):
            p.drawString(15*mm, h - 82*mm - i*4*mm, line)

    p.setFillColor(colors.HexColor('#f8fafc'))
    p.roundRect(15*mm, h - 115*mm, 80*mm, 22*mm, 3*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#64748b'))
    p.setFont("Helvetica-Bold", 8)
    p.drawString(20*mm, h - 100*mm, "BILL TO")
    p.setFillColor(colors.HexColor('#1e293b'))
    p.setFont("Helvetica-Bold", 13)
    p.drawString(20*mm, h - 110*mm, invoice.client)
    p.setFillColor(colors.HexColor('#1e293b'))
    p.rect(15*mm, h - 137*mm, w - 30*mm, 10*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 9)
    p.drawString(20*mm, h - 130*mm, "DESCRIPTION")
    p.drawRightString(w - 20*mm, h - 130*mm, "AMOUNT")
    p.setFillColor(colors.HexColor('#f8fafc'))
    p.rect(15*mm, h - 155*mm, w - 30*mm, 17*mm, fill=1, stroke=0)
    p.setStrokeColor(colors.HexColor('#e2e8f0'))
    p.rect(15*mm, h - 155*mm, w - 30*mm, 17*mm, fill=0, stroke=1)
    p.setFillColor(colors.HexColor('#334155'))
    p.setFont("Helvetica", 10)
    desc = invoice.description[:70] + '...' if len(invoice.description) > 70 else invoice.description
    p.drawString(20*mm, h - 145*mm, desc)
    p.setFont("Helvetica-Bold", 10)
    p.drawRightString(w - 20*mm, h - 145*mm, f"£{invoice.amount}")
    p.setFillColor(colors.HexColor('#3b82f6'))
    p.roundRect(w - 75*mm, h - 185*mm, 60*mm, 20*mm, 3*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 9)
    p.drawCentredString(w - 45*mm, h - 172*mm, "TOTAL DUE")
    p.setFont("Helvetica-Bold", 17)
    p.drawCentredString(w - 45*mm, h - 183*mm, f"£{invoice.amount}")
    p.setFillColor(colors.HexColor('#94a3b8'))
    p.setFont("Helvetica", 9)
    p.drawString(15*mm, h - 200*mm, "Thank you for your business. Please make payment within 30 days.")
    p.setFillColor(colors.HexColor('#f8fafc'))
    p.rect(0, 0, w, 20*mm, fill=1, stroke=0)
    p.setStrokeColor(colors.HexColor('#e2e8f0'))
    p.line(0, 20*mm, w, 20*mm)
    p.setFillColor(colors.HexColor('#94a3b8'))
    p.setFont("Helvetica", 8)
    p.drawCentredString(w/2, 8*mm, "Generated by SoleTax  ·  soletax.pythonanywhere.com")
    p.showPage()
    p.save()
    return response


# ── Expense ───────────────────────────────────────────────────────

@login_required(login_url='/login/')
def add_expense(request):
    if request.method == 'POST':
        txn_date = request.POST.get('transaction_date') or timezone.now().date()
        Expense.objects.create(
            user=request.user,
            description=request.POST['description'],
            amount=request.POST['amount'],
            category=request.POST['category'],
            transaction_date=txn_date,
        )
        return redirect('dashboard')
    categories = Expense.CATEGORY_CHOICES
    return render(request, 'core/expense.html', {'categories': categories, 'today': timezone.now().date()})


# ── Tax report ────────────────────────────────────────────────────

@login_required(login_url='/login/')
def tax_report(request):
    invoices       = Invoice.objects.filter(user=request.user)
    expenses       = Expense.objects.filter(user=request.user)
    total_income   = invoices.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    profit         = total_income - total_expenses
    tax_estimate   = profit * Decimal('0.20')
    return render(request, 'core/tax_report.html', {
        'invoices': invoices, 'expenses': expenses,
        'total_income': total_income, 'total_expenses': total_expenses,
        'profit': profit, 'tax_estimate': tax_estimate,
    })


@login_required(login_url='/login/')
def download_tax_report_pdf(request):
    invoices       = Invoice.objects.filter(user=request.user)
    expenses       = Expense.objects.filter(user=request.user)
    total_income   = invoices.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    total_expenses = expenses.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    profit         = total_income - total_expenses
    tax_estimate   = profit * Decimal('0.20')

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="SoleTax_Tax_Report.pdf"'
    p = canvas.Canvas(response, pagesize=A4)
    w, h = A4

    p.setFillColor(colors.white);  p.rect(0, 0, w, h, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#3b82f6')); p.rect(0, h-6*mm, w, 6*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#f8fafc')); p.rect(0, h-48*mm, w, 42*mm, fill=1, stroke=0)
    p.setFillColor(colors.HexColor('#1e293b')); p.setFont("Helvetica-Bold", 24)
    p.drawString(15*mm, h-26*mm, "SoleTax")
    p.setFillColor(colors.HexColor('#3b82f6')); p.setFont("Helvetica", 10)
    p.drawString(15*mm, h-34*mm, "HMRC MTD Tax Report  ·  UK Sole Trader")
    p.setFillColor(colors.HexColor('#94a3b8')); p.setFont("Helvetica", 9)
    p.drawString(15*mm, h-42*mm, f"Prepared for: {request.user.username}")
    p.setStrokeColor(colors.HexColor('#e2e8f0')); p.line(15*mm, h-50*mm, w-15*mm, h-50*mm)

    box_w = (w - 30*mm - 9*mm) / 4
    summaries = [
        ('#f0fdf4','#166534','#15803d','TOTAL INCOME',   f'£{total_income}'),
        ('#fff1f2','#9f1239','#be123c','TOTAL EXPENSES',  f'£{total_expenses}'),
        ('#eff6ff','#1e40af','#1d4ed8','NET PROFIT',      f'£{profit}'),
        ('#fefce8','#854d0e','#a16207','EST. TAX (20%)',  f'£{tax_estimate}'),
    ]
    for i, (bg, val_c, lbl_c, label, value) in enumerate(summaries):
        x = 15*mm + i*(box_w+3*mm); y = h-80*mm
        p.setFillColor(colors.HexColor(bg)); p.roundRect(x,y,box_w,22*mm,3*mm,fill=1,stroke=0)
        p.setFillColor(colors.HexColor(lbl_c)); p.setFont("Helvetica-Bold",7)
        p.drawCentredString(x+box_w/2, y+17*mm, label)
        p.setFillColor(colors.HexColor(val_c)); p.setFont("Helvetica-Bold",13)
        p.drawCentredString(x+box_w/2, y+7*mm, value)

    y = h-100*mm
    p.setFillColor(colors.HexColor('#1e293b')); p.rect(15*mm,y,w-30*mm,9*mm,fill=1,stroke=0)
    p.setFillColor(colors.white); p.setFont("Helvetica-Bold",8)
    p.drawString(20*mm,y+3*mm,"INCOME — INVOICES"); p.drawRightString(w-20*mm,y+3*mm,"AMOUNT")
    row_y = y-1*mm
    for idx, inv in enumerate(invoices):
        row_y -= 8*mm
        if row_y < 60*mm: break
        p.setFillColor(colors.HexColor('#f8fafc') if idx%2==0 else colors.white)
        p.rect(15*mm,row_y,w-30*mm,7.5*mm,fill=1,stroke=0)
        p.setFillColor(colors.HexColor('#334155')); p.setFont("Helvetica",8.5)
        p.drawString(20*mm,row_y+2*mm,f"{inv.client}  —  {inv.description[:50]}")
        p.setFont("Helvetica-Bold",8.5); p.drawRightString(w-20*mm,row_y+2*mm,f"£{inv.amount}")

    row_y -= 12*mm
    if row_y > 55*mm:
        p.setFillColor(colors.HexColor('#1e293b')); p.rect(15*mm,row_y,w-30*mm,9*mm,fill=1,stroke=0)
        p.setFillColor(colors.white); p.setFont("Helvetica-Bold",8)
        p.drawString(20*mm,row_y+3*mm,"EXPENSES"); p.drawRightString(w-20*mm,row_y+3*mm,"AMOUNT")
        exp_y = row_y-1*mm
        for idx, exp in enumerate(expenses):
            exp_y -= 8*mm
            if exp_y < 25*mm: break
            p.setFillColor(colors.HexColor('#fff1f2') if idx%2==0 else colors.white)
            p.rect(15*mm,exp_y,w-30*mm,7.5*mm,fill=1,stroke=0)
            p.setFillColor(colors.HexColor('#334155')); p.setFont("Helvetica",8.5)
            p.drawString(20*mm,exp_y+2*mm,f"{exp.description}  —  {exp.category}")
            p.setFont("Helvetica-Bold",8.5); p.drawRightString(w-20*mm,exp_y+2*mm,f"£{exp.amount}")

    p.setFillColor(colors.HexColor('#f8fafc')); p.rect(0,0,w,18*mm,fill=1,stroke=0)
    p.setStrokeColor(colors.HexColor('#e2e8f0')); p.line(0,18*mm,w,18*mm)
    p.setFillColor(colors.HexColor('#94a3b8')); p.setFont("Helvetica",8)
    p.drawCentredString(w/2,7*mm,"Generated by SoleTax  ·  soletax.pythonanywhere.com")
    p.showPage(); p.save()
    return response
