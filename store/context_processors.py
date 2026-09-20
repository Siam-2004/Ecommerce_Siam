from store.cart import Cart
from store.models import StoreSetting, Category


def store_context(request):
    """
    Global context processor providing store-wide settings, cart state,
    dynamic categories, and free shipping calculations across all templates.
    """
    cart = Cart(request)

    # Ensure at least one StoreSetting row exists
    try:
        store_setting = StoreSetting.objects.first()
        if not store_setting:
            store_setting = StoreSetting.objects.create(
                is_free_shipping_active=True,
                free_shipping_threshold=3000.00
            )
    except Exception:
        store_setting = None

    is_free_shipping_active = store_setting.is_free_shipping_active if store_setting else True
    free_shipping_threshold = float(store_setting.free_shipping_threshold) if store_setting else 3000.00

    try:
        all_categories = Category.objects.all()
    except Exception:
        all_categories = []

    return {
        'cart': cart,
        'cart_count': len(cart),
        'store_setting': store_setting,
        'is_free_shipping_active': is_free_shipping_active,
        'free_shipping_threshold': free_shipping_threshold,
        'all_categories': all_categories,
        'categories': all_categories,
    }

