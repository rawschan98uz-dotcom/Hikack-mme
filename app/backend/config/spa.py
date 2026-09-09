import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_GET


def _frontend_dist() -> Path:
    return settings.FRONTEND_DIST


def _safe_path(base: Path, rel: str) -> Path:
    target = (base / rel).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise Http404('Invalid path')
    return target


@require_GET
def spa_icon(request, path: str):
    dist = _frontend_dist()
    file_path = _safe_path(dist, f'icons/{path}')
    if not file_path.is_file():
        raise Http404('Icon not found')
    response = FileResponse(open(file_path, 'rb'))
    response['Cache-Control'] = 'public, max-age=86400'
    return response


@require_GET
def spa_asset(request, path: str):
    dist = _frontend_dist()
    file_path = _safe_path(dist, f'assets/{path}')
    if not file_path.is_file():
        raise Http404('Asset not found')
    response = FileResponse(open(file_path, 'rb'))
    response['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response


@require_GET
def spa_index(request):
    index = _frontend_dist() / 'index.html'
    if not index.is_file():
        return _spa_missing()
    response = FileResponse(open(index, 'rb'), content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'no-cache'
    return response


def _spa_missing():
    return HttpResponse(
        '<h1>Frontend not built</h1>'
        '<p>Run <code>npm run build</code> in <code>app/frontend</code>, then restart the server.</p>',
        status=503,
        content_type='text/html; charset=utf-8',
    )


@require_GET
def spa_media(request, path: str):
    media_root = Path(settings.MEDIA_ROOT)
    file_path = _safe_path(media_root, path)
    if not file_path.is_file():
        raise Http404('Media not found')
    content_type, _encoding = mimetypes.guess_type(str(file_path))
    response = FileResponse(open(file_path, 'rb'))
    if content_type:
        response['Content-Type'] = content_type
    return response
