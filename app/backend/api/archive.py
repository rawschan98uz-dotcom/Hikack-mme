"""Single teacher-archiving routine shared by the archive screen and teacher DELETE (A4)."""

from accounts.models import User
from crm.models import Group
from operations.models import ArchivedPerson


def archive_teacher(company, teacher: User, *, reason: str = '', comment: str = '', create_record: bool = True):
    """
    Deactivate a teacher, detach them from active groups and make sure they appear in the archive.
    Archived groups keep their teacher for history (attendance, payroll).
    """
    if teacher.company_id != company.id:
        raise ValueError('Teacher belongs to another company')

    if teacher.is_active:
        teacher.is_active = False
        teacher.save(update_fields=['is_active'])
    Group.objects.filter(company=company, teacher=teacher, status=Group.Status.ACTIVE).update(teacher=None)

    if not create_record:
        return None
    person = ArchivedPerson.objects.filter(company=company, phone=teacher.phone, roles__icontains='teacher').first()
    if person is None:
        person = ArchivedPerson.objects.create(
            company=company,
            name=teacher.get_full_name() or teacher.phone,
            phone=teacher.phone,
            roles='teacher',
            reason=reason,
            comment=comment,
        )
    return person
