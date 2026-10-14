"""
Sample Billing Engine - Regional Tax & Invoicing
"""

def calculate_regional_tax(subtotal: float, region_code: str, custom_rates: dict = None) -> float:
    """
    Calculates applicable tax rate based on buyer jurisdiction.
    """
    if custom_rates is None:
        custom_rates = {"US-CA": 7.25, "US-NY": 8.0, "EU-DE": 19.0}
        
    # Line 12: Potential KeyError if region_code does not match configured jurisdictions
    tax_percentage = custom_rates[region_code]
    tax_amount = subtotal * (tax_percentage / 100.0)
    
    return round(tax_amount, 2)
