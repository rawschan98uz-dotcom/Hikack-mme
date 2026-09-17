import base64
from urllib.parse import urlencode


def build_click_link(company, student_id: int, amount: int, return_url: str = '') -> str:
    service_id = (company.click_service_id or '').strip()
    merchant_id = (company.click_merchant_id or '').strip()
    params = {
        'service_id': service_id or '0',
        'merchant_id': merchant_id or '0',
        'amount': amount,
        'transaction_param': str(student_id),
    }
    if return_url:
        params['return_url'] = return_url
    return f"https://my.click.uz/services/pay?{urlencode(params)}"


def build_payme_link(company, student_id: int, amount: int) -> str:
    merchant_id = (company.payme_merchant_id or '').strip() or 'merchant_id'
    # Amount in tiyin (1 UZS = 100 tiyin)
    tiyin = int(amount) * 100
    param_str = f"m={merchant_id};ac.student_id={student_id};a={tiyin}"
    encoded = base64.b64encode(param_str.encode('utf-8')).decode('utf-8')
    return f"https://checkout.paycom.uz/{encoded}"


def build_uzum_link(company, student_id: int, amount: int) -> str:
    merchant_id = (company.uzum_merchant_id or '').strip() or 'merchant_id'
    params = {
        'merchant_id': merchant_id,
        'amount': amount,
        'student_id': str(student_id),
    }
    return f"https://www.uzumbank.uz/pay?{urlencode(params)}"


def get_student_payment_links(student, amount: int | None = None) -> dict:
    company = student.company
    if amount is None or amount <= 0:
        if student.group and student.group.course and student.group.course.price:
            amount = student.group.course.price
        else:
            amount = 0

    click_configured = bool(company.click_service_id and company.click_merchant_id)
    payme_configured = bool(company.payme_merchant_id)
    uzum_configured = bool(company.uzum_merchant_id)

    return {
        'student_id': student.id,
        'student_name': student.full_name,
        'amount': amount,
        'click': {
            'url': build_click_link(company, student.id, amount),
            'configured': click_configured,
        },
        'payme': {
            'url': build_payme_link(company, student.id, amount),
            'configured': payme_configured,
        },
        'uzum': {
            'url': build_uzum_link(company, student.id, amount),
            'configured': uzum_configured,
        },
    }
