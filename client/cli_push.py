import sys
import os
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))
from core.push import send_push_notification

async def main():
    token = "f7K1yj9DrUdPuG-4Xu1srd:APA91bErLoGmmu5c91TvEzLpKZTsydBmwxcMNmZbicEEE97laejlfOvp5kLpWwgV1odt2oUAq-kCw_Lq-hQyyifpWVbfRYfdr2O5pta-2e3G-oy-AhGTPms"
    print("Testing push notification...")
    
    await send_push_notification(
        token=token,
        title="Test Notification",
        body="This is a test notification from the backend assistant.",
        data={"type": "test"},
        platform="fcm"
    )
    print("Finished")

if __name__ == "__main__":
    asyncio.run(main())
