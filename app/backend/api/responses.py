from rest_framework.response import Response


def ok(data, status_code: int = 200) -> Response:
    return Response({'status': status_code, 'success': True, 'data': data}, status=status_code)


def fail(message: str, status_code: int = 400) -> Response:
    return Response({'status': status_code, 'success': False, 'message': message}, status=status_code)
