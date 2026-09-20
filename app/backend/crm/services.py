from crm.models import Lead, Student
from api.utils import normalize_phone


def get_phone_variants(phone: str) -> list[str]:
    """Return common variants for a phone number (9 digits, with 998, with +998)."""
    raw = normalize_phone(phone)
    if not raw:
        return []
    variants = [raw]
    if len(raw) == 9:
        variants.extend([f'998{raw}', f'+998{raw}'])
    elif len(raw) == 12 and raw.startswith('998'):
        local = raw[3:]
        variants.extend([local, f'+{raw}'])
    # Preserve order while removing duplicates
    return list(dict.fromkeys(variants))


def match_student_to_lead(student: Student) -> Lead | None:
    """
    Find the best matching Lead for the given Student (in memory only, no DB writes).

    Brothers-safe:
    - Compares phone variants.
    - If phone + first_name matches:
      - If both have last_name: last_name must match.
      - If one or both lack last_name: matches if there is no conflicting lead.
    """
    phone_variants = get_phone_variants(student.phone)
    if not phone_variants:
        return None

    candidate_leads = Lead.objects.filter(
        company=student.company,
        phone__in=phone_variants,
    ).order_by('-created_at')

    s_first = (student.first_name or '').strip().lower()
    s_last = (student.last_name or '').strip().lower()

    for lead in candidate_leads:
        l_first = (lead.first_name or '').strip().lower()
        l_last = (lead.last_name or '').strip().lower()

        if l_first == s_first:
            if s_last and l_last:
                if s_last == l_last:
                    return lead
            else:
                # One of them lacks last_name — consider it a match
                return lead

    return None


def enrich_student_from_lead(student: Student, matched_lead: Lead | None) -> None:
    """
    Enrich student fields from a matched Lead or family Leads (in memory only, no DB writes).

    If matched_lead is found:
      - Sets student.lead = matched_lead
    If no exact match:
      - Copies family attributes (school, address, phone2, phone2_owner)
        from any lead with matching phone.
    """
    if matched_lead:
        student.lead = matched_lead
    else:
        # Family logic: inherit family fields from any lead with matching phone
        phone_variants = get_phone_variants(student.phone)
        if not phone_variants:
            return
        # 1. Inherit from leads with matching phone
        candidate_leads = Lead.objects.filter(
            company=student.company,
            phone__in=phone_variants,
        ).order_by('-created_at')
        for fl in candidate_leads:
            if not student.school and fl.school:
                student.school = fl.school
            if not student.address and fl.address:
                student.address = fl.address
            if not student.phone2 and fl.phone2:
                student.phone2 = fl.phone2
                if not student.phone2_owner and fl.phone2_owner:
                    student.phone2_owner = fl.phone2_owner

        # 2. Inherit from existing family students with matching phone (e.g. studying brother)
        candidate_students = Student.objects.filter(
            company=student.company,
            phone__in=phone_variants,
        ).exclude(pk=student.pk if student.pk else 0).order_by('-created_at')
        for fs in candidate_students:
            if not student.school and fs.school:
                student.school = fs.school
            if not student.address and fs.address:
                student.address = fs.address
            if not student.phone2 and fs.phone2:
                student.phone2 = fs.phone2
                if not student.phone2_owner and fs.phone2_owner:
                    student.phone2_owner = fs.phone2_owner


def update_lead_on_conversion(student: Student, lead: Lead) -> None:
    """
    Mark lead as CONVERTED and enrich lead fields from the student.
    Call this AFTER student.save() to ensure atomicity.
    """
    if lead.stage == Lead.Stage.CONVERTED:
        return  # Already converted, skip

    lead.stage = Lead.Stage.CONVERTED
    update_fields = ['stage']
    if not lead.branch and student.branch:
        lead.branch = student.branch
        update_fields.append('branch')
    if not lead.course and student.group and student.group.course:
        lead.course = student.group.course
        update_fields.append('course')
    if not lead.school and student.school:
        lead.school = student.school
        update_fields.append('school')
    lead.save(update_fields=update_fields)


