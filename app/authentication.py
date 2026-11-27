"""Browser sessions for the demo; existing Basic-auth API clients still work."""
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix='/api/auth', tags=['Demo authentication'])
basic = HTTPBasic(auto_error=False)
COOKIE = 'prism_session'
SESSION_SECONDS = 8 * 60 * 60


def password():
    value = os.getenv('PRISM_DEMO_PASSWORD')
    if not value:
        raise HTTPException(503, 'Set PRISM_DEMO_PASSWORD to enable demo')
    return value


def valid_credentials(username, supplied):
    expected = password()
    return secrets.compare_digest(username.encode('utf-8'), b'prism') and secrets.compare_digest(supplied.encode('utf-8'), expected.encode('utf-8'))


def signature(payload):
    # Changing the configured password invalidates all previous browser sessions.
    key = (os.getenv('PRISM_SESSION_SECRET', '') + '\0' + password()).encode('utf-8')
    return hmac.new(key, payload.encode('ascii'), hashlib.sha256).hexdigest()


def valid_session(token):
    if not token or len(token) > 200:
        return False
    try:
        expiry, nonce, mac = token.split('.')
        payload = expiry + '.' + nonce
        return len(nonce) == 32 and time.time() < int(expiry) <= time.time() + SESSION_SECONDS and hmac.compare_digest(mac, signature(payload))
    except (ValueError, UnicodeError):
        return False


def check_origin(request):
    origin = request.headers.get('origin')
    if origin:
        parsed = urlsplit(origin)
        # Managed HTTPS proxies may forward HTTP to the app. A same-host HTTPS
        # origin is valid; an HTTPS request must never accept an HTTP origin.
        if parsed.scheme not in ('http', 'https') or parsed.netloc != request.url.netloc or (request.url.scheme == 'https' and parsed.scheme != 'https'):
            raise HTTPException(403, 'Cross-origin session request rejected')


def require_user(request: Request, creds: HTTPBasicCredentials | None = Depends(basic)):
    password()
    if creds and valid_credentials(creds.username, creds.password):
        return
    if valid_session(request.cookies.get(COOKIE)):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            check_origin(request)
        return
    raise HTTPException(401, 'Login required')


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


@router.get('/session')
def session(request: Request, response: Response):
    password()
    response.headers['Cache-Control'] = 'no-store'
    return {'authenticated': valid_session(request.cookies.get(COOKIE)), 'username': 'prism'}


@router.post('/login')
def login(data: Login, request: Request, response: Response):
    check_origin(request)
    if not valid_credentials(data.username, data.password):
        # No browser-native challenge: errors stay in the PRISM form.
        raise HTTPException(401, 'Username or password is incorrect. Use the local login file for this server.')
    payload = str(int(time.time()) + SESSION_SECONDS) + '.' + secrets.token_hex(16)
    response.set_cookie(COOKIE, payload + '.' + signature(payload), max_age=SESSION_SECONDS,
                        httponly=True, secure=request.url.scheme == 'https' or request.url.hostname not in ('localhost', '127.0.0.1', '::1'), samesite='strict', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'authenticated': True, 'username': 'prism'}


@router.post('/logout')
def logout(request: Request, response: Response):
    check_origin(request)
    response.delete_cookie(COOKIE, path='/', secure=request.url.scheme == 'https' or request.url.hostname not in ('localhost', '127.0.0.1', '::1'), httponly=True, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'
    return {'authenticated': False}
