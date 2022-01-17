from decimal import Decimal, ROUND_DOWN

def round_to_increment(amount, precision):
    return float(Decimal(str(amount)).quantize(Decimal(precision), rounding=ROUND_DOWN))