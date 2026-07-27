"""DocuSign webhook signature verification."""
import hashlib
import hmac
import os
import unittest
from unittest.mock import patch


class DocuSignWebhookSecurityTests(unittest.TestCase):
    def test_unsigned_rejected_when_not_allowed(self):
        from docusign_service import verify_webhook_signature

        with patch.dict(os.environ, {'DOCUSIGN_ALLOW_UNSIGNED_WEBHOOKS': '', 'DOCUSIGN_CONNECT_HMAC_SECRET': ''}, clear=False):
            with patch('docusign_service.is_configured', return_value=False):
                self.assertFalse(verify_webhook_signature(b'{}', {}))

    def test_hmac_signature_accepted(self):
        from docusign_service import verify_webhook_signature

        secret = 'test-secret-key'
        body = b'{"envelopeId":"abc"}'
        timestamp = '1700000000'
        payload = f'{timestamp}.'.encode('utf-8') + body
        signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        headers = {'X-DocuSign-Signature-1': f't={timestamp},v1={signature}'}
        with patch.dict(os.environ, {'DOCUSIGN_CONNECT_HMAC_SECRET': secret}, clear=False):
            self.assertTrue(verify_webhook_signature(body, headers))


if __name__ == '__main__':
    unittest.main()
