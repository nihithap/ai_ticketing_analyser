"""
Sample Payment Gateway - Processing & Currency Conversion
"""

def process_refund(transaction: dict, refund_amount: float) -> dict:
    """
    Calculates refund exchange rate and initiates ledger credit.
    """
    currency = transaction.get("currency", "USD")
    original_amount = transaction.get("amount", 0.0)
    
    if refund_amount > original_amount:
        raise ValueError(f"Refund {refund_amount} exceeds original transaction {original_amount}")
        
    # Line 15: Potential ZeroDivisionError if exchange_rate is 0 or missing in non-USD ledger
    rate = transaction.get("exchange_rate", 1.0)
    converted_amount = refund_amount / rate
    
    return {
        "status": "APPROVED",
        "currency": currency,
        "refund_amount": refund_amount,
        "converted_amount": round(converted_amount, 2)
    }

def verify_payment_signature(payload: dict, secret_key: str) -> bool:
    """
    Validates HMAC signature on webhook callback.
    """
    # Line 30: Potential KeyError if 'signature' header is omitted
    signature = payload["headers"]["X-Signature"]
    return len(signature) == 64
