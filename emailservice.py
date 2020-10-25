import configparser
import smtplib

from email.mime.text import MIMEText


def send_email_as_plateup(to_recipients, subject, body):
    '''
    Sends an email using smtp, specifically with plateup's gmail account.
    '''
    email_cfg = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    email_cfg.read('email_config.ini')
    sender_email = email_cfg["SENDER"]['email']
    sender_password = email_cfg["SENDER"]['pwd']

    my_email = MIMEText(body, "html")
    my_email["From"] = sender_email
    my_email["To"] = ", ".join(to_recipients)
    my_email["Subject"] = subject

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.ehlo()
        server.login(sender_email, sender_password)

        server.sendmail(sender_email, to_recipients, my_email.as_string())
        server.close()

        return True
    except Exception:
        return False
