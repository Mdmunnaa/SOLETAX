from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from .tax_periods import quarter_for_date, tax_year_label


# ──────────────────────────────────────────────────────────────────
# Validators for HMRC identifiers
# ──────────────────────────────────────────────────────────────────

nino_validator = RegexValidator(
    regex=r'^[A-CEGHJ-PR-TW-Z]{1}[A-CEGHJ-NPR-TW-Z]{1}[0-9]{6}[A-D]{1}$',
    message='Enter a valid National Insurance number (e.g. AB123456C), no spaces.'
)

utr_validator = RegexValidator(
    regex=r'^\d{10}$',
    message='Enter a valid 10-digit Unique Taxpayer Reference (UTR).'
)


class TaxProfile(models.Model):
    """
    One per user. Holds the HMRC identifiers and business settings needed
    to submit Income Tax (MTD) quarterly updates / final declarations.

    NOTE: nino and utr are sensitive personal identifiers. They should be
    encrypted at rest in production (e.g. via django-cryptography or a
    KMS-backed field) — stored as plain CharField here as a placeholder
    until that's wired in. Do not ship to production un-encrypted.
    """
    ACCOUNTING_BASIS_CHOICES = [
        ('cash', 'Cash basis'),
        ('accrual', 'Traditional accrual basis'),
    ]
    PERIOD_TYPE_CHOICES = [
        ('standard', 'Standard quarters (6 Apr / 6 Jul / 6 Oct / 6 Jan)'),
        ('calendar', 'Calendar quarters (1 Apr / 1 Jul / 1 Oct / 1 Jan)'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='tax_profile')

    # HMRC identifiers
    nino = models.CharField(
        'National Insurance number', max_length=9, blank=True,
        validators=[nino_validator],
        help_text='Required before any HMRC MTD submission can be made.'
    )
    utr = models.CharField(
        'Unique Taxpayer Reference', max_length=10, blank=True,
        validators=[utr_validator],
        help_text='10-digit UTR from your Self Assessment registration.'
    )
    business_id = models.CharField(
        'HMRC Business ID', max_length=50, blank=True,
        help_text='Returned by HMRC after registering a self-employment income source. '
                   'Empty until the user has linked their HMRC account via OAuth.'
    )

    # Filing preferences
    accounting_basis = models.CharField(
        max_length=10, choices=ACCOUNTING_BASIS_CHOICES, default='cash'
    )
    period_type = models.CharField(
        max_length=10, choices=PERIOD_TYPE_CHOICES, default='standard'
    )
    business_start_date = models.DateField(null=True, blank=True)

    # MTD onboarding status — tracks where this user is in the recognition/
    # sign-up journey, independent of whether HMRC integration is fully live.
    SIGNUP_STATUS_CHOICES = [
        ('not_started', 'Not signed up to MTD'),
        ('pending', 'HMRC sign-up pending'),
        ('active', 'Active on MTD for Income Tax'),
    ]
    mtd_signup_status = models.CharField(
        max_length=15, choices=SIGNUP_STATUS_CHOICES, default='not_started'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"TaxProfile({self.user.username})"

    @property
    def is_hmrc_ready(self):
        """True once we have the minimum identifiers needed to file."""
        return bool(self.nino and self.utr and self.business_id)


# ──────────────────────────────────────────────────────────────────
# Shared mixin: quarter tagging + soft delete + edit audit trail
# ──────────────────────────────────────────────────────────────────

class FinancialRecordBase(models.Model):
    """
    Common fields/behaviour for anything that feeds into an HMRC quarterly
    update (Invoice income, Expense costs). HMRC's digital record-keeping
    rules require records to be kept individually (not just as aggregates)
    and preserved — so records are soft-deleted, never hard-deleted, and
    every edit is captured in a linked audit trail.
    """
    # The actual transaction date (when the income/expense occurred),
    # editable by the user — NOT the date the row was created in our DB.
    transaction_date = models.DateField(
        help_text='The date this transaction actually occurred (not today\'s date).'
    )

    # Which HMRC tax year + quarter this falls into, denormalised for fast
    # lookups when building a quarterly update payload. Recalculated
    # automatically from transaction_date on save.
    tax_year = models.CharField(max_length=7, db_index=True, editable=False, blank=True)  # e.g. '2026-27'
    quarter_index = models.PositiveSmallIntegerField(db_index=True, editable=False, null=True)  # 1-4
    quarter_key = models.CharField(max_length=10, db_index=True, editable=False, blank=True)  # '2026-27-Q1'

    # Soft delete — HMRC requires records to be retained, not destroyed.
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Has this row already been included in a quarterly update sent to HMRC?
    # Once locked, edits should create a correction in the NEXT period rather
    # than silently mutating a figure HMRC already has.
    submitted_to_hmrc = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def _resolve_quarter(self):
        q = quarter_for_date(self.transaction_date)
        self.tax_year = tax_year_label(q.tax_year_start_year)
        self.quarter_index = q.index
        self.quarter_key = q.period_key

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
        """Once submitted to HMRC, the figure shouldn't be silently edited."""
        return self.submitted_to_hmrc


class ActiveRecordManager(models.Manager):
    """Default manager that excludes soft-deleted rows."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Invoice(FinancialRecordBase):
    STATUS_CHOICES = [('Unpaid', 'Unpaid'), ('Paid', 'Paid')]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    client = models.CharField(max_length=200)
    description = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Unpaid')

    objects = ActiveRecordManager()
    all_objects = models.Manager()  # includes soft-deleted, for audit/admin use

    def __str__(self):
        return f"Invoice #{self.id} - {self.client}"

    class Meta:
        ordering = ['-transaction_date']


class Expense(FinancialRecordBase):
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

    objects = ActiveRecordManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"{self.description} - £{self.amount}"

    class Meta:
        ordering = ['-transaction_date']


class RecordEditHistory(models.Model):
    """
    Generic audit trail entry for an edit to an Invoice or Expense.
    Stored as a simple before/after snapshot rather than a generic
    foreign key, to keep this easy to query and reason about.
    """
    RECORD_TYPE_CHOICES = [('invoice', 'Invoice'), ('expense', 'Expense')]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    record_type = models.CharField(max_length=10, choices=RECORD_TYPE_CHOICES)
    record_id = models.PositiveIntegerField()
    field_name = models.CharField(max_length=50)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    edited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-edited_at']
        verbose_name_plural = 'Record edit history'

    def __str__(self):
        return f"{self.record_type}#{self.record_id}: {self.field_name} changed"


class SubmissionLog(models.Model):
    """
    Tracks every (attempted) submission to HMRC's MTD APIs — quarterly
    updates and final declarations. This is the audit record we'd point to
    if HMRC or the user asks "what was submitted and when".

    Designed to exist independently of whether the live API call has been
    wired up yet, so the dashboard can show submission status as soon as
    the OAuth + API layer lands.
    """
    SUBMISSION_TYPE_CHOICES = [
        ('quarterly_update', 'Quarterly Update'),
        ('final_declaration', 'Final Declaration'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Submitted successfully'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    submission_type = models.CharField(max_length=20, choices=SUBMISSION_TYPE_CHOICES)
    tax_year = models.CharField(max_length=7)          # e.g. '2026-27'
    quarter_key = models.CharField(max_length=10, blank=True)  # blank for final declaration

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    hmrc_correlation_id = models.CharField(max_length=100, blank=True)
    request_payload = models.JSONField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        label = self.quarter_key or f"{self.tax_year} Final Declaration"
        return f"{self.user.username} — {label} — {self.status}"
