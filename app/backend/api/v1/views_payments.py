import base64
import hashlib
import json
import time

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from api.responses import fail, ok
from crm.models import Student
from finance.gateways import get_student_payment_links
from finance.models import Payment, PaymentTransaction
from operations.notify import send_payment_receipt_telegram, send_telegram_payment_link
from org.models import Company


def _company(request):
    return request.user.company


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_payment_links(request, student_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        student = Student.objects.select_related('group', 'group__course', 'company').get(
            pk=student_id, company=company
        )
    except Student.DoesNotExist:
        return fail('Student not found', status_code=404)

    amount = request.query_params.get('amount')
    try:
        amount_val = int(amount) if amount else None
    except (ValueError, TypeError):
        amount_val = None

    data = get_student_payment_links(student, amount_val)
    return ok(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def student_send_payment_link(request, student_id: int):
    company = _company(request)
    if company is None:
        return fail('Company not found', status_code=404)

    try:
        student = Student.objects.select_related('group', 'group__course', 'company').get(
            pk=student_id, company=company
        )
    except Student.DoesNotExist:
        return fail('Student not found', status_code=404)

    amount = request.data.get('amount')
    try:
        amount_val = int(amount) if amount else None
    except (ValueError, TypeError):
        amount_val = None

    intro = str(request.data.get('message') or '').strip()
    success, msg = send_telegram_payment_link(student, amount_val, intro)
    if not success:
        return fail(msg, status_code=400)
    return ok({'message': msg, 'sent': True})


# =========================================================================
# Click Merchant API Webhook (Prepare / Complete)
# =========================================================================

@csrf_exempt
def click_webhook(request):
    """Handles Click Prepare (action=0) and Complete (action=1) merchant callbacks."""
    if request.method != 'POST':
        return JsonResponse({'error': -8, 'error_note': 'Only POST method is supported'})

    post_data = request.POST if request.POST else {}
    if not post_data and request.body:
        try:
            post_data = json.loads(request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            post_data = {}

    click_trans_id = str(post_data.get('click_trans_id') or '').strip()
    service_id = str(post_data.get('service_id') or '').strip()
    merchant_trans_id = str(post_data.get('merchant_trans_id') or '').strip()  # student_id
    merchant_prepare_id = str(post_data.get('merchant_prepare_id') or '').strip()
    amount_raw = post_data.get('amount')
    action = str(post_data.get('action') or '0').strip()
    sign_time = str(post_data.get('sign_time') or '').strip()
    sign_string = str(post_data.get('sign_string') or '').strip()

    try:
        amount = int(float(amount_raw or 0))
    except (ValueError, TypeError):
        amount = 0

    # Locate company
    company = None
    if service_id:
        company = Company.objects.filter(click_service_id=service_id).first()
    if not company:
        company = Company.objects.filter(click_merchant_id__gt='').first() or Company.objects.first()

    if not company:
        return JsonResponse({'error': -8, 'error_note': 'Company not configured for Click'})

    secret_key = (company.click_secret_key or '').strip()

    # Find student
    try:
        student = Student.objects.select_related('group', 'group__course', 'company').get(
            pk=int(merchant_trans_id), company=company
        )
    except (Student.DoesNotExist, ValueError, TypeError):
        student = None

    # Validate action 0: Prepare
    if action == '0':
        if not student:
            return JsonResponse({
                'click_trans_id': click_trans_id,
                'merchant_trans_id': merchant_trans_id,
                'error': -5,
                'error_note': 'User does not exist',
            })

        # Signature verification if secret_key is set
        if secret_key:
            expected_str = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{amount_raw}{action}{sign_time}"
            expected_sign = hashlib.md5(expected_str.encode('utf-8')).hexdigest()
            if sign_string.lower() != expected_sign.lower():
                return JsonResponse({
                    'click_trans_id': click_trans_id,
                    'merchant_trans_id': merchant_trans_id,
                    'error': -1,
                    'error_note': 'Sign check failed',
                })

        tx, _ = PaymentTransaction.objects.get_or_create(
            company=company,
            provider=PaymentTransaction.Provider.CLICK,
            trans_id=click_trans_id,
            defaults={
                'student': student,
                'amount': amount,
                'status': PaymentTransaction.Status.PENDING,
                'data': {'sign_time': sign_time},
            },
        )

        return JsonResponse({
            'click_trans_id': click_trans_id,
            'merchant_trans_id': merchant_trans_id,
            'merchant_prepare_id': tx.id,
            'error': 0,
            'error_note': 'Success',
        })

    # Validate action 1: Complete
    elif action == '1':
        # Signature verification if secret_key is set
        if secret_key:
            expected_str = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{merchant_prepare_id}{amount_raw}{action}{sign_time}"
            expected_sign = hashlib.md5(expected_str.encode('utf-8')).hexdigest()
            if sign_string.lower() != expected_sign.lower():
                return JsonResponse({
                    'click_trans_id': click_trans_id,
                    'merchant_trans_id': merchant_trans_id,
                    'error': -1,
                    'error_note': 'Sign check failed',
                })

        tx = PaymentTransaction.objects.filter(
            company=company,
            provider=PaymentTransaction.Provider.CLICK,
            trans_id=click_trans_id,
        ).first()

        if not tx:
            if merchant_prepare_id:
                tx = PaymentTransaction.objects.filter(pk=merchant_prepare_id, company=company).first()

        if not tx:
            return JsonResponse({
                'click_trans_id': click_trans_id,
                'merchant_trans_id': merchant_trans_id,
                'error': -6,
                'error_note': 'Transaction does not exist',
            })

        if tx.status == PaymentTransaction.Status.COMPLETED and tx.payment:
            return JsonResponse({
                'click_trans_id': click_trans_id,
                'merchant_trans_id': merchant_trans_id,
                'merchant_confirm_id': tx.id,
                'error': 0,
                'error_note': 'Success (already completed)',
            })

        student = tx.student
        course_price = student.group.course.price if (student.group and student.group.course) else 0
        months_covered = 1
        if course_price and course_price > 0 and amount >= course_price:
            months_covered = max(1, round(amount / course_price))

        payment = Payment.objects.create(
            company=company,
            student=student,
            student_name=student.full_name,
            amount=amount,
            months_covered=months_covered,
            method=Payment.Method.CARD,
            comment=f'Click trans #{click_trans_id}',
        )

        tx.status = PaymentTransaction.Status.COMPLETED
        tx.payment = payment
        tx.save()

        # Update paid_this_month
        now = timezone.localtime(payment.created_at)
        today = timezone.localdate()
        if now.year == today.year and now.month == today.month:
            student.paid_this_month = True
            student.save(update_fields=['paid_this_month'])

        # Instant Telegram receipt
        send_payment_receipt_telegram(payment)

        return JsonResponse({
            'click_trans_id': click_trans_id,
            'merchant_trans_id': merchant_trans_id,
            'merchant_confirm_id': tx.id,
            'error': 0,
            'error_note': 'Success',
        })

    return JsonResponse({'error': -3, 'error_note': 'Unknown action'})


# =========================================================================
# Payme Merchant API Webhook (JSON-RPC 2.0)
# =========================================================================

@csrf_exempt
def payme_webhook(request):
    """Handles Payme JSON-RPC 2.0 callbacks."""
    if request.method != 'POST':
        return JsonResponse({'error': {'code': -32600, 'message': 'Invalid Request'}}, status=400)

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': {'code': -32700, 'message': 'Parse error'}}, status=400)

    req_id = body.get('id')
    method = body.get('method')
    params = body.get('params') or {}

    # Basic Auth checking
    auth_header = request.headers.get('Authorization') or request.META.get('HTTP_AUTHORIZATION') or ''
    company = None

    if auth_header.startswith('Basic '):
        try:
            encoded_key = auth_header.split(' ', 1)[1]
            decoded = base64.b64decode(encoded_key).decode('utf-8')
            # Format is "Paycom:secret_key"
            if ':' in decoded:
                _, secret = decoded.split(':', 1)
                secret = secret.strip()
                if secret:
                    company = Company.objects.filter(payme_secret_key=secret).first()
        except Exception:
            pass

    if not company:
        company = Company.objects.filter(payme_merchant_id__gt='').first() or Company.objects.first()

    if not company:
        return JsonResponse({
            'error': {'code': -32504, 'message': 'Company not configured for Payme'},
            'id': req_id,
        })

    # Method 1: CheckPerformTransaction
    if method == 'CheckPerformTransaction':
        account = params.get('account') or {}
        student_id = account.get('student_id')
        try:
            student = Student.objects.get(pk=int(student_id), company=company)
        except (Student.DoesNotExist, TypeError, ValueError):
            return JsonResponse({
                'error': {'code': -31050, 'message': {'ru': 'Ученик не найден', 'uz': 'Talaba topilmadi'}},
                'id': req_id,
            })

        amount = int(params.get('amount') or 0) // 100
        if amount <= 0:
            return JsonResponse({
                'error': {'code': -31001, 'message': {'ru': 'Неверная сумма', 'uz': "Noto'g'ri summa"}},
                'id': req_id,
            })

        return JsonResponse({
            'result': {
                'allow': True,
                'detail': {
                    'receipt_type': 0,
                    'items': [{
                        'title': f'Обучение: {student.full_name}',
                        'price': params.get('amount'),
                        'count': 1,
                        'code': '00000000000000000',
                        'units': 241092,
                        'vat_percent': 0,
                        'package_code': '000000',
                    }],
                },
            },
            'id': req_id,
        })

    # Method 2: CreateTransaction
    elif method == 'CreateTransaction':
        trans_id = str(params.get('id'))
        account = params.get('account') or {}
        student_id = account.get('student_id')
        amount = int(params.get('amount') or 0) // 100

        try:
            student = Student.objects.get(pk=int(student_id), company=company)
        except (Student.DoesNotExist, TypeError, ValueError):
            return JsonResponse({
                'error': {'code': -31050, 'message': 'Student not found'},
                'id': req_id,
            })

        tx = PaymentTransaction.objects.filter(
            company=company,
            provider=PaymentTransaction.Provider.PAYME,
            trans_id=trans_id,
        ).first()

        now_ms = int(time.time() * 1000)

        if tx:
            if tx.status == PaymentTransaction.Status.CANCELLED:
                return JsonResponse({
                    'error': {'code': -31008, 'message': 'Transaction cancelled'},
                    'id': req_id,
                })
            return JsonResponse({
                'result': {
                    'create_time': int(tx.created_at.timestamp() * 1000),
                    'transaction': str(tx.id),
                    'state': 2 if tx.status == PaymentTransaction.Status.COMPLETED else 1,
                },
                'id': req_id,
            })

        tx = PaymentTransaction.objects.create(
            company=company,
            student=student,
            provider=PaymentTransaction.Provider.PAYME,
            trans_id=trans_id,
            amount=amount,
            status=PaymentTransaction.Status.PENDING,
            data={'payme_time': params.get('time')},
        )

        return JsonResponse({
            'result': {
                'create_time': now_ms,
                'transaction': str(tx.id),
                'state': 1,
            },
            'id': req_id,
        })

    # Method 3: PerformTransaction
    elif method == 'PerformTransaction':
        trans_id = str(params.get('id'))
        tx = PaymentTransaction.objects.filter(
            company=company,
            provider=PaymentTransaction.Provider.PAYME,
            trans_id=trans_id,
        ).first()

        if not tx:
            return JsonResponse({
                'error': {'code': -31003, 'message': 'Transaction not found'},
                'id': req_id,
            })

        now_ms = int(time.time() * 1000)

        if tx.status == PaymentTransaction.Status.COMPLETED and tx.payment:
            return JsonResponse({
                'result': {
                    'transaction': str(tx.id),
                    'perform_time': int(tx.payment.created_at.timestamp() * 1000),
                    'state': 2,
                },
                'id': req_id,
            })

        if tx.status == PaymentTransaction.Status.CANCELLED:
            return JsonResponse({
                'error': {'code': -31008, 'message': 'Transaction cancelled'},
                'id': req_id,
            })

        student = tx.student
        course_price = student.group.course.price if (student.group and student.group.course) else 0
        months_covered = 1
        if course_price and course_price > 0 and tx.amount >= course_price:
            months_covered = max(1, round(tx.amount / course_price))

        payment = Payment.objects.create(
            company=company,
            student=student,
            student_name=student.full_name,
            amount=tx.amount,
            months_covered=months_covered,
            method=Payment.Method.CARD,
            comment=f'Payme trans #{trans_id}',
        )

        tx.status = PaymentTransaction.Status.COMPLETED
        tx.payment = payment
        tx.save()

        # Update paid_this_month
        now = timezone.localtime(payment.created_at)
        today = timezone.localdate()
        if now.year == today.year and now.month == today.month:
            student.paid_this_month = True
            student.save(update_fields=['paid_this_month'])

        # Instant Telegram receipt
        send_payment_receipt_telegram(payment)

        return JsonResponse({
            'result': {
                'transaction': str(tx.id),
                'perform_time': now_ms,
                'state': 2,
            },
            'id': req_id,
        })

    # Method 4: CancelTransaction
    elif method == 'CancelTransaction':
        trans_id = str(params.get('id'))
        tx = PaymentTransaction.objects.filter(
            company=company,
            provider=PaymentTransaction.Provider.PAYME,
            trans_id=trans_id,
        ).first()

        if not tx:
            return JsonResponse({
                'error': {'code': -31003, 'message': 'Transaction not found'},
                'id': req_id,
            })

        now_ms = int(time.time() * 1000)
        was_completed = (tx.status == PaymentTransaction.Status.COMPLETED)

        tx.status = PaymentTransaction.Status.CANCELLED
        tx.save()

        if tx.payment:
            tx.payment.delete()
            tx.payment = None
            tx.save()

        return JsonResponse({
            'result': {
                'transaction': str(tx.id),
                'cancel_time': now_ms,
                'state': -2 if was_completed else -1,
            },
            'id': req_id,
        })

    # Method 5: CheckTransaction
    elif method == 'CheckTransaction':
        trans_id = str(params.get('id'))
        tx = PaymentTransaction.objects.filter(
            company=company,
            provider=PaymentTransaction.Provider.PAYME,
            trans_id=trans_id,
        ).first()

        if not tx:
            return JsonResponse({
                'error': {'code': -31003, 'message': 'Transaction not found'},
                'id': req_id,
            })

        create_ms = int(tx.created_at.timestamp() * 1000)
        perform_ms = int(tx.payment.created_at.timestamp() * 1000) if tx.payment else 0
        cancel_ms = int(tx.updated_at.timestamp() * 1000) if tx.status == PaymentTransaction.Status.CANCELLED else 0

        state = 1
        if tx.status == PaymentTransaction.Status.COMPLETED:
            state = 2
        elif tx.status == PaymentTransaction.Status.CANCELLED:
            state = -2 if perform_ms > 0 else -1

        return JsonResponse({
            'result': {
                'create_time': create_ms,
                'perform_time': perform_ms,
                'cancel_time': cancel_ms,
                'transaction': str(tx.id),
                'state': state,
                'reason': None,
            },
            'id': req_id,
        })

    return JsonResponse({'error': {'code': -32601, 'message': 'Method not found'}, 'id': req_id})
