"""Canonical messaging, retry and connected workflow regressions."""
from datetime import timedelta, time
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from apps.appointments.models import Appointment, DoctorAvailability
from .models import Consultation, ConsultationMessage

User = get_user_model()

class SecureMessagingTests(APITestCase):
    def setUp(self):
        self.patient = User.objects.create_user(email='chat-patient@test.com', password='test', role='patient')
        self.doctor = User.objects.create_user(email='chat-doctor@test.com', password='test', role='doctor')
        self.other = User.objects.create_user(email='chat-other@test.com', password='test', role='patient')
        self.consult = Consultation.objects.create(patient=self.patient, doctor=self.doctor)
        self.url = reverse('consultation-messages', args=[self.consult.pk])
        self.client.force_authenticate(self.patient)

    def test_strict_message_validation_without_writes(self):
        for payload in [None, '', [], 42, True, {}, {'message': None}, {'message': 42}, {'message': True},
                        {'message': []}, {'message': '  '}, {'message': 'x'*2001},
                        {'message': 'ok', 'sender': str(self.other.pk)}, {'message': 'ok', 'client_msg_id': []},
                        {'message': 'ok', 'client_msg_id': 'x'*65}]:
            with self.subTest(payload=payload):
                import json
                response = self.client.generic('POST', self.url, json.dumps(payload), content_type='application/json')
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(ConsultationMessage.objects.count(), 0)

    def test_retry_key_is_scoped_to_sender_and_content(self):
        payload = {'message': 'Hello', 'client_msg_id': 'same-key'}
        first = self.client.post(self.url, payload, format='json')
        again = self.client.post(self.url, payload, format='json')
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.data['id'], again.data['id'])
        self.assertEqual(str(first.data['sender']), str(self.patient.pk))
        conflict = self.client.post(self.url, {**payload, 'message': 'Changed'}, format='json')
        self.assertEqual(conflict.status_code, 409)
        self.client.force_authenticate(self.doctor)
        own = self.client.post(self.url, payload, format='json')
        self.assertEqual(own.status_code, 201)
        self.assertNotEqual(first.data['id'], own.data['id'])
        self.assertEqual(ConsultationMessage.objects.count(), 2)

    def test_history_is_paginated_and_scoped(self):
        for index in range(53):
            ConsultationMessage.objects.create(consultation=self.consult, sender=self.patient, message=str(index))
        first = self.client.get(self.url)
        second = self.client.get(self.url, {'page': 2})
        self.assertEqual(first.data['count'], 53)
        self.assertEqual(len(first.data['results']), 50)
        self.assertEqual(len(second.data['results']), 3)
        ids1 = {m['id'] for m in first.data['results']}
        self.assertFalse(ids1 & {m['id'] for m in second.data['results']})
        self.assertEqual(first.data['results'][0]['message'], '52')
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {'message': 'attack'}).status_code, 404)

    def test_closed_consultations_allow_history_and_original_retry_only(self):
        payload = {'message': 'Before closing', 'client_msg_id': 'saved'}
        first = self.client.post(self.url, payload)
        for state in ['completed', 'cancelled']:
            self.consult.status = state; self.consult.save()
            self.assertEqual(self.client.get(self.url).status_code, 200)
            self.assertEqual(self.client.post(self.url, payload).data['id'], first.data['id'])
            self.assertEqual(self.client.post(self.url, {'message': 'New'}).status_code, 409)
        self.assertEqual(ConsultationMessage.objects.count(), 1)

    def test_current_identity_checks_database_and_access_token_type(self):
        self.client.force_authenticate(None)
        url = reverse('consultation-identity')
        access = str(AccessToken.for_user(self.patient))
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+access)
        self.assertEqual(self.client.get(url).data['role'], 'patient')
        self.patient.role = 'nurse'; self.patient.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.patient.role = 'patient'; self.patient.is_active = False; self.patient.save()
        self.assertEqual(self.client.get(url).status_code, 401)
        self.patient.is_active = True; self.patient.save()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+str(RefreshToken.for_user(self.patient)))
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_connected_booking_consultation_message_and_completion(self):
        start = (timezone.now()+timedelta(days=7)).replace(hour=10, minute=0, second=0, microsecond=0)
        DoctorAvailability.objects.create(doctor=self.doctor, weekday=start.weekday(), start_time=time(9), end_time=time(17))
        booking = self.client.post(reverse('appointment-list'), {
            'doctor': str(self.doctor.pk), 'scheduled_start': start.isoformat(),
            'scheduled_end': (start+timedelta(minutes=30)).isoformat(), 'reason': 'Chat workflow', 'symptoms': [],
        }, format='json')
        self.assertEqual(booking.status_code, 201, booking.data)
        self.client.force_authenticate(self.doctor)
        self.assertEqual(self.client.post(reverse('appointment-confirm', args=[booking.data['id']]), {}, format='json').status_code, 200)
        created = self.client.post(reverse('consultation-list'), {'appointment': booking.data['id']}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        pk = created.data['id']; url = reverse('consultation-messages', args=[pk])
        self.assertEqual(self.client.post(reverse('consultation-start', args=[pk]), {}, format='json').status_code, 200)
        self.client.force_authenticate(self.patient)
        sent = self.client.post(url, {'message': 'Symptoms', 'client_msg_id': 'workflow'}, format='json')
        self.assertEqual(sent.status_code, 201)
        self.client.force_authenticate(self.doctor)
        self.assertEqual(self.client.get(url).data['results'][0]['id'], sent.data['id'])
        ended = self.client.post(reverse('consultation-end', args=[pk]), {
            'diagnosis': 'Recorded', 'follow_up_required': True, 'follow_up_notes': 'Next week',
        }, format='json')
        self.assertEqual(ended.status_code, 200)
        self.assertEqual(ended.data['status'], 'completed')
        self.client.force_authenticate(self.patient)
        self.assertEqual(self.client.get(reverse('consultation-detail', args=[pk])).data['diagnosis'], 'Recorded')
        self.assertEqual(self.client.post(url, {'message': 'After closing'}).status_code, 409)
