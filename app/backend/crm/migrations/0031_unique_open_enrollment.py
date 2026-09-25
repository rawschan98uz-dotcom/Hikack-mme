from django.db import migrations, models
from django.utils import timezone


def close_duplicate_open_enrollments(apps, schema_editor):
    """D1: only one open enrollment per (student, group); extra ones are closed."""
    GroupEnrollment = apps.get_model('crm', 'GroupEnrollment')
    today = timezone.localdate()
    seen = set()
    for enrollment in GroupEnrollment.objects.filter(left_date__isnull=True).order_by('student_id', 'group_id', 'joined_date', 'id'):
        key = (enrollment.student_id, enrollment.group_id)
        if key in seen:
            enrollment.left_date = today
            enrollment.status = 'left'
            enrollment.note = 'duplicate open enrollment closed by migration'
            enrollment.save(update_fields=['left_date', 'status', 'note'])
        else:
            seen.add(key)


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0030_group_weekdays_alter_group_branch_and_more'),
    ]

    operations = [
        migrations.RunPython(close_duplicate_open_enrollments, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='groupenrollment',
            constraint=models.UniqueConstraint(
                condition=models.Q(('left_date__isnull', True)),
                fields=('student', 'group'),
                name='uniq_open_enrollment_per_student_group',
            ),
        ),
    ]
