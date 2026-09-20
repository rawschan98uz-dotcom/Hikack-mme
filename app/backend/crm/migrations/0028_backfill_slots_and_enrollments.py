from django.db import migrations
from django.utils import timezone


def backfill_slots_and_enrollments(apps, schema_editor):
    Group = apps.get_model('crm', 'Group')
    GroupScheduleSlot = apps.get_model('crm', 'GroupScheduleSlot')
    Student = apps.get_model('crm', 'Student')
    GroupEnrollment = apps.get_model('crm', 'GroupEnrollment')

    day_mapping = {
        1: [0, 2, 4],  # ODD: Mon, Wed, Fri
        2: [1, 3, 5],  # EVEN: Tue, Thu, Sat
        3: [5, 6],     # WEEKEND: Sat, Sun
        4: [0, 1, 2, 3, 4, 5, 6],  # EVERY_DAY
        5: [0, 2, 4],  # CUSTOM
    }

    # 1. Backfill slots
    for g in Group.objects.all():
        if g.lesson_start_time and g.lesson_end_time:
            weekdays = day_mapping.get(g.days, [0, 2, 4])
            for wd in weekdays:
                GroupScheduleSlot.objects.get_or_create(
                    group=g,
                    weekday=wd,
                    defaults={
                        'start_time': g.lesson_start_time,
                        'end_time': g.lesson_end_time,
                        'room': g.room,
                    },
                )

    # 2. Backfill enrollments
    today = timezone.localdate()
    for s in Student.objects.filter(group__isnull=False).select_related('group'):
        joined = s.created_at.date() if s.created_at else today
        status = 'active'
        if s.status == 2:  # FROZEN
            status = 'frozen'
        elif s.status in (7, 8):  # LEFT
            status = 'left'
        elif s.status == 9:  # GRADUATED
            status = 'graduated'

        GroupEnrollment.objects.get_or_create(
            student=s,
            group=s.group,
            defaults={
                'company_id': s.company_id,
                'status': status,
                'joined_date': joined,
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0027_groupenrollment_groupscheduleslot_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_slots_and_enrollments, reverse_code=noop),
    ]