def link_student_to_lead(student: Student, update_lead: bool = True) -> Lead | None:
    """
    Finds and links a matching Lead to the Student.

    This is the unified entry point that performs:
    1. match_student_to_lead() — find the best matching lead
    2. enrich_student_from_lead() — copy family/lead fields to student in memory
    3. update_lead_on_conversion() — mark lead as CONVERTED (only if update_lead=True)

    NOTE: Step 3 writes to DB. The caller is responsible for calling student.save()
    BEFORE this function if they want atomic behavior. For backward compatibility,
    this function still works if called before student.save(), but the caller should
    use the split functions for safer control.
    """
    matched_lead = match_student_to_lead(student)
    enrich_student_from_lead(student, matched_lead)

    if matched_lead and update_lead:
        update_lead_on_conversion(student, matched_lead)

    return matched_lead


def sync_student_paid_this_month(student: Student | int | None) -> bool:
    """Recalculates and updates student.paid_this_month based on actual payments in current calendar month."""
    if not student:
        return False
    if isinstance(student, int):
        student = Student.objects.filter(pk=student).first()
        if not student:
            return False

    from django.utils import timezone
    from finance.models import Payment
    today = timezone.localdate()
    has_payment_this_month = Payment.objects.filter(
        student=student,
        created_at__year=today.year,
        created_at__month=today.month,
    ).exists()

    if student.paid_this_month != has_payment_this_month:
        student.paid_this_month = has_payment_this_month
        student.save(update_fields=['paid_this_month'])
    return has_payment_this_month


def days_overlap(days1: int, days2: int) -> bool:
    """Check if two Group.Days choices have any overlapping days of the week."""
    from crm.models import Group
    if days1 == Group.Days.EVERY_DAY or days2 == Group.Days.EVERY_DAY:
        return True
    if days1 == Group.Days.CUSTOM or days2 == Group.Days.CUSTOM:
        return True
    mapping = {
        Group.Days.ODD: {0, 2, 4},
        Group.Days.EVEN: {1, 3, 5},
        Group.Days.WEEKEND: {5, 6},
    }
    set1 = mapping.get(days1, set())
    set2 = mapping.get(days2, set())
    return bool(set1 & set2)


def dates_overlap(start1, end1, start2, end2) -> bool:
    """Check if two date ranges [start1, end1] and [start2, end2] intersect."""
    if end1 and start2 and end1 < start2:
        return False
    if end2 and start1 and end2 < start1:
        return False
    return True


def times_overlap(start1, end1, start2, end2) -> bool:
    """Check if two time intervals (start1, end1) and (start2, end2) overlap."""
    if not (start1 and end1 and start2 and end2):
        return False
    return start1 < end2 and start2 < end1


def sync_group_schedule_slots(group, weekdays=None):
    """
    Synchronize normalized GroupScheduleSlot records for a group based on its
    lesson_start_time, lesson_end_time, room, and days (or explicit weekdays).
    """
    from crm.models import Group, GroupScheduleSlot

    if not (group.lesson_start_time and group.lesson_end_time):
        group.schedule_slots.all().delete()
        return

    if weekdays is None:
        mapping = {
            Group.Days.ODD: [0, 2, 4],
            Group.Days.EVEN: [1, 3, 5],
            Group.Days.WEEKEND: [5, 6],
            Group.Days.EVERY_DAY: [0, 1, 2, 3, 4, 5, 6],
            Group.Days.CUSTOM: [0, 2, 4],
        }
        weekdays = mapping.get(group.days, [0, 2, 4])

    group.schedule_slots.exclude(weekday__in=weekdays).delete()

    for wd in weekdays:
        GroupScheduleSlot.objects.update_or_create(
            group=group,
            weekday=wd,
            defaults={
                'start_time': group.lesson_start_time,
                'end_time': group.lesson_end_time,
                'room': group.room,
            },
        )



