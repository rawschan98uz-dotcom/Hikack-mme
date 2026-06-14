from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, re_path

from config.spa import spa_asset, spa_index


def health_check(_request):
    return HttpResponse('ok', content_type='text/plain')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check),
    path('v1/', include('api.v1.urls')),
    re_path(r'^assets/(?P<path>.+)$', spa_asset),
    re_path(r'^(?!v1/|admin/|static/|media/|health/).*$', spa_index),
]