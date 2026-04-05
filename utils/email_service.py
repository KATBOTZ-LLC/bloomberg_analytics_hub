"""
Email notification service for security alerts
Sends emails for failed login attempts and security events using SendGrid API
"""

import logging
import os
from datetime import datetime
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False


class EmailService:
    """Service for sending security notification emails via SendGrid"""

    def __init__(self):
        """Initialize email service with SendGrid configuration"""
        self.logger = logging.getLogger(__name__)

        # SendGrid configuration from environment variables
        self.sendgrid_api_key = os.getenv('SENDGRID_API_KEY', '')
        self.sender_email = os.getenv('SENDGRID_FROM_EMAIL', '')
        self.notification_email = os.getenv('NOTIFICATION_EMAIL', '')

        # Check if email is configured
        self.is_configured = bool(
            SENDGRID_AVAILABLE and
            self.sendgrid_api_key and
            self.sender_email and
            self.notification_email
        )

        if not SENDGRID_AVAILABLE:
            self.logger.warning("SendGrid library not installed. Run: pip install sendgrid")
        elif not self.is_configured:
            self.logger.warning("Email service not fully configured. Notifications will be logged only.")
        else:
            self.logger.info(f"Email service initialized. Notifications will be sent to: {self.notification_email}")

    def send_failed_login_alert(self, attempted_email, ip_address=None, timestamp=None):
        """
        Send email alert for failed login attempt

        Args:
            attempted_email (str): Email address that attempted to login
            ip_address (str): IP address of the attempt
            timestamp (datetime): Time of the attempt

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not timestamp:
            timestamp = datetime.now()

        subject = f"🚨 Security Alert: Failed Login Attempt"

        # Create email body
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 2px solid #ef4444; border-radius: 10px;">
                <h2 style="color: #ef4444;">🚨 Security Alert: Failed Login Attempt</h2>

                <p>A failed login attempt was detected on your Bloomberg Analytics Hub account.</p>

                <div style="background-color: #fee2e2; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #dc2626;">Attempt Details:</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 5px; font-weight: bold;">Email Attempted:</td>
                            <td style="padding: 5px;">{attempted_email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px; font-weight: bold;">Time:</td>
                            <td style="padding: 5px;">{timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td>
                        </tr>
                        {f'<tr><td style="padding: 5px; font-weight: bold;">IP Address:</td><td style="padding: 5px;">{ip_address}</td></tr>' if ip_address else ''}
                    </table>
                </div>

                <div style="background-color: #fef3c7; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #d97706;">⚠️ What This Means:</h3>
                    <p>Someone attempted to access your account using the email address <strong>{attempted_email}</strong> with an incorrect password.</p>
                </div>

                <div style="background-color: #dbeafe; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1e40af;">🛡️ Recommended Actions:</h3>
                    <ul>
                        <li>If this was you, please verify your password</li>
                        <li>If this wasn't you, your account credentials may be compromised</li>
                        <li>Consider changing your password immediately</li>
                        <li>Review your account activity</li>
                        <li>Enable two-factor authentication if available</li>
                    </ul>
                </div>

                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb;">
                    <p style="font-size: 12px; color: #6b7280;">
                        This is an automated security notification from Bloomberg Analytics Hub.<br>
                        If you have questions, please contact your system administrator.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return self._send_email(self.notification_email, subject, body)

    def send_new_user_attempt_alert(self, attempted_email, ip_address=None, timestamp=None):
        """
        Send email alert when someone tries to login with non-existent email

        Args:
            attempted_email (str): Email address that doesn't exist in system
            ip_address (str): IP address of the attempt
            timestamp (datetime): Time of the attempt

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not timestamp:
            timestamp = datetime.now()

        subject = f"🔔 Login Attempt with Unregistered Email: {attempted_email}"

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 2px solid #f59e0b; border-radius: 10px;">
                <h2 style="color: #f59e0b;">🔔 Unregistered User Login Attempt</h2>

                <p>Someone attempted to login to Bloomberg Analytics Hub using an email address that is not registered in the system.</p>

                <div style="background-color: #fef3c7; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #d97706;">Attempt Details:</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 5px; font-weight: bold;">Email Attempted:</td>
                            <td style="padding: 5px;">{attempted_email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px; font-weight: bold;">Time:</td>
                            <td style="padding: 5px;">{timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td>
                        </tr>
                        {f'<tr><td style="padding: 5px; font-weight: bold;">IP Address:</td><td style="padding: 5px;">{ip_address}</td></tr>' if ip_address else ''}
                        <tr>
                            <td style="padding: 5px; font-weight: bold;">Status:</td>
                            <td style="padding: 5px; color: #dc2626; font-weight: bold;">EMAIL NOT REGISTERED</td>
                        </tr>
                    </table>
                </div>

                <div style="background-color: #e0e7ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #4338ca;">💡 What This Means:</h3>
                    <p>This could indicate:</p>
                    <ul>
                        <li>A legitimate user trying to access with wrong email</li>
                        <li>Someone exploring the system</li>
                        <li>Potential unauthorized access attempt</li>
                        <li>A user who needs to be registered</li>
                    </ul>
                </div>

                <div style="background-color: #dbeafe; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1e40af;">📋 Recommended Actions:</h3>
                    <ul>
                        <li>Verify if this is a legitimate user who needs access</li>
                        <li>Contact the person at <strong>{attempted_email}</strong> if appropriate</li>
                        <li>Create an account using the admin tool if this is a valid user</li>
                        <li>Monitor for repeated attempts</li>
                        <li>Review security logs</li>
                    </ul>
                </div>

                <div style="background-color: #f3f4f6; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">🔧 To Create This User:</h3>
                    <p>Run the admin tool:</p>
                    <pre style="background-color: #1f2937; color: #10b981; padding: 10px; border-radius: 5px; overflow-x: auto;">python3 admin_user_manager.py</pre>
                    <p>Then select option 1 to create a new user with email: <strong>{attempted_email}</strong></p>
                </div>

                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb;">
                    <p style="font-size: 12px; color: #6b7280;">
                        This is an automated security notification from Bloomberg Analytics Hub.<br>
                        System Administrator: {self.notification_email}
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return self._send_email(self.notification_email, subject, body)

    def _send_email(self, to_email, subject, html_content):
        """
        Internal method to send email via SendGrid API

        Args:
            to_email (str): Recipient email address
            subject (str): Email subject
            html_content (str): HTML email body

        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.is_configured:
            self.logger.warning(f"Email not configured. Would send: {subject} to {to_email}")
            self.logger.info(f"Email content preview: {html_content[:200]}...")
            return False

        try:
            message = Mail(
                from_email=self.sender_email,
                to_emails=to_email,
                subject=subject,
                html_content=html_content
            )

            sg = SendGridAPIClient(self.sendgrid_api_key)
            response = sg.send(message)

            self.logger.info(f"Email sent successfully to {to_email}: {subject} (Status: {response.status_code})")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send email via SendGrid: {str(e)}")
            return False

    def send_access_request_alert(self, name, email, company, reason, timestamp=None):
        """
        Send email alert when someone requests access to the dashboard

        Args:
            name (str): Name of the requester
            email (str): Email address of the requester
            company (str): Company name
            reason (str): Reason for requesting access
            timestamp (datetime): Time of the request

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not timestamp:
            timestamp = datetime.now()

        subject = f"📋 New Access Request: {name} from {company}"

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 2px solid #3b82f6; border-radius: 10px;">
                <h2 style="color: #3b82f6;">📋 New Access Request</h2>

                <p>Someone has requested access to the CFO Pulse Dashboard.</p>

                <div style="background-color: #dbeafe; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1e40af;">Request Details:</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; font-weight: bold; width: 140px;">Name:</td>
                            <td style="padding: 8px;">{name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">Email:</td>
                            <td style="padding: 8px;"><a href="mailto:{email}">{email}</a></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">Company:</td>
                            <td style="padding: 8px;">{company}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">Request Time:</td>
                            <td style="padding: 8px;">{timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td>
                        </tr>
                    </table>
                </div>

                <div style="background-color: #f3f4f6; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #374151;">📝 Reason for Access:</h3>
                    <p style="background-color: #ffffff; padding: 12px; border-radius: 5px; border-left: 4px solid #3b82f6;">
                        {reason}
                    </p>
                </div>

                <div style="background-color: #ecfdf5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #065f46;">🔧 To Grant Access:</h3>
                    <p>Run the admin tool:</p>
                    <pre style="background-color: #1f2937; color: #10b981; padding: 10px; border-radius: 5px; overflow-x: auto;">python3 admin_user_manager.py</pre>
                    <p>Then select option 1 to create a new user with email: <strong>{email}</strong></p>
                </div>

                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb;">
                    <p style="font-size: 12px; color: #6b7280;">
                        This is an automated notification from CFO Pulse Dashboard.<br>
                        Please review and respond to this request.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return self._send_email(self.notification_email, subject, body)

    def test_email_configuration(self):
        """
        Test email configuration by sending a test message

        Returns:
            bool: True if test successful, False otherwise
        """
        if not self.is_configured:
            self.logger.error("Email service not configured")
            return False

        subject = "Test Email - Bloomberg Analytics Hub"
        body = """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 2px solid #10b981; border-radius: 10px;">
                <h2 style="color: #10b981;">✅ Email Configuration Test</h2>
                <p>This is a test email from Bloomberg Analytics Hub.</p>
                <p><strong>If you received this, your SendGrid email configuration is working correctly!</strong></p>
                <div style="background-color: #d1fae5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #065f46;">Configuration Details:</h3>
                    <ul>
                        <li>From Email: {self.sender_email}</li>
                        <li>Notification Email: {self.notification_email}</li>
                        <li>Service: SendGrid API</li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """

        return self._send_email(self.notification_email, subject, body)
