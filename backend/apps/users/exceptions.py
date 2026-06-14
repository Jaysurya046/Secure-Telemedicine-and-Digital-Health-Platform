"""
Custom exception handler for API responses.
"""
from rest_framework.views import exception_handler  # type: ignore[import]
from rest_framework.response import Response  # type: ignore[import]
from rest_framework import status  # type: ignore[import]
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that provides consistent error responses.
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    # Log the exception
    logger.error(f"Exception: {exc}", exc_info=True)
    
    if response is not None:
        # Customize the response data
        custom_response_data = {
            'error': True,
            'message': str(exc),
            'details': response.data if isinstance(response.data, dict) else {'detail': response.data}
        }
        response.data = custom_response_data
        
    else:
        # Handle Django validation errors
        if isinstance(exc, DjangoValidationError):
            custom_response_data = {
                'error': True,
                'message': 'Validation error',
                'details': exc.message_dict if hasattr(exc, 'message_dict') else {'detail': exc.messages}
            }
            response = Response(custom_response_data, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle 404 errors
        elif isinstance(exc, Http404):
            custom_response_data = {
                'error': True,
                'message': 'Not found',
                'details': {'detail': str(exc)}
            }
            response = Response(custom_response_data, status=status.HTTP_404_NOT_FOUND)
        
        # Handle other exceptions
        else:
            custom_response_data = {
                'error': True,
                'message': 'Internal server error',
                'details': {'detail': str(exc)}
            }
            response = Response(custom_response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return response
