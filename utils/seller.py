def get_seller_share(total_sales: int, is_verified: bool):
    if is_verified:
        return 0.85, "Notezy Elite"

    if total_sales >= 100:
        return 0.80, "Top Seller"

    if total_sales >= 25:
        return 0.75, "Rising Seller"

    return 0.70, "New Seller"