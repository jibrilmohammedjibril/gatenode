
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, desc
from typing import Optional, List
import logging
from core.events import event_manager
from core.push import notify_user_devices
from core.models import Notification, User, Unit, Estate, Block

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Service for managing persisted notifications in the database.
    """
    async def create_notification(self, db: AsyncSession, user_id: str, title: str, message: str) -> Notification:
        notif = Notification(
            title=title,
            message=message,
            user_id=user_id,
            is_read=False
        )
        db.add(notif)
        await db.commit()
        await db.refresh(notif)
        return notif

    async def get_notifications(self, db: AsyncSession, user_id: str, limit: int = 50, unread_only: bool = False) -> List[Notification]:
        query = select(Notification).where(Notification.user_id == user_id)
        
        if unread_only:
            query = query.where(Notification.is_read == False)
            
        query = query.order_by(Notification.created_at.desc()).limit(limit)
        
        result = await db.execute(query)
        return result.scalars().all()

    async def mark_as_read(self, db: AsyncSession, notification_id: str, user_id: str) -> bool:
        stmt = select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
        result = await db.execute(stmt)
        notif = result.scalars().first()
        
        if notif:
            notif.is_read = True
            await db.commit()
            return True
        return False
        
    async def mark_all_as_read(self, db: AsyncSession, user_id: str):
        stmt = update(Notification).where(
            Notification.user_id == user_id, 
            Notification.is_read == False
        ).values(is_read=True)
        await db.execute(stmt)
        await db.commit()

notification_service = NotificationService()

class NotificationManager:
    """
    Centralized manager for all application push notifications.
    Enforces consistency in Titles, Bodies, Deep Links, and Data Payloads.
    Also handles persistence via NotificationService.
    """
    
    async def _send(self, db: AsyncSession, user_id: str, title: str, body: str, data: dict, **kwargs):
        # 1. Persist to DB
        try:
            await notification_service.create_notification(db, user_id, title, body)
            try:
                await event_manager.publish(
                    "notification",
                    {"title": title, "message": body, **(data or {})},
                    user_id,
                )
            except Exception as e:
                logger.error(f"Failed to publish notification SSE for user {user_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to persist notification to DB for user {user_id}: {e}")
            try:
                await db.rollback()
            except:
                pass
            # Do not return here. If DB logging fails, we still want to attempt the actual Push Notification
        
        # 2. Send Push
        try:
            await notify_user_devices(
                user_id=user_id,
                title=title,
                body=body,
                data=data,
                db=db,
                **kwargs
            )
        except Exception as e:
            logger.error(f"Push Notification transmission failed for user {user_id}: {e}")

    async def send_emergency_alert(self, db: AsyncSession, user_id: str, title: str, body: str, alert_id: str):
        await self._send(
            db=db,
            user_id=user_id,
            title=title,
            body=body,
            data={"type": "alert", "alert_id": alert_id, "priority": "high"},
            channel_id="urgent_alerts",
            group=f"alert_{alert_id}",
            ttl=3600,
        )

    async def send_visitor_arrival(self, db: AsyncSession, user_id: str, visitor_name: str, visitor_id: str):
        await self._send(
            db=db,
            user_id=user_id,
            title="Visitor Arrived",
            body=f"{visitor_name} has arrived at the gate.",
            data={"type": "visitor_arrival", "visitorId": visitor_id},
            group="visitor_updates",
            ttl=600 # 10 mins expiry
        )

    async def send_visitor_checkout(self, db: AsyncSession, user_id: str, visitor_name: str, visitor_id: str):
        await self._send(
            db=db,
            user_id=user_id,
            title="Visitor Departed",
            body=f"{visitor_name} has left the estate.",
            data={"type": "visitor_checkout", "visitorId": visitor_id},
            group="visitor_updates"
        )

    async def send_access_denied(self, db: AsyncSession, user_id: str, visitor_name: str, visitor_id: str):
        await self._send(
            db=db,
            user_id=user_id,
            title="Access Denied 🚫",
            body=f"Entry was refused for {visitor_name}.",
            data={"type": "visitor_denied", "visitorId": visitor_id},
            ttl=3600 # 1 hour
        )

    async def send_invite_expiring(self, db: AsyncSession, user_id: str, visitor_name: str, invite_id: str, minutes_left: int):
        await self._send(
            db=db,
            user_id=user_id,
            title="Invite Expiring Soon",
            body=f"Your invite for {visitor_name} expires in {minutes_left} minutes. Extension needed?",
            data={"type": "invite_expiry", "inviteId": invite_id, "action": "extend"},
            ttl=minutes_left * 60
        )

    async def send_visitor_waiting_approval(self, db: AsyncSession, user_id: str, visitor_name: str):
        await self._send(
            db=db,
            user_id=user_id,
            title="Approval Request",
            body=f"{visitor_name} is at the gate requesting entry. Approve?",
            data={"type": "manual_approval", "visitorName": visitor_name},
            ttl=600, # 10 mins
            channel_id="urgent_alerts"
        )

    # --- Subscriptions ---
    async def send_subscription_warning(self, db: AsyncSession, user_id: str, days_left: int):
        # 1. Send Push
        await self._send(
            db=db,
            user_id=user_id,
            title="Premium Trial Expiring Soon",
            body=f"Your premium trial expires in {days_left} day{'s' if days_left > 1 else ''}. Don't lose access to premium features!",
            data={"type": "subscription_warning", "daysLeft": days_left},
            channel_id="account_alerts"
        )
        
        # 2. Send Email
        try:
            from sqlalchemy.future import select
            from core.models import User
            from core.mail import send_email_async
            
            user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
            if user and user.email:
                await send_email_async(
                    email_to=user.email,
                    subject=f"Your Premium Trial Expires in {days_left} Day{'s' if days_left > 1 else ''}",
                    title="Trial Expiring Soon",
                    body_text=f"Hi {user.full_name},<br><br>We hope you're enjoying the app. Your 30-day premium trial will expire in exactly {days_left} day{'s' if days_left > 1 else ''}.<br><br>Please upgrade your plan in the app to retain access to features like creating invites, registering vehicles, and broadcasting emergency alerts.",
                    show_app_links=True
                )
        except Exception as e:
            print(f"Error sending sub warning email: {e}")

    async def send_subscription_expired(self, db: AsyncSession, user_id: str):
        # 1. Send Push
        await self._send(
            db=db,
            user_id=user_id,
            title="Premium Trial Expired",
            body="Your premium trial has expired. You are now on the Basic Plan.",
            data={"type": "subscription_expired"},
            channel_id="account_alerts"
        )
        
        # 2. Send Email
        try:
            from sqlalchemy.future import select
            from core.models import User
            from core.mail import send_email_async
            
            user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
            if user and user.email:
                await send_email_async(
                    email_to=user.email,
                    subject="Your Premium Trial Has Expired",
                    title="Trial Expired",
                    body_text=f"Hi {user.full_name},<br><br>Your 30-day premium trial has officially expired, and your account has been transitioned to the Basic Plan.<br><br>You can upgrade your subscription at any time within the app to regain full access to all resident features.",
                    show_app_links=True
                )
        except Exception as e:
            print(f"Error sending sub expired email: {e}")

    # --- Bills & Wallet ---
    async def send_new_bill(self, db: AsyncSession, user_id: str, bill_title: str, amount: int, bill_id: str):
        # Amount in Kobo
        naira = "{:,.2f}".format(amount / 100)
        await self._send(
            db=db,
            user_id=user_id,
            title=f"New Bill: {bill_title}",
            body=f"A bill of ₦{naira} has been generated.",
            data={"type": "new_bill", "billId": bill_id},
            group="bills"
        )

    async def send_low_power_alert(self, db: AsyncSession, user_id: str, units_left: float, meter_id: str):
        await self._send(
            db=db,
            user_id=user_id,
            title="Low Power Balance ⚡",
            body=f"Your meter balance is under {units_left} units. Top up now to avoid disconnection.",
            data={"type": "low_power", "meterId": meter_id},
            channel_id="utility_alerts"
        )

    async def send_payment_success(self, db: AsyncSession, user_id: str, amount: int, tx_ref: str, unit_id: str = None):
         naira = "{:,.2f}".format(amount / 100)
         
         # 1. Send Push
         await self._send(
            db=db,
            user_id=user_id,
            title="Wallet Funded 💰",
            body=f"Your wallet has been funded with ₦{naira}.",
            data={"type": "payment_success", "txId": tx_ref},
            channel_id="payments"
        )

         # 2. Send Receipt Email
         try:
             # Fetch details
             stmt = select(User).where(User.id == user_id)
             user = (await db.execute(stmt)).scalars().first()
             
             house_name = "N/A"
             address = "N/A"
             
             if unit_id:
                 stmt_unit = select(Unit, Block, Estate).join(Block, Unit.block_id == Block.id).join(Estate, Block.estate_id == Estate.id).where(Unit.id == unit_id)
                 res = (await db.execute(stmt_unit)).first()
                 if res:
                     unit_obj, block_obj, estate_obj = res
                     house_name = f"{unit_obj.unit_number} {block_obj.name or ''}"
                     address = f"{estate_obj.name}, {estate_obj.address}"

             if user and user.email:
                 from datetime import datetime
                 from core import mail
                 formatted_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
                 current_year = str(datetime.now().year)
                 
                 await mail.send_receipt_async(
                     email_to=user.email,
                     user_name=user.full_name,
                     amount=naira,
                     bill_type="Wallet Top Up",
                     house_name=house_name,
                     address=address,
                     transaction_time=formatted_time,
                     transaction_id=tx_ref,
                     current_year=current_year
                 )
         except Exception as e:
             print(f"Error sending receipt email: {e}")
    
    async def send_service_payment_success(self, db: AsyncSession, user_id: str, amount: int, service_name: str, tx_ref: str, unit_id: str = None):
         """
         Notify user of successful bill payment (Airtime, Electricity, etc)
         """
         naira_val = amount / 100
         formatted_amount = "{:,.2f}".format(naira_val)
         
         # 1. Send Push
         await self._send(
            db=db,
            user_id=user_id,
            title="Bill Paid Successfully",
            body=f"Your payment of ₦{formatted_amount} for {service_name} was successful.",
            data={"type": "service_payment_success", "txId": tx_ref, "service": service_name},
            channel_id="payments"
        )
         
         # 2. Send Receipt Email
         try:
             # Fetch details
             stmt = select(User).where(User.id == user_id)
             user = (await db.execute(stmt)).scalars().first()
             
             house_name = "N/A"
             address = "N/A"
             
             if unit_id:
                 stmt_unit = select(Unit, Block, Estate).join(Block, Unit.block_id == Block.id).join(Estate, Block.estate_id == Estate.id).where(Unit.id == unit_id)
                 res = (await db.execute(stmt_unit)).first()
                 if res:
                     unit_obj, block_obj, estate_obj = res
                     house_name = f"{unit_obj.unit_number} {block_obj.name or ''}"
                     address = f"{estate_obj.name}, {estate_obj.address}"

             if user and user.email:
                 from datetime import datetime
                 from core import mail
                 formatted_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
                 current_year = str(datetime.now().year)
                 
                 await mail.send_receipt_async(
                     email_to=user.email,
                     user_name=user.full_name,
                     amount=formatted_amount,
                     bill_type=service_name,
                     house_name=house_name,
                     address=address,
                     transaction_time=formatted_time,
                     transaction_id=tx_ref,
                     current_year=current_year
                 )
         except Exception as e:
             print(f"Error sending receipt email: {e}")

    async def send_payment_failed(self, db: AsyncSession, user_id: str, reason: str, tx_ref: str):
         await self._send(
            db=db,
            user_id=user_id,
            title="Payment Failed ❌",
            body=f"We couldn't process your payment. {reason}",
            data={"type": "payment_failed", "txId": tx_ref}
        )

    # --- Household ---
    async def send_added_to_household(self, db: AsyncSession, user_id: str, unit_number: str, house_id: str):
        await self._send(
            db=db,
            user_id=user_id,
            title="Welcome Home 🏠",
            body=f"You've been added to the household at {unit_number}.",
            data={"type": "household_add", "houseId": house_id}
        )

    async def send_removed_from_household(self, db: AsyncSession, user_id: str, unit_number: str, house_id: str):
        await self._send(
            db=db,
            user_id=user_id,
            title="Household Updated 🚪",
            body=f"You have been removed from the household at {unit_number}.",
            data={"type": "household_remove", "houseId": house_id}
        )

    async def send_post_reply(self, db: AsyncSession, user_id: str, replier_name: str, post_id: str):
        await self._send(
            db=db,
            user_id=user_id,
            title="New Reply 💬",
            body=f"{replier_name} replied to your post.",
            data={"type": "post_reply", "postId": post_id},
            group="feed_updates"
        )

    async def send_chat_message(
        self,
        db: AsyncSession,
        user_id: str,
        sender_name: str,
        conversation_id: str,
        message_preview: str,
        group_name: str | None = None,
    ):
        title = f"New message from {sender_name}"
        if group_name:
            title = f"{sender_name} in {group_name}"

        await self._send(
            db=db,
            user_id=user_id,
            title=title,
            body=message_preview,
            data={"type": "chat_message", "conversationId": conversation_id},
            group=f"conversation_{conversation_id}",
            channel_id="messages",
        )

    # --- Support ---
    async def send_support_reply(self, db: AsyncSession, user_id: str, message_preview: str, conversation_id: str):
        await self._send(
            db=db,
            user_id=user_id,
            title="Support Reply",
            body=f"Agent: \"{message_preview}\"",
            data={"type": "support_msg", "conversationId": conversation_id},
            group="support"
        )

notifications = NotificationManager()
