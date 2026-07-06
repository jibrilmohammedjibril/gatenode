# Wallet Bank Flow

Use these endpoints in this order:

1. Load live bank list
2. Resolve account name with Nomba
3. Submit transfer-out

All calls require an authenticated resident Bearer token.

## 1) Get live bank list

`GET /wallet/banks?q=first`

Use this endpoint to populate the bank picker in the transfer-out form.

### Query params
- `q` optional search string for bank name or bank code

### Response

```json
{
  "banks": [
    {
      "bankName": "First Bank of Nigeria",
      "bankCode": "011"
    }
  ],
  "count": 1,
  "source": "nomba"
}
```

### Frontend behavior
- Load once when the transfer screen opens
- Allow search/filter with `q`
- Store the selected `bankName` and `bankCode`
- Use `bankCode`, not display text, for downstream requests

## 2) Resolve bank account name

`POST /wallet/resolve-bank-account`

Use this endpoint after the user enters an account number and selects a bank.

### Request body

```json
{
  "bankName": "First Bank",
  "bankCode": "011",
  "accountNumber": "0123456789",
  "accountName": "Jide Adeyemi"
}
```

### Response

```json
{
  "bankName": "First Bank",
  "bankCode": "011",
  "accountNumber": "0123456789",
  "accountName": "Jide Adeyemi",
  "verified": true,
  "matchesProvidedAccountName": true,
  "source": "nomba"
}
```

### Frontend behavior
- Call this on blur, on a verify action, or before enabling submit
- Show the returned `accountName` clearly
- If `matchesProvidedAccountName` is `false`, block submission and ask the user to confirm the details
- If the API errors, show a retryable validation message

## 3) Transfer out

`POST /wallet/transfer-out`

Use this to send money from the resident wallet to a Nigerian bank account.

### Request body

```json
{
  "bankName": "First Bank",
  "bankCode": "011",
  "accountNumber": "0123456789",
  "accountName": "Jide Adeyemi",
  "amount": 5000,
  "transactionPin": "1234",
  "narration": "Wallet withdrawal"
}
```

### Response

```json
{
  "status": "pending",
  "reference": "WDR-ABC123DEF456",
  "amount": 5000,
  "bankName": "First Bank",
  "accountNumber": "0123456789",
  "accountName": "Jide Adeyemi",
  "providerReference": "NB-TRANS-12345",
  "message": "Transfer queued successfully"
}
```

### Possible statuses
- `pending`
- `success`
- `failed`

### Frontend behavior
- Require transaction PIN before submit
- Require a successful account lookup before submit
- Disable submit if lookup name does not match the entered recipient
- Show pending state if transfer is queued
- Refresh transaction history after submission
- If status is pending, let transaction history and webhook reconciliation finalize the result

## Suggested flow

1. Open transfer screen
2. Call `GET /wallet/banks`
3. User selects bank
4. User enters account number
5. Call `POST /wallet/resolve-bank-account`
6. Show resolved name
7. User enters amount and PIN
8. Call `POST /wallet/transfer-out`
9. Show success, pending, or failure state
10. Refresh wallet transactions

## Error handling

- `400` means the form data is invalid
- `409` means wallet is not ready or setup is required
- `502` means Nomba lookup or transfer provider failed
- If lookup fails, allow retry
- If transfer-out returns `pending`, do not treat it as a final failure
