from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from api.openapi import (
    ErrorResponseSerializer,
    TokenObtainPairRequestSerializer,
    TokenObtainPairResponseSerializer,
    TokenRefreshRequestSerializer,
    TokenRefreshResponseSerializer,
)


class DocumentedTokenObtainPairView(TokenObtainPairView):
    @extend_schema(
        tags=["Autenticación"],
        summary="Obtener token JWT",
        description=(
            "Autentica un usuario local de la API y devuelve dos tokens: `access` "
            "para consumir endpoints protegidos y `refresh` para renovar la sesión. "
            "Después de obtener el `access`, envialo en cada request protegida con "
            "el header `Authorization: Bearer <access_token>`. El `access` está "
            "configurado para durar 1 hora."
        ),
        auth=[],
        request=TokenObtainPairRequestSerializer,
        responses={
            status.HTTP_200_OK: TokenObtainPairResponseSerializer,
            status.HTTP_400_BAD_REQUEST: ErrorResponseSerializer,
            status.HTTP_401_UNAUTHORIZED: ErrorResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Credenciales de usuario local",
                value={"username": "admin", "password": "tu_password"},
                request_only=True,
            ),
            OpenApiExample(
                "Tokens emitidos",
                value={"refresh": "<refresh_token>", "access": "<access_token>"},
                response_only=True,
                status_codes=[str(status.HTTP_200_OK)],
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class DocumentedTokenRefreshView(TokenRefreshView):
    @extend_schema(
        tags=["Autenticación"],
        summary="Renovar token JWT",
        description=(
            "Genera un nuevo token `access` a partir de un token `refresh` válido. "
            "Usalo cuando el `access` haya expirado, sin pedirle al usuario sus "
            "credenciales otra vez. Si el `refresh` es inválido o venció, hay que "
            "volver a iniciar sesión en `/api/auth/token/`."
        ),
        auth=[],
        request=TokenRefreshRequestSerializer,
        responses={
            status.HTTP_200_OK: TokenRefreshResponseSerializer,
            status.HTTP_400_BAD_REQUEST: ErrorResponseSerializer,
            status.HTTP_401_UNAUTHORIZED: ErrorResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "Refresh token",
                value={"refresh": "<refresh_token>"},
                request_only=True,
            ),
            OpenApiExample(
                "Nuevo access token",
                value={"access": "<nuevo_access_token>"},
                response_only=True,
                status_codes=[str(status.HTTP_200_OK)],
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
