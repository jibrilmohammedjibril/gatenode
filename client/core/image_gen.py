import asyncio
import io
from playwright.async_api import async_playwright
import boto3
from botocore.client import Config
from .config import settings

import asyncio
import io
import base64
from playwright.async_api import async_playwright
import qrcode
import boto3
from botocore.client import Config
from .config import settings

# HTML Template - No JS, No External Scripts
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QR Code</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #ffffff;
            --text-primary: #000000;
            --text-secondary: #666666;
            --font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        body {
            background-color: transparent;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            font-family: var(--font-family);
            -webkit-font-smoothing: antialiased;
        }
        .qr-card {
            background-color: var(--bg-color);
            padding: 20px;
            border-radius: 32px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            width: 240px;
        }
        .guest-name {
            font-size: 18px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 8px;
            text-align: center;
            width: 100%;
            word-wrap: break-word;
        }
        .qr-container {
            background: white;
            padding: 0;
            margin-bottom: 8px;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .qr-container img {
            display: block;
            width: 200px;
            height: 200px;
        }
        .label {
            font-size: 14px;
            color: var(--text-secondary);
            font-weight: 500;
            margin-top: 8px;
            margin-bottom: 2px;
        }
        .access-code {
            font-size: 24px;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: 2px;
            margin-bottom: 12px;
        }
        .validity-section {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 100%;
        }
        .date {
            font-size: 14px;
            color: var(--text-primary);
            font-weight: 600;
            margin-top: 8px;
        }
        .time {
            font-size: 16px;
            color: var(--text-primary);
            font-weight: 700;
            margin-top: 2px;
        }
    </style>
</head>
<body>
    <div class="qr-card">
        <div class="guest-name">{name}</div>
        <div class="qr-container">
            <img src="data:image/png;base64,{qr_base64}" alt="QR Code" />
        </div>
        <div class="label">{label}</div>
        <div class="access-code">{code}</div>
        <div class="validity-section">
            <div class="date">{date}</div>
            <div class="time">{time}</div>
        </div>
    </div>
</body>
</html>
"""

async def generate_invite_image(visitor_name, invite_type, access_code, date_str, time_range):
    """
    Generates an invite image. 
    1. Creates QR code in Python (Reliable).
    2. Embeds into HTML as Base64.
    3. Renders HTML via Playwright.
    """
    
    # 1. Generate QR Code (Python)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=0,
    )
    qr.add_data(access_code) # Encoding the Access Code directly
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to Base64
    buffered = io.BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    # 2. Prepare HTML
    # Use replace() instead of format() to avoid issues with CSS curly braces
    html_content = HTML_TEMPLATE \
        .replace("{name}", visitor_name) \
        .replace("{qr_base64}", qr_base64) \
        .replace("{label}", invite_type) \
        .replace("{code}", access_code) \
        .replace("{date}", date_str) \
        .replace("{time}", time_range)
        
    async with async_playwright() as p:
        # Launch browser (Chromium)
        browser = await p.chromium.launch(args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        # Viewport 414x896 (Mobile) + Scale 3 (Retina)
        context = await browser.new_context(
            device_scale_factor=3,
            viewport={'width': 414, 'height': 896} 
        )
        page = await context.new_page()
        
        # Set Content - No Scripts to wait for!
        # Just wait for networkidle (Fonts)
        try:
            await page.set_content(html_content, wait_until="networkidle", timeout=15000)
        except:
            print("Warning: Network idle timeout (fonts might be slow), proceeding anyway.")
        
        # Select the card element
        card = await page.query_selector(".qr-card")
        
        if not card:
            await browser.close()
            raise Exception("Could not find .qr-card element")
            
        # Screenshot the element
        screenshot_bytes = await card.screenshot(type="png")
        
        await browser.close()
        
        return io.BytesIO(screenshot_bytes)

def upload_to_minio(file_obj, filename):
    s3_client = boto3.client(
        's3',
        endpoint_url=f"https://{settings.MINIO_ENDPOINT}" if settings.MINIO_SECURE else f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4', s3={'addressing_style': 'path'})
    )
    
    try:
        s3_client.upload_fileobj(
            file_obj,
            settings.MINIO_BUCKET,
            filename,
            ExtraArgs={'ContentType': 'image/png', 'ACL': 'public-read'}
        )
        
        # Construct URL
        url = f"https://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{filename}"
        return url
    except Exception as e:
        print(f"Upload failed: {e}")
        return None

def delete_from_minio(filename: str):
    """
    Deletes an object from the MinIO/S3 bucket.
    Used for garbage collection after WhatsApp template dispatch.
    """
    s3_client = boto3.client(
        's3',
        endpoint_url=f"https://{settings.MINIO_ENDPOINT}" if settings.MINIO_SECURE else f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=Config(signature_version='s3v4', s3={'addressing_style': 'path'})
    )
    
    try:
        s3_client.delete_object(
            Bucket=settings.MINIO_BUCKET,
            Key=filename
        )
        print(f"DEBUG: Successfully deleted {filename} from MinIO")
        return True
    except Exception as e:
        print(f"ERROR: Failed to delete {filename} from MinIO: {e}")
        return False
