import json
import time
from typing import Any, Dict, Optional, Iterable, List

import httpx

from core.config import settings


class NombaAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NombaService:
    def __init__(self) -> None:
        self.base_url = settings.NOMBA_BASE_URL.rstrip("/")
        self.client_id = settings.NOMBA_CLIENT_ID
        self.client_secret = settings.NOMBA_CLIENT_SECRET
        self.account_id = settings.NOMBA_ACCOUNT_ID
        self._access_token: Optional[str] = None
        self._bank_list_cache: Optional[List[Dict[str, Any]]] = None
        self._bank_list_cache_at: float = 0.0
        self._bank_list_cache_ttl_seconds = 12 * 60 * 60

    @staticmethod
    def _normalize_slug(value: str) -> str:
        return value.strip().lower()

    @staticmethod
    def _is_electricity_meter_type(value: str) -> bool:
        return NombaService._normalize_slug(value) in {"prepaid", "postpaid"}

    @staticmethod
    def _is_cable_type(value: str) -> bool:
        return NombaService._normalize_slug(value) in {"dstv", "gotv", "startimes", "showmax"}

    @staticmethod
    def _is_telco(value: str) -> bool:
        return NombaService._normalize_slug(value) in {"mtn", "glo", "airtel", "9mobile"}

    def _electricity_meter_options(self) -> List[Dict[str, Any]]:
        return [
            {"slug": "prepaid", "name": "Prepaid", "type": "Electricity"},
            {"slug": "postpaid", "name": "Postpaid", "type": "Electricity"},
        ]

    @staticmethod
    def _normalize_plan_amount_to_kobo(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(float(value) * 100)
        except (TypeError, ValueError):
            return None

    def _static_billers_for_category(self, category: str) -> List[Dict[str, Any]]:
        category_slug = self._normalize_slug(category)
        if category_slug == "electricity":
            return []
        if category_slug == "cable":
            return [
                {"id": "dstv", "name": "DSTV", "type": "cable", "options": []},
                {"id": "gotv", "name": "GOTV", "type": "cable", "options": []},
                {"id": "startimes", "name": "Startimes", "type": "cable", "options": []},
                {"id": "showmax", "name": "Showmax", "type": "cable", "options": []},
            ]
        if category_slug in {"airtime", "data", "internet"}:
            return [
                {"id": "mtn", "name": "MTN", "type": category_slug, "options": []},
                {"id": "glo", "name": "GLO", "type": category_slug, "options": []},
                {"id": "airtel", "name": "Airtel", "type": category_slug, "options": []},
                {"id": "9mobile", "name": "9mobile", "type": category_slug, "options": []},
            ]
        return []

    async def _get_access_token(self) -> str:
        if self._access_token:
            # Note: For production, we should handle token expiration.
            # This is a simplified version.
            return self._access_token
            
        if not self.client_id or not self.client_secret:
            raise NombaAPIError("Nomba is not configured")

        url = f"{self.base_url}/v1/auth/token/issue"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers={"accountId": self.account_id})

        if response.status_code not in (200, 201, 202):
            try:
                error_payload = response.json()
            except Exception:
                error_payload = response.text
            raise NombaAPIError(f"Nomba auth failed: {error_payload}", status_code=response.status_code)
            
        data = response.json().get("data", {})
        self._access_token = data.get("access_token")
        if not self._access_token:
            raise NombaAPIError("Nomba auth did not return an access token")
            
        return self._access_token

    async def _headers(self) -> Dict[str, str]:
        token = await self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "accountId": self.account_id,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        headers = await self._headers()

        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, json=payload, params=params, headers=headers)

        if response.status_code not in (200, 201, 202):
            try:
                error_payload = response.json()
            except Exception:
                error_payload = response.text
            raise NombaAPIError(f"Nomba request failed: {error_payload}", status_code=response.status_code)

        try:
            return response.json()
        except Exception:
            return {}

    async def _request_with_candidates(
        self,
        method: str,
        endpoints: Iterable[str],
        *,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        last_error: Optional[NombaAPIError] = None
        for endpoint in endpoints:
            try:
                return await self._request(method, endpoint, payload=payload, params=params)
            except NombaAPIError as exc:
                last_error = exc
                if exc.status_code not in {400, 404, 405, 409, 422}:
                    raise

        if last_error:
            raise last_error
        raise NombaAPIError("Nomba request failed")

    async def create_virtual_account(
        self,
        *,
        account_ref: str,
        account_name: str,
        bvn: str,
        currency: str = "NGN",
    ) -> Dict[str, Any]:
        # Nomba virtual accounts are created on the documented /v1/accounts/virtual endpoint.
        # Per Nomba docs, accountRef, accountName, and currency are required; bvn is optional.
        payload = {
            "accountRef": account_ref,
            "accountName": account_name,
            "currency": currency,
            "bvn": bvn,
        }
        return await self._request("POST", "/v1/accounts/virtual", payload=payload)

    async def list_electricity_discos(self) -> Dict[str, Any]:
        return await self._request("GET", "/v1/bill/electricity/discos")

    async def lookup_electricity_customer(self, *, disco: str, customer_id: str) -> Dict[str, Any]:
        return await self._request(
            "GET",
            "/v1/bill/electricity/lookup",
            params={"disco": disco, "customerId": customer_id},
        )

    async def vend_electricity(
        self,
        *,
        disco: str,
        merchant_tx_ref: str,
        payer_name: str,
        amount: int,
        customer_id: str,
        meter_type: str,
    ) -> Dict[str, Any]:
        payload = {
            "disco": disco,
            "merchantTxRef": merchant_tx_ref,
            "payerName": payer_name,
            "amount": amount,
            "customerId": customer_id,
            "meterType": meter_type,
        }
        return await self._request("POST", "/v1/bill/electricity", payload=payload)

    async def list_data_plans(self, *, telco: str) -> Dict[str, Any]:
        payload = await self._request("GET", f"/v1/bill/data-plan/{telco}")
        data = payload.get("data", [])
        if isinstance(data, list):
            normalized: List[Dict[str, Any]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                amount = self._normalize_plan_amount_to_kobo(item.get("amount"))
                normalized.append(
                    {
                        **item,
                        "amount": amount,
                        "minimum_amount": amount,
                        "maximum_amount": amount,
                        "slug": item.get("slug") or item.get("plan"),
                        "name": item.get("plan") or item.get("name"),
                        "type": item.get("type") or "Data",
                    }
                )
            payload["data"] = normalized
        return payload

    async def vend_airtime(
        self,
        *,
        amount: int,
        phone_number: str,
        network: str,
        merchant_tx_ref: str,
        sender_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "amount": amount,
            "phoneNumber": phone_number,
            "network": network,
            "merchantTxRef": merchant_tx_ref,
        }
        if sender_name:
            payload["senderName"] = sender_name
        return await self._request("POST", "/v1/bill/topup", payload=payload)

    async def vend_data(
        self,
        *,
        amount: int,
        phone_number: str,
        network: str,
        merchant_tx_ref: str,
        sender_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "amount": amount,
            "phoneNumber": phone_number,
            "network": network,
            "merchantTxRef": merchant_tx_ref,
        }
        if sender_name:
            payload["senderName"] = sender_name
        return await self._request("POST", "/v1/bill/data", payload=payload)

    async def list_cabletv_plans(self, *, cable_tv_type: str) -> Dict[str, Any]:
        payload = await self._request(
            "GET",
            "/v1/bill/cableTvProduct",
            params={"cableTvType": cable_tv_type},
        )
        data = payload.get("data", [])
        if isinstance(data, list):
            normalized: List[Dict[str, Any]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                amount = self._normalize_plan_amount_to_kobo(item.get("amount"))
                normalized.append(
                    {
                        **item,
                        "amount": amount,
                        "minimum_amount": amount,
                        "maximum_amount": amount,
                        "slug": item.get("slug") or item.get("subScriptionType") or item.get("name"),
                        "name": item.get("subScriptionType") or item.get("name"),
                        "type": "CableTV",
                    }
                )
            payload["data"] = normalized
        return payload

    async def lookup_cabletv_customer(self, *, cable_tv_type: str, customer_id: str) -> Dict[str, Any]:
        return await self._request(
            "GET",
            "/v1/bill/cabletv/lookup",
            params={"cableTvType": cable_tv_type, "customerId": customer_id},
        )

    async def subscribe_cabletv(
        self,
        *,
        cable_tv_type: str,
        merchant_tx_ref: str,
        payer_name: str,
        amount: int,
        customer_id: str,
    ) -> Dict[str, Any]:
        payload = {
            "cableTvType": cable_tv_type,
            "merchantTxRef": merchant_tx_ref,
            "payerName": payer_name,
            "amount": amount,
            "customerId": customer_id,
        }
        return await self._request("POST", "/v1/bill/cabletv", payload=payload)

    async def fetch_account_balance(self, *, account_id: str) -> Dict[str, Any]:
        # Placeholder for fetching account balance if Nomba supports per-virtual-account balances
        # Otherwise, this might need to fetch the main account balance
        return await self._request("GET", f"/v1/accounts/{account_id}/balance")

    async def fetch_account_balance_kobo(self, *, account_id: str) -> int:
        response = await self.fetch_account_balance(account_id=account_id)
        data = response.get("data", {})
        balance = data.get("balance", 0)
        # Assuming balance is returned in Naira or Kobo; normalize either shape.
        try:
            return int(float(balance) * 100) if "." in str(balance) else int(balance)
        except (ValueError, TypeError):
            return 0

    async def create_transfer(
        self,
        *,
        amount: int, # in kobo typically, need to check if Nomba expects NGN
        account_number: str,
        account_name: str,
        bank_code: str,
        narration: str,
        reference: str,
    ) -> Dict[str, Any]:
        payload = {
            "amount": amount / 100.0, # convert kobo to Naira if Nomba requires NGN
            "accountNumber": account_number,
            "accountName": account_name,
            "bankCode": bank_code,
            "narration": narration,
            "merchantTxRef": reference,
        }
        return await self._request("POST", "/v1/transfers/bank", payload=payload)

    def _extract_account_lookup_name(self, payload: Dict[str, Any]) -> Optional[str]:
        data = payload.get("data", payload)
        if isinstance(data, dict):
            for key in ("accountName", "account_name", "beneficiaryName", "name"):
                value = data.get(key)
                if value:
                    return str(value).strip()
        if isinstance(payload, dict):
            for key in ("accountName", "account_name", "beneficiaryName", "name"):
                value = payload.get(key)
                if value:
                    return str(value).strip()
        return None

    async def resolve_bank_account(
        self,
        *,
        bank_code: str,
        account_number: str,
    ) -> Dict[str, Any]:
        payload = {
            "bankCode": bank_code,
            "accountNumber": account_number,
        }
        return await self._request_with_candidates(
            "POST",
            (
                "/v1/transfers/bank/lookup",
                "/v1/transfers/bank/account/lookup",
                "/v1/transfers/bank/resolve",
            ),
            payload=payload,
        )

    def _normalize_bank_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        bank_name = (
            item.get("bankName")
            or item.get("bank_name")
            or item.get("name")
            or item.get("institutionName")
            or ""
        )
        bank_code = (
            item.get("bankCode")
            or item.get("bank_code")
            or item.get("code")
            or item.get("institutionCode")
            or ""
        )
        return {
            "bankName": str(bank_name).strip(),
            "bankCode": str(bank_code).strip(),
        }

    def _extract_banks(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = payload.get("data", payload)
        if isinstance(data, dict):
            for key in ("banks", "items", "results", "data"):
                nested = data.get(key)
                if isinstance(nested, list):
                    return [self._normalize_bank_item(item) for item in nested if isinstance(item, dict)]
            return [self._normalize_bank_item(data)] if data else []
        if isinstance(data, list):
            return [self._normalize_bank_item(item) for item in data if isinstance(item, dict)]
        return []

    async def list_banks(self, *, force_refresh: bool = False) -> List[Dict[str, Any]]:
        now = time.time()
        if (
            not force_refresh
            and self._bank_list_cache is not None
            and (now - self._bank_list_cache_at) < self._bank_list_cache_ttl_seconds
        ):
            return self._bank_list_cache

        response = await self._request("GET", "/v1/transfers/banks")
        banks = self._extract_banks(response)
        self._bank_list_cache = banks
        self._bank_list_cache_at = now
        return banks
        
    async def create_book_transfer(
        self,
        *,
        source_account_id: str,
        destination_account_id: str,
        amount: int,
        reference: str,
        narration: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Virtual accounts are inbound-only on Nomba, so the client keeps
        # internal ledger moves separate from the provider.
        return {
            "status": "success",
            "data": {
                "id": reference,
                "sourceAccount": source_account_id,
                "destinationAccount": destination_account_id,
                "amount": amount,
                "narration": narration,
                "idempotencyKey": idempotency_key,
            },
        }
        
    def extract_biller_products(self, payload: Dict[str, Any]) -> list[Dict[str, Any]]:
        data = payload.get("data", [])
        if isinstance(data, dict):
            for key in ("products", "items", "billers"):
                nested = data.get(key)
                if isinstance(nested, list):
                    return nested
            return [data]
        if isinstance(data, list):
            return data
        return []

    async def list_billers(self, *, category: str) -> Dict[str, Any]:
        category_slug = self._normalize_slug(category)
        if category_slug == "electricity":
            response = await self.list_electricity_discos()
            data = response.get("data", [])
            billers = []
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    disco_id = str(item.get("id") or item.get("disco") or item.get("code") or "").strip()
                    name = str(item.get("name") or item.get("discoName") or disco_id).strip()
                    if not disco_id:
                        continue
                    billers.append(
                        {
                            "id": disco_id,
                            "name": name,
                            "type": "electricity",
                            "options": self._electricity_meter_options(),
                        }
                    )
            response["data"] = billers
            return response
        return {
            "code": "00",
            "description": "Success",
            "data": self._static_billers_for_category(category_slug),
        }

    async def list_biller_products(self, *, biller_id: str) -> Dict[str, Any]:
        biller_slug = self._normalize_slug(biller_id)
        if self._is_electricity_meter_type(biller_slug):
            return {
                "code": "00",
                "description": "Success",
                "data": self._electricity_meter_options(),
            }
        if self._is_cable_type(biller_slug):
            return await self.list_cabletv_plans(cable_tv_type=biller_slug)
        if self._is_telco(biller_slug):
            return await self.list_data_plans(telco=biller_slug)
        return await self._request_with_candidates(
            "GET",
            (
                f"/v1/billers/{biller_id}/products",
                f"/v1/bill-payments/billers/{biller_id}/products",
                f"/v1/billers/{biller_id}/items",
            ),
        )

    async def validate_bill_customer(self, *, provider_slug: str, customer_number: str) -> Dict[str, Any]:
        provider_slug_normalized = self._normalize_slug(provider_slug)
        if provider_slug_normalized in {"prepaid", "postpaid"}:
            return {
                "code": "00",
                "description": "Success",
                "data": customer_number,
            }
        if self._is_cable_type(provider_slug_normalized):
            return await self.lookup_cabletv_customer(
                cable_tv_type=provider_slug_normalized,
                customer_id=customer_number,
            )
        if self._is_telco(provider_slug_normalized):
            return {
                "code": "00",
                "description": "Success",
                "data": customer_number,
            }
        payload = {
            "provider": provider_slug,
            "providerSlug": provider_slug,
            "customerNumber": customer_number,
            "customer_number": customer_number,
        }
        return await self._request_with_candidates(
            "POST",
            (
                "/v1/bill-payments/validate",
                f"/v1/bill-payments/validate/{provider_slug}",
                f"/v1/billers/{provider_slug}/validate",
            ),
            payload=payload,
        )

    async def initiate_bill_payment(
        self,
        *,
        bill_type: str,
        attributes: Dict[str, Any],
        account_id: str,
        reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "billType": bill_type,
            "type": bill_type,
            "attributes": attributes,
            "accountId": account_id,
            "reference": reference,
            "merchantTxRef": reference,
        }
        bill_type_slug = self._normalize_slug(bill_type)
        if bill_type_slug == "electricity":
            return await self.vend_electricity(
                disco=str(attributes.get("disco") or attributes.get("provider") or ""),
                merchant_tx_ref=reference or attributes.get("reference") or attributes.get("merchantTxRef") or "",
                payer_name=str(attributes.get("payerName") or attributes.get("senderName") or "Nomba User"),
                amount=int(attributes.get("amount") or 0),
                customer_id=str(attributes.get("customerId") or attributes.get("customerNumber") or attributes.get("meterAccountNumber") or ""),
                meter_type=str(attributes.get("meterType") or "prepaid"),
            )
        if bill_type_slug == "airtime":
            return await self.vend_airtime(
                amount=int(attributes.get("amount") or 0),
                phone_number=str(attributes.get("phoneNumber") or attributes.get("customerNumber") or ""),
                network=str(attributes.get("network") or attributes.get("provider") or ""),
                merchant_tx_ref=reference or attributes.get("reference") or attributes.get("merchantTxRef") or "",
                sender_name=str(attributes.get("senderName") or attributes.get("payerName") or ""),
            )
        if bill_type_slug == "data":
            return await self.vend_data(
                amount=int(attributes.get("amount") or 0),
                phone_number=str(attributes.get("phoneNumber") or attributes.get("customerNumber") or ""),
                network=str(attributes.get("network") or attributes.get("provider") or ""),
                merchant_tx_ref=reference or attributes.get("reference") or attributes.get("merchantTxRef") or "",
                sender_name=str(attributes.get("senderName") or attributes.get("payerName") or ""),
            )
        if bill_type_slug in {"television", "cabletv", "cable"}:
            return await self.subscribe_cabletv(
                cable_tv_type=str(attributes.get("cableTvType") or attributes.get("provider") or ""),
                merchant_tx_ref=reference or attributes.get("reference") or attributes.get("merchantTxRef") or "",
                payer_name=str(attributes.get("payerName") or attributes.get("senderName") or "Nomba User"),
                amount=int(attributes.get("amount") or 0),
                customer_id=str(attributes.get("customerId") or attributes.get("customerNumber") or ""),
            )
        return await self._request_with_candidates(
            "POST",
            (
                "/v1/bill-payments/pay",
                "/v1/bill-payments/initiate",
                "/v1/payments/bills",
            ),
            payload=payload,
        )


nomba_service = NombaService()
