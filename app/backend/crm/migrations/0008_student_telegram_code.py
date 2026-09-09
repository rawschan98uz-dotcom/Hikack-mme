# -*- coding: utf-8 -*-
import secrets

from django.db import migrations, models

ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def generate_code():
    return ''.join(secrets.choice(ALPHABET) for _ in range(8))


def backfill_codes(apps, schema_editor):
    Student = apps.get_model('crm', 'Student')
    for student in Student.objects.all():
        if student.telegram_code:
            continue
        for _ in range(20):
            code = generate_code()
            if not Student.objects.filter(telegram_code=code).exists():
                student.telegram_code = code
                student.save(update_fields=['telegram_code'])
                break


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0007_student_parent_telegram_student_telegram'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='telegram_code',
            field=models.CharField(blank=True, max_length=16, null=True, unique=True),
        ),
        migrations.RunPython(backfill_codes, migrations.RunPython.noop),
    ]
