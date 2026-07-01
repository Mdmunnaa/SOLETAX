from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from .tax_periods import quarter_for_date, tax_year_label


# ──────────────────────────────────────────────────────────────────
# HMRC identifier validators
# ──────────────────────────────────────────────────────────────────

nino_validator = RegexValidator(
    regex=r'^[A-CEGHJ-PR-TW-Z]{1}[A-CEGHJ-NPR-TW-Z]{1}[0-9]{6}[A-D]{1}$',
    message='Enter a valid National Insurance number (e.g. AB123456C), no spaces.'
)
utr_validator = RegexValidator(
    regex=r'^\d{10}$',
    message='Enter a valid 10-digit Unique Taxpayer Reference (UTR).'
)


# ──────────────────────────────────────────────────────────────────
# UserProfile — editable by the user from /profile/
# Stores personal/business details used on invoices AND HMRC identifiers
# needed for MTD submissions. Merges the user-facing profile fields
# (name, address, VAT) with the MTD-compliance fields (UTR, NINO,
# business_id, accounting basis, signup status).
# ──────────────────────────────────────────────────────────────────

class UserProfile(models.Model):
    ACCOUNTING_BASIS_CHOICES = [
        ('cash',    'Cash basis'),
        ('accrual', 'Traditional accrual basis'),
    ]
    PERIOD_TYPE_CHOICES = [
        ('standard', 'Standard quarters (6 Apr / 6 Jul / 6 Oct / 6 Jan)'),
        ('calendar', 'Calendar quarters (1 Apr / 1 Jul / 1 Oct / 1 Jan)'),
    ]
    SIGNUP_STATUS_CHOICES = [
        ('not_started', 'Not signed up to MTD'),
        ('pending',     'HMRC sign-up pending'),
        ('active',      'Active on MTD for Income Tax'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # Personal / business identity (shown on invoices + used in MTD)
    full_name     = models.CharField(max_length=200, blank=True)
    business_name = models.CharField(max_length=200, blank=True,
                                      help_text="Your trading name, if different from your own name")
    phone         = models.CharField(max_length=30, blank=True)

    # HMRC tax identifiers
    utr = models.CharField(
        max_length=10, blank=True,
        verbose_name="UTR (Unique Taxpayer Reference)",
        help_text="10-digit number from HMRC, e.g. 1234567890",
        validators=[utr_validator],
    )
    ni_number = models.CharField(
        max_length=9, blank=True,
        verbose_name="National Insurance Number",
        help_text="e.g. AB123456C — no spaces",
        validators=[nino_validator],
    )
    business_id = models.CharField(
        max_length=50, blank=True,
        verbose_name="HMRC Business ID",
        help_text="Returned by HMRC after OAuth. Empty until user links HMRC account.",
    )

    # VAT
    is_vat_registered = models.BooleanField(default=False, verbose_name="VAT Registered?")
    vat_number        = models.CharField(max_length=20, blank=True, verbose_name="VAT Number")

    # Business address (used on invoices and MTD submissions)
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city          = models.CharField(max_length=100, blank=True)
    postcode      = models.CharField(max_length=20, blank=True)

    # MTD / filing preferences
    accounting_basis      = models.CharField(max_length=10, choices=ACCOUNTING_BASIS_CHOICES, default='cash')
    period_type           = models.CharField(max_length=10, choices=PERIOD_TYPE_CHOICES, default='standard')
    business_start_date   = models.DateField(null=True, blank=True, help_text="Usually 6 April")
    accounting_period_end = models.DateField(null=True, blank=True, help_text="Usually 5 April next year")

    # MTD onboarding status
    mtd_signup_status = models.CharField(
        max_length=15, choices=SIGNUP_STATUS_CHOICES, default='not_started'
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile: {self.user.username}"

    @property
    def is_complete(self):
        """Quick check — used to show 'complete your profile' banner in dashboard."""
        return all([self.full_name, self.utr, self.address_line1, self.city, self.postcode])

    @property
    def is_hmrc_ready(self):
        """True once we have the minimum identifiers to actually file via MTD API."""
        return bool(self.ni_number and self.utr and self.business_id)


# ──────────────────────────────────────────────────────────────────
# Shared base for Invoice and Expense — quarter tagging + audit trail
# ──────────────────────────────────────────────────────────────────

class FinancialRecordBase(models.Model):
    transaction_date = models.DateField(
        help_text="The date this transaction actually occurred (not today's date)."
    )
    tax_year      = models.CharField(max_length=7,  db_index=True, editable=False, blank=True)
    quarter_index = models.PositiveSmallIntegerField(db_index=True, editable=False, null=True)
    quarter_key   = models.CharField(max_length=10, db_index=True, editable=False, blank=True)

    is_deleted    = models.BooleanField(default=False, db_index=True)
    deleted_at    = models.DateTimeField(null=True, blank=True)

    submitted_to_hmrc = models.BooleanField(default=False)
    locked_at         = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def _resolve_quarter(self):
        q = quarter_for_date(self.transaction_date)
        self.tax_year     = tax_year_label(q.tax_year_start_year)
        self.quarter_index = q.index
        self.quarter_key   = q.period_key

    def save(self, *args, **kwargs):
        if self.transaction_date:
            self._resolve_quarter()
        super().save(*args, **kwargs)

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    @property
    def is_locked(self):
        return self.submitted_to_hmrc


class ActiveRecordManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


# ──────────────────────────────────────────────────────────────────
# Invoice & Expense
# ──────────────────────────────────────────────────────────────────

class Invoice(FinancialRecordBase):
    STATUS_CHOICES = [('Unpaid', 'Unpaid'), ('Paid', 'Paid')]
    user        = models.ForeignKey(User, on_delete=models.CASCADE)
    client      = models.CharField(max_length=200)
    description = models.TextField()
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Unpaid')

    objects     = ActiveRecordManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"Invoice #{self.id} - {self.client}"

    class Meta:
        ordering = ['-transaction_date']


class Expense(FinancialRecordBase):
    CATEGORY_CHOICES = [
        ('Office costs',                  'Office costs'),
        ('Travel & transport',            'Travel & transport'),
        ('Clothing (uniform/protective)', 'Clothing'),
        ('Staff costs',                   'Staff costs'),
        ('Legal & financial costs',       'Legal & financial costs'),
        ('Marketing & advertising',       'Marketing & advertising'),
        ('Training courses',              'Training courses'),
        ('Software & subscriptions',      'Software & subscriptions'),
        ('Phone & internet',              'Phone & internet'),
        ('Other allowable expenses',      'Other allowable expenses'),
    ]
    user        = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.CharField(max_length=200)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    category    = models.CharField(max_length=100, choices=CATEGORY_CHOICES)

    objects     = ActiveRecordManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"{self.description} - £{self.amount}"

    class Meta:
        ordering = ['-transaction_date']


# ──────────────────────────────────────────────────────────────────
# Audit trail & submission log
# ──────────────────────────────────────────────────────────────────

class RecordEditHistory(models.Model):
    RECORD_TYPE_CHOICES = [('invoice', 'Invoice'), ('expense', 'Expense')]
    user        = models.ForeignKey(User, on_delete=models.CASCADE)
    record_type = models.CharField(max_length=10, choices=RECORD_TYPE_CHOICES)
    record_id   = models.PositiveIntegerField()
    field_name  = models.CharField(max_length=50)
    old_value   = models.TextField(blank=True)
    new_value   = models.TextField(blank=True)
    edited_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-edited_at']
        verbose_name_plural = 'Record edit history'


class SubmissionLog(models.Model):
    SUBMISSION_TYPE_CHOICES = [
        ('quarterly_update',  'Quarterly Update'),
        ('final_declaration', 'Final Declaration'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Submitted successfully'),
        ('failed',  'Failed'),
    ]
    user              = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    submission_type   = models.CharField(max_length=20, choices=SUBMISSION_TYPE_CHOICES)
    tax_year          = models.CharField(max_length=7)
    quarter_key       = models.CharField(max_length=10, blank=True)
    status            = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    hmrc_correlation_id = models.CharField(max_length=100, blank=True)
    request_payload   = models.JSONField(null=True, blank=True)
    response_payload  = models.JSONField(null=True, blank=True)
    error_message     = models.TextField(blank=True)
    submitted_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        label = self.quarter_key or f"{self.tax_year} Final Declaration"
        return f"{self.user.username} — {label} — {self.status}"
