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
    return FileResponse(open(file_path, 'rb'))


@require_GET
def spa_asset(request, path: str):
    dist = _frontend_dist()
    file_path = _safe_path(dist, f'assets/{path}')
    if not file_path.is_file():
        raise Http404('Asset not found')
    return FileResponse(open(file_path, 'rb'))


@require_GET
def spa_index(request):
    index = _frontend_dist() / 'index.html'
    if not index.is_file():
        return _spa_missing()
    return FileResponse(open(index, 'rb'), content_type='text/html; charset=utf-8')


def _spa_missing():
    return HttpResponse(
        '<h1>Frontend not built</h1>'
        '<p>Run <code>npm run build</code> in <code>app/frontend</code>, then restart the server.</p>',
        status=503,
        content_type='text/html; charset=utf-8',
    )
