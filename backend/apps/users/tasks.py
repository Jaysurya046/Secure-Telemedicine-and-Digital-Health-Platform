"""
Celery tasks for User app.
"""
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from django.utils import timezone
from datetime import timedelta

User = get_user_model()


@shared_task
def send_welcome_email(user_id):
    """Send welcome email to new user."""
    try:
        user = User.objects.get(id=user_id)
        subject = 'Welcome to Telemedicine Platform'
        message = f'''
        Hello {user.profile.first_name},
        
        Welcome to our Telemedicine Platform!
        
        Your account has been successfully created.
        
        Best regards,
        Telemedicine Team
        '''
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return f'Welcome email sent to {user.email}'
    except User.DoesNotExist:
        return f'User {user_id} not found'
    except Exception as e:
        return f'Error sending email: {str(e)}'


@shared_task
def send_verification_email(user_id, verification_token):
    """Send email verification link."""
    try:
        user = User.objects.get(id=user_id)
        subject = 'Verify your email address'
        message = f'''
        Hello {user.profile.first_name},
        
        Please verify your email address by clicking the link below:
        
        {settings.FRONTEND_URL}/verify-email/{verification_token}
        
        This link will expire in 24 hours.
        
        Best regards,
        Telemedicine Team
        '''
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return f'Verification email sent to {user.email}'
    except User.DoesNotExist:
        return f'User {user_id} not found'
    except Exception as e:
        return f'Error sending email: {str(e)}'


@shared_task
def send_password_reset_email(user_id, reset_token):
    """Send password reset email."""
    try:
        user = User.objects.get(id=user_id)
        subject = 'Reset your password'
        message = f'''
        Hello {user.profile.first_name},
        
        You requested to reset your password. Click the link below to reset it:
        
        {settings.FRONTEND_URL}/reset-password/{reset_token}
        
        This link will expire in 1 hour.
        
        If you didn't request this, please ignore this email.
        
        Best regards,
        Telemedicine Team
        '''
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return f'Password reset email sent to {user.email}'
    except User.DoesNotExist:
        return f'User {user_id} not found'
    except Exception as e:
        return f'Error sending email: {str(e)}'


@shared_task
def cleanup_expired_tokens():
    """Clean up expired JWT tokens from blacklist."""
    try:
        # Delete tokens older than 7 days
        expiry_date = timezone.now() - timedelta(days=7)
        deleted_count = OutstandingToken.objects.filter(
            expires_at__lt=expiry_date
        ).delete()[0]
        
        return f'Deleted {deleted_count} expired tokens'
    except Exception as e:
        return f'Error cleaning up tokens: {str(e)}'


@shared_task
def send_bulk_notification(user_ids, subject, message):
    """Send bulk email notification to users."""
    try:
        users = User.objects.filter(id__in=user_ids, is_active=True)
        emails = [user.email for user in users]
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            emails,
            fail_silently=False,
        )
        return f'Bulk notification sent to {len(emails)} users'
    except Exception as e:
        return f'Error sending bulk notification: {str(e)}'
