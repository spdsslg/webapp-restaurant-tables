"""SMTP delivery for the local development inbox"""
from email.message import EmailMessage
import smtplib

import click
from flask import current_app

def send_email(recipient, subject, body):
    message = EmailMessage()
    message["From"] = current_app.config["MAIL_SENDER"]
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(current_app.config["MAIL_HOST"],
                      current_app.config["MAIL_PORT"], timeout=5) as smtp:
        smtp.send_message(message)

def register_mail_commands(app):
    @app.cli.command("send-test-email")
    def send_test_email():
        """Send a harmless test message to the configured development inbox"""
        try:
            send_email("demo@example.test", "Restaurant email test",
                       "Email capture is working. Password reset will be added later")
        except (OSError, smtplib.SMTPException) as error:
            raise click.ClickException("SMTP delivery failed,check the email service configuration.") from error
        click.echo("Test message sent to demo@example.test")
