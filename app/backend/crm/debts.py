"""Reminder for the office when a student leaves without paying."""

from django.utils import timezone

from crm.models import Student


def _money(value: int) -> str:
    return f'{value:,}'.replace(',', ' ')


def remind_about_unpaid_leave(student: Student):
    """
    Create a reminder "left without paying" for administrators and the CEO.
    It is not assigned to anyone, so every office user sees it (teachers do not), and it stays on
    the dashboard as overdue until somebody marks it done.
    """
    from api.v1.views import student_debt_on
    from operations.models import Reminder

    debt = student_debt_on(student)
    if debt is None:
        return None

    verb = 'Завершил курс' if student.status == Student.Status.GRADUATED else 'Ушёл'
    title = f'{verb} с долгом: {student.full_name}'
    if Reminder.objects.filter(
        student=student, kind=Reminder.KIND_UNPAID_LEAVE,
    ).exclude(status=Reminder.Status.DONE).exists():
        return None

    # Exact since the month lines: every owed month at its own price
    amount = ''
    if debt['approx_amount']:
        amount = f', {_money(debt["approx_amount"])} сум'
        if debt['monthly_price'] and debt['months'] > 1:
            amount += f' ({debt["months"]} × {_money(debt["monthly_price"])})'
    phones = f'Телефон: {student.phone}' + (f', доп.: {student.phone2}' if student.phone2 else '')
    lines = [
        f'Не оплачено: {debt["months"]} мес. — с {debt["unpaid_since"].strftime("%d.%m.%Y")}{amount}.',
        phones,
    ]
    if student.parent_telegram:
        lines.append(f'Telegram родителя: {student.parent_telegram}')
    return Reminder.objects.create(
        company_id=student.company_id,
        student=student,
        kind=Reminder.KIND_UNPAID_LEAVE,
        title=title[:255],
        details='\n'.join(lines),
        due_date=timezone.localdate(),
        status=Reminder.Status.TODAY,
    )


LOCKED_MESSAGE = (
    'Долг ученика ещё не оплачен. Примите оплату в карточке ученика — после этого напоминание можно закрыть. '
    'Закрыть без оплаты может только CEO, указав причину списания.'
)


def unpaid_leave_state(reminder) -> dict:
    """
    Live state of a "left without paying" reminder: is the debt still there (then the reminder is locked:
    it cannot be closed, edited or deleted) and how much is left. Other reminders are never locked.
    """
    from api.v1.views import student_debt_on
    from operations.models import Reminder

    if reminder.kind != Reminder.KIND_UNPAID_LEAVE or reminder.student_id is None \
            or reminder.status == Reminder.Status.DONE:
        return {'locked': False, 'debt_months': 0, 'debt_amount': 0}
    left_on = timezone.localtime(reminder.created_at).date()
    debt = student_debt_on(reminder.student, left_on)
    if debt is None:
        return {'locked': False, 'debt_months': 0, 'debt_amount': 0}
    return {'locked': True, 'debt_months': debt['months'], 'debt_amount': debt['approx_amount']}


def close_unpaid_leave(reminder, user, write_off_reason: str = '') -> str | None:
    """
    Close a "left without paying" reminder. Returns an error text, or None when closed.
    Paid -> anyone who may manage reminders; not paid -> only the CEO with a reason (written off).
    """
    from accounts.rbac import ROLE_CEO, get_effective_role
    from operations.models import Reminder, log_audit

    state = unpaid_leave_state(reminder)
    stamp = timezone.localdate().strftime('%d.%m.%Y')
    who = user.display_name() if hasattr(user, 'display_name') else str(user)
    if state['locked']:
        is_ceo = user.is_superuser or get_effective_role(user) == ROLE_CEO
        reason = (write_off_reason or '').strip()
        if not is_ceo:
            return LOCKED_MESSAGE
        if len(reason) < 3:
            return 'Укажите причину списания долга.'
        reminder.resolution = (
            f'Долг списан {stamp}, CEO {who}: {reason} '
            f'(не оплачено {state["debt_months"]} мес., ≈ {_money(state["debt_amount"])} сум)'
        )
        log_audit(
            company=reminder.company, actor=user, entity_type='student', entity_id=reminder.student_id,
            action='debt_write_off', reason=reason,
            old_values={'debt_months': state['debt_months'], 'debt_amount': state['debt_amount']},
        )
        reminder.written_off = True
        # The forgiven months are closed in the student's lines: they are no debt anywhere any more
        from finance.charges import write_off
        write_off(reminder.student, timezone.localtime(reminder.created_at).date())
    else:
        reminder.resolution = f'Долг оплачен, закрыто {stamp} ({who})'
    reminder.status = Reminder.Status.DONE
    reminder.save(update_fields=['status', 'resolution', 'written_off'])
    return None


def close_on_return(student: Student) -> None:
    """
    A student who left with a debt was put back to studying: the debt is not forgiven, it simply moves to the
    ordinary "Debtors" list, so the pinned "left without paying" reminder is closed with a note.
    """
    from operations.models import Reminder

    stamp = timezone.localdate().strftime('%d.%m.%Y')
    Reminder.objects.filter(student=student, kind=Reminder.KIND_UNPAID_LEAVE).exclude(
        status=Reminder.Status.DONE,
    ).update(
        status=Reminder.Status.DONE,
        resolution=f'Ученик вернулся к обучению {stamp} — долг перешёл в список «Должники»',
    )


def written_off_debts(student_ids) -> dict:
    """student id -> resolution text of the latest "left without paying" reminder, if the CEO wrote that debt off."""
    from operations.models import Reminder

    result = {}
    rows = Reminder.objects.filter(
        student_id__in=list(student_ids), kind=Reminder.KIND_UNPAID_LEAVE,
    ).order_by('student_id', 'created_at', 'id').values('student_id', 'written_off', 'resolution')
    for row in rows:
        # The latest reminder of each student wins (a student may leave, come back and leave again)
        if row['written_off']:
            result[row['student_id']] = row['resolution']
        else:
            result.pop(row['student_id'], None)
    return result
