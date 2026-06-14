from django.contrib import admin
from django.urls import include, path, re_path

from config.spa import spa_asset, spa_index

urlpatterns = [
    path('admin/', admin.site.urls),
    path('v1/', include('api.v1.urls')),
    re_path(r'^assets/(?P<path>.+)$', spa_asset),
    re_path(r'^(?!v1/|admin/|static/|media/).*$', spa_index),
]
