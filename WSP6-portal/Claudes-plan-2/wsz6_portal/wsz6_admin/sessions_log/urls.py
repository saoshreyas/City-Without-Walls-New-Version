from django.urls import path
from . import views

app_name = 'sessions_log'

urlpatterns = [
    path('', views.session_list, name='list'),
    path('delete/<uuid:session_key>/', views.delete_session, name='delete_session'),
]
