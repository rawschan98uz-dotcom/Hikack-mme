from django.db import migrations, models
import django.db.models.functions.text


def merge_duplicate_categories(apps, schema_editor):
    """D1 / section 7 p.12: merge duplicate expense categories (case-insensitive) into the oldest one."""
    ExpenseCategory = apps.get_model('finance', 'ExpenseCategory')
    Expense = apps.get_model('finance', 'Expense')
    keep_by_key = {}
    for category in ExpenseCategory.objects.order_by('company_id', 'id'):
        key = (category.company_id, category.name.strip().lower())
        keeper = keep_by_key.get(key)
        if keeper is None:
            keep_by_key[key] = category
            continue
        Expense.objects.filter(category_id=category.id).update(category_id=keeper.id)
        category.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0007_remove_paymenttransaction_finance_pay_company_bcfdc4_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_categories, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='expensecategory',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower('name'), models.F('company'),
                name='uniq_expense_category_per_company',
            ),
        ),
    ]
