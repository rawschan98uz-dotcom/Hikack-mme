from django.core.management.base import BaseCommand
from django.db import transaction

from crm.models import Student
from crm.services import sync_student_group_enrollment


class Command(BaseCommand):
    help = 'Bring GroupEnrollment history in line with Student.group / Student.status for all students (C1).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would change without saving.')

    def handle(self, *args, dry_run=False, **options):
        totals = {'closed': 0, 'created': 0, 'updated': 0}
        touched = 0
        with transaction.atomic():
            for student in Student.objects.all().iterator():
                result = sync_student_group_enrollment(student)
                if any(result.values()):
                    touched += 1
                for key in totals:
                    totals[key] += result[key]
            if dry_run:
                transaction.set_rollback(True)

        prefix = '[dry-run] ' if dry_run else ''
        self.stdout.write(
            f"{prefix}students fixed: {touched}; enrollments created: {totals['created']}, "
            f"closed: {totals['closed']}, status updated: {totals['updated']}"
        )