def validate_group_schedule(
    company,
    branch,
    teacher,
    room,
    days: int,
    start_time,
    end_time,
    start_date=None,
    end_date=None,
    exclude_group_id=None,
) -> dict | None:
    """
    Validate schedule consistency and check for room and teacher collisions.
    Returns None if valid, or a dict describing the error/conflict.
    """
    from accounts.models import TeacherBranch
    from crm.models import Group

    # Time validations
    if bool(start_time) != bool(end_time):
        return {
            'status_code': 400,
            'code': 'invalid_time_range',
            'message': 'Both lesson start time and lesson end time are required if one is set.',
        }
    if start_time and end_time and start_time >= end_time:
        return {
            'status_code': 400,
            'code': 'invalid_time_range',
            'message': 'Lesson start time must be before lesson end time.',
        }

    # Date validations
    if start_date and end_date and start_date > end_date:
        return {
            'status_code': 400,
            'code': 'invalid_date_range',
            'message': 'Group start date must be before or equal to group end date.',
        }

    # Branch consistency
    if room and room.branch_id != branch.id:
        return {
            'status_code': 400,
            'code': 'invalid_room_branch',
            'message': 'Room belongs to a different branch.',
        }

    if teacher:
        if not TeacherBranch.objects.filter(teacher=teacher, branch=branch).exists():
            return {
                'status_code': 400,
                'code': 'teacher_not_in_branch',
                'message': 'Teacher is not assigned to this branch.',
            }

    # If no times are specified, no slot collisions to check
    if not (start_time and end_time):
        return None

    # Collision detection with active groups
    candidates = Group.objects.filter(
        company=company,
        status=Group.Status.ACTIVE,
    )
    if exclude_group_id:
        candidates = candidates.exclude(pk=exclude_group_id)

    conflicts = []
    for g in candidates:
        if not g.lesson_start_time or not g.lesson_end_time:
            continue
        if not days_overlap(days, g.days):
            continue
        if not dates_overlap(start_date, end_date, g.group_start_date, g.group_end_date):
            continue
        if not times_overlap(start_time, end_time, g.lesson_start_time, g.lesson_end_time):
            continue

        if room and g.room_id == room.id:
            conflicts.append({
                'type': 'room',
                'group_id': g.id,
                'group_name': g.name,
                'room_name': room.name,
            })

        if teacher and g.teacher_id == teacher.id:
            conflicts.append({
                'type': 'teacher',
                'group_id': g.id,
                'group_name': g.name,
                'teacher_name': teacher.display_name(),
            })

    if conflicts:
        msgs = []
        room_conflicts = [c for c in conflicts if c['type'] == 'room']
        teacher_conflicts = [c for c in conflicts if c['type'] == 'teacher']
        if room_conflicts:
            msgs.append(f"Room collision: '{room.name}' is already occupied by '{room_conflicts[0]['group_name']}'")
        if teacher_conflicts:
            msgs.append(f"Teacher collision: '{teacher.display_name()}' already has group '{teacher_conflicts[0]['group_name']}'")
        return {
            'status_code': 409,
            'code': 'schedule_conflict',
            'message': '; '.join(msgs),
            'conflicts': conflicts,
        }

    return None


def sync_student_group_enrollment(student: Student, old_group_id: int | None = None, old_status: int | None = None) -> None:
    """
    Maintain GroupEnrollment lifecycle when a student is created, assigned, transferred, or changes status.
    """
    from django.utils import timezone
    from crm.models import GroupEnrollment

    today = timezone.localdate()

    # Case 1: Group changed
    if student.group_id != old_group_id:
        if old_group_id:
            GroupEnrollment.objects.filter(
                student=student,
                group_id=old_group_id,
                left_date__isnull=True,
            ).update(
                left_date=today,
                status=GroupEnrollment.Status.TRANSFERRED if student.group_id else GroupEnrollment.Status.LEFT,
            )
        if student.group_id:
            GroupEnrollment.objects.create(
                company=student.company,
                student=student,
                group=student.group,
                status=GroupEnrollment.Status.ACTIVE if student.status == Student.Status.STUDYING else GroupEnrollment.Status.FROZEN,
                joined_date=today,
            )
        return

    # Case 2: Same group, but student status changed
    if student.group_id and old_status is not None and old_status != student.status:
        active_enrollments = GroupEnrollment.objects.filter(
            student=student,
            group_id=student.group_id,
            left_date__isnull=True,
        )
        if student.status == Student.Status.FROZEN:
            active_enrollments.update(status=GroupEnrollment.Status.FROZEN)
        elif student.status == Student.Status.STUDYING:
            active_enrollments.update(status=GroupEnrollment.Status.ACTIVE)
        elif student.status in (Student.Status.LEFT, Student.Status.LEFT_TRIAL):
            active_enrollments.update(status=GroupEnrollment.Status.LEFT, left_date=today)
        elif student.status == Student.Status.GRADUATED:
            active_enrollments.update(status=GroupEnrollment.Status.GRADUATED, left_date=today)


