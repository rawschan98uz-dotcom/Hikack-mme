from django.db import migrations


def link_salary_and_payment_snapshots(apps, schema_editor):
    SalarySetting = apps.get_model('finance', 'SalarySetting')
    Payment = apps.get_model('finance', 'Payment')
    User = apps.get_model('accounts', 'User')

    # 1. Link SalarySetting to teacher User
    for setting in SalarySetting.objects.filter(teacher__isnull=True):
        if not setting.teacher_name:
            continue
        raw_name = setting.teacher_name.strip().lower()
        if not raw_name or raw_name == '—':
            continue

        matched_teachers = []
        for t in User.objects.filter(company_id=setting.company_id, user_type='teacher'):
            full = f"{t.first_name} {t.last_name}".strip().lower()
            rev = f"{t.last_name} {t.first_name}".strip().lower()
            t_phone = (t.phone or '').strip()
            if raw_name in (full, rev, t_phone, t.first_name.lower()):
                matched_teachers.append(t)

        if len(matched_teachers) == 1:
            setting.teacher = matched_teachers[0]
            setting.save(update_fields=['teacher'])

    # 2. Snapshot existing payments
    for payment in Payment.objects.filter(teacher__isnull=True):
        student = payment.student
        if student and student.group_id:
            group = student.group
            payment.group = group
            if group:
                payment.course = group.course
                payment.teacher = group.teacher
        if payment.gross_amount is None:
            payment.gross_amount = payment.amount
        if payment.net_amount is None:
            payment.net_amount = payment.amount
        payment.save(update_fields=['group', 'course', 'teacher', 'gross_amount', 'net_amount'])


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_payment_course_payment_discount_amount_and_more'),
    ]

    operations = [
        migrations.RunPython(link_salary_and_payment_snapshots, migrations.RunPython.noop),
    ]
