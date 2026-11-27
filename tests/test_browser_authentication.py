"""A normal browser form authenticates without native Basic-auth dialogs."""
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.server import app
from app.authentication import COOKIE


class BrowserAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'PRISM_DEMO_PASSWORD': 'synthetic-test-password'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app, base_url='http://localhost')
        self.addCleanup(self.client.close)

    def login(self, **kwargs):
        return self.client.post('/api/auth/login', json={'username': 'prism', 'password': 'synthetic-test-password'}, **kwargs)

    def test_public_shell_protected_data_and_browser_login(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertFalse(self.client.get('/api/auth/session').json()['authenticated'])
        self.assertEqual(self.client.get('/api/exceptions').status_code, 401)
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('SameSite=strict', response.headers['set-cookie'])
        self.assertTrue(self.client.get('/api/auth/session').json()['authenticated'])
        self.assertEqual(self.client.get('/api/exceptions').status_code, 200)
        self.assertEqual(self.client.get('/api/local/status').status_code, 200)

    def test_wrong_password_stays_in_form_without_native_challenge(self):
        response = self.client.post('/api/auth/login', json={'username': 'prism', 'password': 'wrong'})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('www-authenticate', response.headers)
        self.assertFalse(self.client.get('/api/auth/session').json()['authenticated'])

    def test_tampered_and_expired_sessions_rejected(self):
        self.login()
        cookie = self.client.cookies[COOKIE]
        self.client.cookies.clear()
        for bad in (cookie+'x', '1.'+cookie.split('.', 1)[1], 'invalid'):
            self.assertEqual(self.client.get('/api/exceptions', headers={'cookie': COOKIE+'='+bad}).status_code, 401)

    def test_logout_and_password_rotation(self):
        self.login()
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 200)
        self.assertEqual(self.client.get('/api/exceptions').status_code, 401)
        self.login()
        with patch.dict(os.environ, {'PRISM_DEMO_PASSWORD': 'rotated-test-password'}):
            self.assertEqual(self.client.get('/api/exceptions').status_code, 401)

    def test_cross_origin_login_and_mutation_are_rejected(self):
        self.assertEqual(self.login(headers={'origin': 'https://other.example'}).status_code, 403)
        self.login()
        self.assertEqual(self.client.post('/api/auth/logout', headers={'origin': 'https://other.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/demo/erp/run', json={}, headers={'origin': 'https://other.example'}).status_code, 403)

    def test_basic_api_clients_are_preserved(self):
        self.assertEqual(self.client.get('/api/exceptions', auth=('prism', 'synthetic-test-password')).status_code, 200)

    def test_https_proxy_cookie_is_secure(self):
        with TestClient(app, base_url='http://prism.example') as client:
            r = client.post('/api/auth/login', json={'username': 'prism', 'password': 'synthetic-test-password'}, headers={'origin': 'https://prism.example'})
            self.assertEqual(r.status_code, 200)
            self.assertIn('Secure', r.headers['set-cookie'])
