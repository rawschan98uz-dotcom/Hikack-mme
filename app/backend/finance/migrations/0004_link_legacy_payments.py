import django.db.models.deletion
from django.db import migrations


def link_legacy_payments(apps, schema_editor):
    Payment = apps.get_model('finance', 'Payment')
    Student = apps.get_model('crm', 'Student')

    for payment in Payment.objects.filter(student__isnull=True):
        if not payment.student_name:
            continue
        p_name = payment.student_name.strip().lower()
        if not p_name:
            continue

        matched_students = []
        for s in Student.objects.filter(company_id=payment.company_id):
            full = f"{s.first_name} {s.last_name}".strip().lower()
            rev = f"{s.last_name} {s.first_name}".strip().lower()
            if full == p_name or rev == p_name:
                matched_students.append(s)

        # Strictly only link if there is exactly ONE unambiguous student match
        if len(matched_students) == 1:
            payment.student = matched_students[0]
            payment.save(update_fields=['student'])


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0003_paymenttransaction'),
        ('crm', '0016_attendancerecord_note'),
    ]

    operations = [
        migrations.RunPython(link_legacy_payments, migrations.RunPython.noop),
    ]
