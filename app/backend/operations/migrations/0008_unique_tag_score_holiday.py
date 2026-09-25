from django.db import migrations, models
import django.db.models.functions.text


def dedupe(apps, schema_editor):
    """D1: clean duplicates before adding unique constraints."""
    Tag = apps.get_model('operations', 'Tag')
    StudentScore = apps.get_model('operations', 'StudentScore')
    Holiday = apps.get_model('operations', 'Holiday')

    # Tags: merge duplicates (case-insensitive) into the oldest one, moving group/lead links.
    keep_by_key = {}
    for tag in Tag.objects.order_by('company_id', 'id'):
        key = (tag.company_id, tag.name.strip().lower())
        keeper = keep_by_key.get(key)
        if keeper is None:
            keep_by_key[key] = tag
            continue
        for rel in tag._meta.related_objects:
            if not rel.many_to_many:
                continue
            accessor = rel.get_accessor_name()
            for obj in getattr(tag, accessor).all():
                getattr(obj, rel.field.name).add(keeper)
        tag.delete()

    # Scores: keep the most recently updated grade per (student, group).
    seen = set()
    for score in StudentScore.objects.order_by('student_id', 'group_id', '-updated_at', '-id'):
        key = (score.student_id, score.group_id)
        if key in seen:
            score.delete()
        else:
            seen.add(key)

    # Holidays: one per (company, branch, date).
    seen = set()
    for holiday in Holiday.objects.order_by('company_id', 'branch_id', 'holiday_date', 'id'):
        key = (holiday.company_id, holiday.branch_id, holiday.holiday_date)
        if key in seen:
            holiday.delete()
        else:
            seen.add(key)


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0007_delete_activitylog'),
        ('crm', '0030_group_weekdays_alter_group_branch_and_more'),
        ('org', '0007_room_company_branch_unique'),
    ]

    operations = [
        migrations.RunPython(dedupe, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='tag',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower('name'), models.F('company'),
                name='uniq_tag_name_per_company',
            ),
        ),
        migrations.AddConstraint(
            model_name='studentscore',
            constraint=models.UniqueConstraint(fields=('student', 'group'), name='uniq_score_per_student_group'),
        ),
        migrations.AddConstraint(
            model_name='holiday',
            constraint=models.UniqueConstraint(
                fields=('company', 'branch', 'holiday_date'), name='uniq_holiday_per_branch_day',
            ),
        ),
    ]
