import httpx
from fastapi.concurrency import run_in_threadpool
from .config import settings
import logging

# Beautiful HTML Template (Shared Logic)
EMAIL_TEMPLATE = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <title>Resident Client Notification</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800;900&display=swap" rel="stylesheet">
    <style type="text/css">
        body, table, td, a { -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
        table, td { mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
        img { -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }
        table { border-collapse: separate !important; border-spacing: 0; }
        body { height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; background-color: #f7f9fc; font-family: 'Inter', Helvetica, Arial, sans-serif; }
        .mobile-padding { padding-left: 20px !important; padding-right: 20px !important; }
        .content { padding: 40px 24px !important; }
        .access-code { font-size: 32px !important; letter-spacing: 2px !important; word-break: break-all; }
        .header-text { font-size: 26px !important; }
        @media screen and (max-width: 600px) {
            .wrapper { width: 100% !important; max-width: 100% !important; box-sizing: border-box !important; }
            /* Increase right padding to account for the box-shadow so it doesn't cause horizontal scroll */
            .mobile-padding { padding-left: 10px !important; padding-right: 25px !important; box-sizing: border-box !important; }
            .content { padding: 40px 20px !important; }
            .access-code { font-size: 32px !important; letter-spacing: 2px !important; }
            .header-text { font-size: 26px !important; }
            /* Center and stack app store badges vertically on mobile */
            .mobile-stack a { display: block !important; margin: 15px auto !important; width: fit-content !important; }
        }
    </style>
</head>
<body style="margin: 0 !important; padding: 0 !important; background-color: #f7f9fc;">
    <center>
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed; background-color: #f7f9fc;">
            <tr>
                <td align="center" style="padding: 40px 0;">
                    <div style="max-width: 600px; width: 100%; margin: 0 auto;">
                        <table border="0" cellpadding="0" cellspacing="0" width="100%" class="wrapper" style="max-width: 600px;">
                            <tr>
                                <td align="center" style="padding-bottom: 25px;">
                                    <div style="font-family: 'Inter', Arial, sans-serif; font-size: 24px; font-weight: 800; color: #0f172a;">Resident Client</div>
                                </td>
                            </tr>
                        </table>
                    </div>
                    <div style="max-width: 600px; width: 100%; margin: 0 auto;" class="mobile-padding">
                        <table border="0" cellpadding="0" cellspacing="0" width="100%" class="wrapper" style="max-width: 600px; background-color: #ffffff; border-radius: 24px; border: 3px solid #0f172a; box-shadow: 10px 10px 0px #0f172a;">
                            <tr>
                                <td align="center" class="content" style="padding: 50px 40px; border-radius: 24px;">
                                    <h1 class="header-text" style="margin: 0; font-family: 'Inter', Helvetica, Arial, sans-serif; font-size: 32px; font-weight: 800; color: #0f172a; line-height: 1.2; letter-spacing: -0.5px;">
                                        {TITLE}
                                    </h1>
                                    <p style="margin: 15px 0 35px; font-family: 'Inter', Helvetica, Arial, sans-serif; font-size: 17px; font-weight: 500; color: #64748b; line-height: 1.6; max-width: 480px;">
                                        {BODY_TEXT}
                                    </p>
                                    
                                    {ACCESS_CODE_SECTION}
                                    {APP_STORE_SECTION}
                                </td>
                            </tr>
                        </table>
                    </div>
                </td>
            </tr>
        </table>
    </center>
</body>
</html>
"""

def send_email(
    email_to: str,
    subject: str,
    title: str = "Notification",
    body_text: str = "",
    access_code: str = None,
    code_label: str = "YOUR ACCESS CODE", # New parameter
    html_content: str = None, # Backwards compatibility if passing raw HTML
    sender_name: str = None,
    show_app_links: bool = True # Control visibility of app store links
) -> bool:
    
    if not settings.ZEPTOMAIL_API_KEY:
        print(f"⚠️ ZeptoMail API Key not found. Mocking email to {email_to}")
        return False
        
    final_html = html_content
    
    if not final_html:
        # Construct Body
        access_code_section = ""
        if access_code:
            access_code_section = f"""
            <div style="margin: 40px 0;">
                <div style="font-family: 'Inter', Helvetica, Arial, sans-serif; font-size: 14px; font-weight: 800; color: #94a3b8; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 5px;">
                    {code_label}
                </div>
                <div class="access-code" style="font-family: 'Inter', Helvetica, Arial, sans-serif; font-size: 56px; font-weight: 900; color: #9333ea; letter-spacing: 8px; line-height: 1.1; word-break: break-all;">
                    {access_code}
                </div>
            </div>
            """
            
        app_store_section = ""
        if show_app_links:
            app_store_section = """
            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr><td style="padding-bottom: 30px;"><div style="height: 1px; background-color: #e2e8f0; width: 100%;"></div></td></tr>
                <tr><td align="center" style="font-family: 'Inter', Helvetica, Arial, sans-serif; font-size: 15px; font-weight: 700; color: #0f172a; padding-bottom: 25px;">Download the App to Join</td></tr>
                <tr>
                    <td align="center">
                        <div class="mobile-stack">
                            <a href="{APP_URL}" style="text-decoration: none; display: inline-block; margin: 10px; padding: 14px 22px; background: #0f172a; color: #ffffff; border-radius: 999px; font-family: 'Inter', Arial, sans-serif; font-size: 15px; font-weight: 700;">Open App</a>
                        </div>
                    </td>
                </tr>
            </table>
            """
            
        app_url = settings.PUBLIC_WEB_APP_URL or "https://gatenode.app"
        final_html = EMAIL_TEMPLATE.replace("{TITLE}", title)\
                                     .replace("{BODY_TEXT}", body_text)\
                                     .replace("{ACCESS_CODE_SECTION}", access_code_section)\
                                     .replace("{APP_STORE_SECTION}", app_store_section.replace("{APP_URL}", app_url))

    url = settings.ZEPTOMAIL_API_URL
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": settings.ZEPTOMAIL_API_KEY
    }
    
    # Use config sender or fallback
    sender_email = settings.EMAIL_FROM_EMAIL or "noreply@gatenode.com"
    # Logic: If arg provided, use it. Else use config. Else fallback.
    final_sender_name = sender_name if sender_name else (settings.EMAIL_FROM_NAME or "Resident Client")
    
    payload = {
        "from": {"address": sender_email, "name": final_sender_name},
        "to": [{"email_address": {"address": email_to, "name": email_to.split("@")[0]}}],
        "subject": subject,
        "htmlbody": final_html
    }

    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code in [200, 201]:
                print(f"✅ ZeptoMail sent to {email_to}")
                return True
            else:
                print(f"❌ ZeptoMail failed: {response.text}")
                return False
    except Exception as e:
        print(f"❌ Error sending ZeptoMail to {email_to}: {e}")
        return False

# Transaction Receipt Template
RECEIPT_TEMPLATE = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <title>Payment Successful | Resident Client</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style type="text/css">
        /* RESET STYLES */
        body, table, td, a { -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
        table, td { mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
        img { -ms-interpolation-mode: bicubic; border: 0; outline: none; text-decoration: none; }
        table { border-collapse: separate !important; border-spacing: 0; }
        body { height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; background-color: #ffffff; font-family: 'Public Sans', Helvetica, Arial, sans-serif; }
        
        /* SPIN ANIMATION */
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .spin-logo { animation: spin 10s linear infinite; }

        /* MOBILE STYLES */
        @media screen and (max-width: 600px) {
            .wrapper { width: 100% !important; max-width: 100% !important; padding: 0 25px 0 10px !important; box-sizing: border-box !important; }
            .content { padding: 40px 20px !important; }
            .amount-text { font-size: 38px !important; }
            .header-text { font-size: 26px !important; }
        }
    </style>
</head>
<body style="margin: 0 !important; padding: 0 !important; background-color: #ffffff;">
    <center>
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed; background-color: #ffffff;">
            <tr>
                <td align="center" style="padding: 60px 0;">
                    <!-- [LOGO] -->
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 500px;">
                        <tr>
                            <td align="center" style="padding-bottom: 40px;">
                                <div style="font-family: 'Public Sans', sans-serif; font-size: 28px; font-weight: 900; color: #000000;">Resident Client</div>
                            </td>
                        </tr>
                    </table>

                    <!-- [MAIN CARD] -->
                    <div style="max-width: 500px; width: 100%; margin: 0 auto;" class="wrapper">
                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #ffffff; border-radius: 40px; border: 4px solid #000000; box-shadow: 14px 14px 0px #000000;">
                            <tr>
                                <td align="center" class="content" style="padding: 60px 40px;">
                                    <!-- Header -->
                                    <h1 class="header-text" style="margin: 0; font-family: 'Public Sans', sans-serif; font-size: 32px; font-weight: 900; color: #000000; line-height: 1.1; letter-spacing: -1px; text-transform: uppercase;">
                                        Payment Received
                                    </h1>
                                    <p style="margin: 15px 0 40px; font-family: 'Public Sans', sans-serif; font-size: 18px; font-weight: 600; color: #525252; line-height: 1.4;">
                                        {USER_NAME}, your transaction has been confirmed.
                                    </p>

                                    <!-- HERO AMOUNT -->
                                    <div style="background-color: #f4f4f5; border: 4px solid #000000; border-radius: 30px; padding: 35px 20px; margin-bottom: 40px; box-shadow: 8px 8px 0px #9333ea;">
                                        <div style="font-size: 14px; font-weight: 800; color: #71717a; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 10px;">
                                            TOTAL PAID
                                        </div>
                                        <div class="amount-text" style="font-size: 52px; font-weight: 900; color: #000000; letter-spacing: -2px;">
                                            ₦{AMOUNT}
                                        </div>
                                    </div>

                                    <!-- TRANSACTION DETAILS -->
                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                        <tr>
                                            <td align="left" style="padding: 15px 0; border-bottom: 3px solid #f4f4f5;">
                                                <span style="font-size: 13px; font-weight: 800; color: #a1a1aa; text-transform: uppercase; letter-spacing: 1px;">Service/Bill</span>
                                            </td>
                                            <td align="right" style="padding: 15px 0; border-bottom: 3px solid #f4f4f5;">
                                                <span style="font-size: 16px; font-weight: 800; color: #000000;">{BILL_TYPE}</span>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td align="left" style="padding: 15px 0; border-bottom: 3px solid #f4f4f5;">
                                                <span style="font-size: 13px; font-weight: 800; color: #a1a1aa; text-transform: uppercase; letter-spacing: 1px;">House & Address</span>
                                            </td>
                                            <td align="right" style="padding: 15px 0; border-bottom: 3px solid #f4f4f5;">
                                                <div style="font-size: 16px; font-weight: 800; color: #000000;">{HOUSE_NAME}</div>
                                                <div style="font-size: 14px; font-weight: 500; color: #71717a;">{ADDRESS}</div>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td align="left" style="padding: 15px 0; border-bottom: 3px solid #f4f4f5;">
                                                <span style="font-size: 13px; font-weight: 800; color: #a1a1aa; text-transform: uppercase; letter-spacing: 1px;">Paid On</span>
                                            </td>
                                            <td align="right" style="padding: 15px 0; border-bottom: 3px solid #f4f4f5;">
                                                <span style="font-size: 16px; font-weight: 800; color: #000000;">{TRANSACTION_TIME}</span>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td align="left" style="padding: 15px 0;">
                                                <span style="font-size: 13px; font-weight: 800; color: #a1a1aa; text-transform: uppercase; letter-spacing: 1px;">Reference</span>
                                            </td>
                                            <td align="right" style="padding: 15px 0;">
                                                <span style="font-size: 14px; font-weight: 800; color: #9333ea;">{TRANSACTION_ID}</span>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                        </table>
                    </div>

                    <!-- [FOOTER] -->
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 500px;">
                        <tr>
                            <td align="center" style="padding-top: 50px; font-family: 'Public Sans', sans-serif; font-size: 14px; color: #a1a1aa; font-weight: 500;">
                                <p style="margin: 0;">&copy; {CURRENT_YEAR} Resident Client</p>
                                <p style="margin: 10px 0 0;">Questions? Hit us up in the app.</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </center>
</body>
</html>
"""

def send_receipt(
    email_to: str,
    user_name: str,
    amount: str,
    bill_type: str,
    house_name: str,
    address: str,
    transaction_time: str,
    transaction_id: str,
    current_year: str
) -> bool:
    """
    Sends a Transaction Receipt email using ZeptoMail.
    """
    if not settings.ZEPTOMAIL_API_KEY:
        print(f"⚠️ ZeptoMail API Key not found. Mocking receipt email to {email_to}")
        return False

    final_html = RECEIPT_TEMPLATE.replace("{USER_NAME}", user_name)\
                                 .replace("{AMOUNT}", amount)\
                                 .replace("{BILL_TYPE}", bill_type)\
                                 .replace("{HOUSE_NAME}", house_name)\
                                 .replace("{ADDRESS}", address)\
                                 .replace("{TRANSACTION_TIME}", transaction_time)\
                                 .replace("{TRANSACTION_ID}", transaction_id)\
                                 .replace("{CURRENT_YEAR}", current_year)

    url = settings.ZEPTOMAIL_API_URL
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": settings.ZEPTOMAIL_API_KEY
    }
    
    sender_email = settings.EMAIL_FROM_EMAIL or "noreply@gatenode.com"
    sender_name = settings.EMAIL_FROM_NAME or "Resident Client"
    
    payload = {
        "from": {"address": sender_email, "name": sender_name},
        "to": [{"email_address": {"address": email_to, "name": email_to.split("@")[0]}}],
        "subject": "Payment Receipt",
        "htmlbody": final_html
    }

    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code in [200, 201]:
                print(f"✅ Receipt sent to {email_to}")
                return True
            else:
                print(f"❌ Receipt failed: {response.text}")
                return False
    except Exception as e:
        print(f"❌ Error sending Receipt to {email_to}: {e}")
        return False


async def send_email_async(**kwargs) -> bool:
    return await run_in_threadpool(send_email, **kwargs)


async def send_receipt_async(**kwargs) -> bool:
    return await run_in_threadpool(send_receipt, **kwargs)
