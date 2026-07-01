from django.contrib import admin
from .models import Invoice, Expense, UserProfile, RecordEditHistory, SubmissionLog


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'full_name', 'utr', 'mtd_signup_status', 'is_complete_display', 'is_hmrc_ready_display')
    list_filter   = ('mtd_signup_status', 'accounting_basis', 'is_vat_registered')
    search_fields = ('user__username', 'full_name', 'utr', 'business_id')
    readonly_fields = ('updated_at',)

    @admin.display(boolean=True, description='Profile complete')
    def is_complete_display(self, obj):
        return obj.is_complete

    @admin.display(boolean=True, description='HMRC API ready')
    def is_hmrc_ready_display(self, obj):
        return obj.is_hmrc_ready


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'client', 'amount', 'transaction_date', 'quarter_key', 'status', 'submitted_to_hmrc', 'is_deleted')
    list_filter   = ('status', 'is_deleted', 'submitted_to_hmrc', 'tax_year', 'quarter_index')
    search_fields = ('client', 'description', 'user__username')
    readonly_fields = ('tax_year', 'quarter_index', 'quarter_key', 'created_at', 'updated_at')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'description', 'category', 'amount', 'transaction_date', 'quarter_key', 'submitted_to_hmrc', 'is_deleted')
    list_filter   = ('category', 'is_deleted', 'submitted_to_hmrc', 'tax_year', 'quarter_index')
    search_fields = ('description', 'user__username')
    readonly_fields = ('tax_year', 'quarter_index', 'quarter_key', 'created_at', 'updated_at')


@admin.register(RecordEditHistory)
class RecordEditHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'record_type', 'record_id', 'field_name', 'old_value', 'new_value', 'edited_at')
    list_filter  = ('record_type', 'field_name')
    readonly_fields = [f.name for f in RecordEditHistory._meta.fields]
    def has_add_permission(self, request):    return False
    def has_change_permission(self, request, obj=None): return False


@admin.register(SubmissionLog)
class SubmissionLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'submission_type', 'tax_year', 'quarter_key', 'status', 'submitted_at')
    list_filter  = ('submission_type', 'status', 'tax_year')
    readonly_fields = ('submitted_at',)
