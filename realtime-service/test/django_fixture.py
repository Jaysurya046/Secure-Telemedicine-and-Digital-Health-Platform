"""Disposable real Django HTTP server used only by Socket.IO integration tests."""
import json, os, sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.test_settings'
import django
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
settings.SECURE_SSL_REDIRECT = False
settings.LOGGING = {}
logging.disable(logging.CRITICAL)
from django.core.management import call_command
call_command('migrate', verbosity=0)
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from apps.consultations.models import Consultation, ConsultationMessage
User = get_user_model()
users = {role: User.objects.create_user(email=role+'@integration.test', password='test', role='patient' if role=='attacker' else role)
         for role in ['doctor', 'patient', 'attacker']}
consult = Consultation.objects.create(doctor=users['doctor'], patient=users['patient'], status='in_progress')
from django.core.wsgi import get_wsgi_application
from wsgiref.simple_server import make_server, WSGIRequestHandler
app = get_wsgi_application()
def application(environ, start_response):
    # Local test fixture controls, never mounted by the product server.
    if environ['PATH_INFO'] == '/__test__/state/':
        size = int(environ.get('CONTENT_LENGTH') or 0)
        data = json.loads(environ['wsgi.input'].read(size) or b'{}')
        if 'active' in data:
            User.objects.filter(pk=users['patient'].pk).update(is_active=data['active'])
        if 'role' in data:
            User.objects.filter(pk=users['patient'].pk).update(role=data['role'])
        if 'patient' in data:
            Consultation.objects.filter(pk=consult.pk).update(patient=users[data['patient']])
        if 'status' in data:
            Consultation.objects.filter(pk=consult.pk).update(status=data['status'])
        result = {'count': ConsultationMessage.objects.count()}
        start_response('200 OK', [('Content-Type', 'application/json')]); return [json.dumps(result).encode()]
    return app(environ, start_response)
class Quiet(WSGIRequestHandler):
    def log_message(self, *args): pass
server = make_server('127.0.0.1', 0, application, handler_class=Quiet)
tokens = {role: str(AccessToken.for_user(user)) for role, user in users.items()}
print(json.dumps({'port': server.server_port, 'tokens': tokens, 'roomId': str(consult.room_id), 'consultationId': str(consult.pk),
    'refresh': str(RefreshToken.for_user(users['patient'])), 'patientId': str(users['patient'].pk)}), flush=True)
server.serve_forever()
