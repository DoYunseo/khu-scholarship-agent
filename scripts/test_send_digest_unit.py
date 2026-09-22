import os
import unittest
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from send_digest import (
    UNSUBSCRIBE_SUBJECT_PREFIX,
    build_html_body,
    build_unsubscribe_url,
    create_unsubscribe_token,
    find_unsubscribed_recipients,
    parse_recipients,
    recipient_from_unsubscribe_token,
    send_email,
)


class UnsubscribeTests(unittest.TestCase):
    def test_recipient_parsing_deduplicates_and_normalizes(self) -> None:
        self.assertEqual(
            parse_recipients(" First@Example.com,second@example.com", "first@example.com"),
            ["first@example.com", "second@example.com"],
        )

    def test_signed_token_round_trip_and_tampering(self) -> None:
        token = create_unsubscribe_token("User@Example.com", "test-secret")
        self.assertEqual(
            recipient_from_unsubscribe_token(token, "test-secret"), "user@example.com"
        )
        self.assertIsNone(recipient_from_unsubscribe_token(token + "x", "test-secret"))

    def test_unsubscribe_button_is_at_end_of_html(self) -> None:
        url = build_unsubscribe_url("sender@example.com", "user@example.com", "secret")
        html = build_html_body("digest body", url)
        self.assertIn("수신 거부", html)
        self.assertIn("mailto:sender@example.com", html)
        self.assertGreater(html.index("수신 거부"), html.index("digest body"))

    @patch("send_digest.imaplib.IMAP4_SSL")
    def test_finds_recipient_from_signed_unsubscribe_message(
        self, imap_class: MagicMock
    ) -> None:
        token = create_unsubscribe_token("user@example.com", "test-secret")
        message = EmailMessage()
        message["Subject"] = f"{UNSUBSCRIBE_SUBJECT_PREFIX} {token}"
        mailbox = imap_class.return_value.__enter__.return_value
        mailbox.select.return_value = ("OK", [b"1"])
        mailbox.search.return_value = ("OK", [b"42"])
        mailbox.fetch.return_value = ("OK", [(b"42", message.as_bytes())])

        self.assertEqual(
            find_unsubscribed_recipients(
                "imap.example.com", 993, "sender", "password", "test-secret"
            ),
            {"user@example.com"},
        )

    @patch("send_digest.find_unsubscribed_recipients")
    @patch("send_digest.smtplib.SMTP")
    def test_sends_individually_and_skips_unsubscribed(
        self, smtp_class: MagicMock, find_unsubscribed: MagicMock
    ) -> None:
        find_unsubscribed.return_value = {"second@example.com"}
        smtp = smtp_class.return_value.__enter__.return_value
        env = {
            "EMAIL_HOST": "smtp.example.com",
            "EMAIL_PORT": "587",
            "EMAIL_USERNAME": "sender@example.com",
            "EMAIL_PASSWORD": "password",
            "EMAIL_FROM": "sender@example.com",
            "EMAIL_TO": "first@example.com",
            "EMAIL_TO_ADDITIONAL": "second@example.com",
            "EMAIL_UNSUBSCRIBE_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=True):
            send_email("digest body", "subject")

        smtp.send_message.assert_called_once()
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], "first@example.com")
        self.assertIn(UNSUBSCRIBE_SUBJECT_PREFIX, message["List-Unsubscribe"])


if __name__ == "__main__":
    unittest.main()
