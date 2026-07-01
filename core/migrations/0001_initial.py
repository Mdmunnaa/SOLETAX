import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name',     models.CharField(blank=True, max_length=200)),
                ('business_name', models.CharField(blank=True, max_length=200, help_text='Your trading name, if different from your own name')),
                ('phone',         models.CharField(blank=True, max_length=30)),
                ('utr', models.CharField(blank=True, max_length=10, verbose_name='UTR (Unique Taxpayer Reference)', help_text='10-digit number from HMRC, e.g. 1234567890', validators=[django.core.validators.RegexValidator(message='Enter a valid 10-digit Unique Taxpayer Reference (UTR).', regex='^\\d{10}$')])),
                ('ni_number', models.CharField(blank=True, max_length=9, verbose_name='National Insurance Number', help_text='e.g. AB123456C — no spaces', validators=[django.core.validators.RegexValidator(message='Enter a valid National Insurance number (e.g. AB123456C), no spaces.', regex='^[A-CEGHJ-PR-TW-Z]{1}[A-CEGHJ-NPR-TW-Z]{1}[0-9]{6}[A-D]{1}$')])),
                ('business_id',   models.CharField(blank=True, max_length=50, verbose_name='HMRC Business ID', help_text='Returned by HMRC after OAuth. Empty until user links HMRC account.')),
                ('is_vat_registered', models.BooleanField(default=False, verbose_name='VAT Registered?')),
                ('vat_number',    models.CharField(blank=True, max_length=20, verbose_name='VAT Number')),
                ('address_line1', models.CharField(blank=True, max_length=200)),
                ('address_line2', models.CharField(blank=True, max_length=200)),
                ('city',          models.CharField(blank=True, max_length=100)),
                ('postcode',      models.CharField(blank=True, max_length=20)),
                ('accounting_basis',    models.CharField(choices=[('cash', 'Cash basis'), ('accrual', 'Traditional accrual basis')], default='cash', max_length=10)),
                ('period_type',         models.CharField(choices=[('standard', 'Standard quarters (6 Apr / 6 Jul / 6 Oct / 6 Jan)'), ('calendar', 'Calendar quarters (1 Apr / 1 Jul / 1 Oct / 1 Jan)')], default='standard', max_length=10)),
                ('business_start_date',   models.DateField(blank=True, null=True, help_text='Usually 6 April')),
                ('accounting_period_end', models.DateField(blank=True, null=True, help_text='Usually 5 April next year')),
                ('mtd_signup_status', models.CharField(choices=[('not_started', 'Not signed up to MTD'), ('pending', 'HMRC sign-up pending'), ('active', 'Active on MTD for Income Tax')], default='not_started', max_length=15)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),

        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_date', models.DateField(help_text="The date this transaction actually occurred (not today's date).")),
                ('tax_year',      models.CharField(blank=True, db_index=True, editable=False, max_length=7)),
                ('quarter_index', models.PositiveSmallIntegerField(db_index=True, editable=False, null=True)),
                ('quarter_key',   models.CharField(blank=True, db_index=True, editable=False, max_length=10)),
                ('is_deleted',    models.BooleanField(db_index=True, default=False)),
                ('deleted_at',    models.DateTimeField(blank=True, null=True)),
                ('submitted_to_hmrc', models.BooleanField(default=False)),
                ('locked_at',    models.DateTimeField(blank=True, null=True)),
                ('created_at',   models.DateTimeField(auto_now_add=True)),
                ('updated_at',   models.DateTimeField(auto_now=True)),
                ('client',       models.CharField(max_length=200)),
                ('description',  models.TextField()),
                ('amount',       models.DecimalField(decimal_places=2, max_digits=10)),
                ('status',       models.CharField(choices=[('Unpaid', 'Unpaid'), ('Paid', 'Paid')], default='Unpaid', max_length=10)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-transaction_date']},
        ),

        migrations.CreateModel(
            name='Expense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_date', models.DateField(help_text="The date this transaction actually occurred (not today's date).")),
                ('tax_year',      models.CharField(blank=True, db_index=True, editable=False, max_length=7)),
                ('quarter_index', models.PositiveSmallIntegerField(db_index=True, editable=False, null=True)),
                ('quarter_key',   models.CharField(blank=True, db_index=True, editable=False, max_length=10)),
                ('is_deleted',    models.BooleanField(db_index=True, default=False)),
                ('deleted_at',    models.DateTimeField(blank=True, null=True)),
                ('submitted_to_hmrc', models.BooleanField(default=False)),
                ('locked_at',    models.DateTimeField(blank=True, null=True)),
                ('created_at',   models.DateTimeField(auto_now_add=True)),
                ('updated_at',   models.DateTimeField(auto_now=True)),
                ('description',  models.CharField(max_length=200)),
                ('amount',       models.DecimalField(decimal_places=2, max_digits=10)),
                ('category',     models.CharField(choices=[('Office costs', 'Office costs'), ('Travel & transport', 'Travel & transport'), ('Clothing (uniform/protective)', 'Clothing'), ('Staff costs', 'Staff costs'), ('Legal & financial costs', 'Legal & financial costs'), ('Marketing & advertising', 'Marketing & advertising'), ('Training courses', 'Training courses'), ('Software & subscriptions', 'Software & subscriptions'), ('Phone & internet', 'Phone & internet'), ('Other allowable expenses', 'Other allowable expenses')], max_length=100)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-transaction_date']},
        ),

        migrations.CreateModel(
            name='RecordEditHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('record_type', models.CharField(choices=[('invoice', 'Invoice'), ('expense', 'Expense')], max_length=10)),
                ('record_id',   models.PositiveIntegerField()),
                ('field_name',  models.CharField(max_length=50)),
                ('old_value',   models.TextField(blank=True)),
                ('new_value',   models.TextField(blank=True)),
                ('edited_at',   models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name_plural': 'Record edit history', 'ordering': ['-edited_at']},
        ),

        migrations.CreateModel(
            name='SubmissionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('submission_type', models.CharField(choices=[('quarterly_update', 'Quarterly Update'), ('final_declaration', 'Final Declaration')], max_length=20)),
                ('tax_year',    models.CharField(max_length=7)),
                ('quarter_key', models.CharField(blank=True, max_length=10)),
                ('status',      models.CharField(choices=[('pending', 'Pending'), ('success', 'Submitted successfully'), ('failed', 'Failed')], default='pending', max_length=10)),
                ('hmrc_correlation_id', models.CharField(blank=True, max_length=100)),
                ('request_payload',  models.JSONField(blank=True, null=True)),
                ('response_payload', models.JSONField(blank=True, null=True)),
                ('error_message',    models.TextField(blank=True)),
                ('submitted_at',     models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submissions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-submitted_at']},
        ),
    ]
