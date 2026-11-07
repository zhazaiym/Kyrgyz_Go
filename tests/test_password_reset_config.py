from mysite.api import password_reset


class FakeSMTP:
    def __init__(self, *args, **kwargs):
        self.message = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self, **kwargs):
        pass

    def send_message(self, message):
        self.message = message
        sent_messages.append(message)


sent_messages = []


def test_reset_email_points_to_vulnerability_safe_frontend_url(monkeypatch):
    sent_messages.clear()
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    monkeypatch.setenv('SMTP_PORT', '587')
    monkeypatch.setenv('SMTP_FROM', 'noreply@example.test')
    monkeypatch.setenv('FRONTEND_RESET_URL', 'https://kerben-travel.vercel.app/ru/reset-password')
    monkeypatch.setattr(password_reset.smtplib, 'SMTP', FakeSMTP)

    password_reset.send_reset_email('client@example.test', 'abc/def+ghi')

    body = sent_messages[0].get_content()
    assert 'https://kerben-travel.vercel.app/ru/reset-password?token=abc%2Fdef%2Bghi' in body
