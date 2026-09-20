from decimal import Decimal
from store.models import Product


class Cart:
    def __init__(self, request):
        self.request = request
        self.session = request.session
        cart = self.session.get('session_key')
        if 'session_key' not in request.session:
            cart = self.session['session_key'] = {}
        self.cart = cart

    def sync_abandoned_cart(self):
        try:
            if not hasattr(self, 'request') or not self.request.user.is_authenticated:
                return

            from store.models import AbandonedCart
            user = self.request.user
            total = self.get_total_price()

            serializable_cart = {}
            for item_id, item_info in self.cart.items():
                if isinstance(item_info, dict) and 'product_id' in item_info:
                    serializable_cart[item_id] = {
                        'product_id': item_info.get('product_id'),
                        'price': str(item_info.get('price')),
                        'quantity': item_info.get('quantity'),
                        'size': item_info.get('size', '')
                    }

            if len(serializable_cart) > 0:
                abandoned_cart, created = AbandonedCart.objects.get_or_create(
                    user=user,
                    is_recovered=False,
                    defaults={
                        'email': user.email,
                        'phone': getattr(user, 'phone_number', '') or '',
                        'cart_data': serializable_cart,
                        'total_price': total
                    }
                )
                if not created:
                    abandoned_cart.cart_data = serializable_cart
                    abandoned_cart.total_price = total
                    abandoned_cart.email = user.email
                    if abandoned_cart.is_email_sent:
                        abandoned_cart.is_email_sent = False
                        abandoned_cart.email_sent_at = None
                    abandoned_cart.save()
            else:
                AbandonedCart.objects.filter(user=user, is_recovered=False, is_email_sent=False).delete()
        except Exception as e:
            print(f"Sync abandoned cart error: {e}")

    def add(self, product, quantity=1, size='', override_quantity=False):
        item_id = f"{product.id}_{size}" if size else str(product.id)

        # === NEW: চেক করা হচ্ছে প্রোডাক্টের ডিসকাউন্ট প্রাইস আছে কি না ===
        actual_price = product.discount_price if product.discount_price and product.discount_price > 0 else product.price

        if item_id not in self.cart:
            self.cart[item_id] = {
                'product_id': str(product.id),
                'price': str(actual_price),  # ডিসকাউন্ট থাকলে সেটা, না থাকলে রেগুলার প্রাইস বসবে
                'quantity': 0,
                'size': size
            }

        if override_quantity:
            self.cart[item_id]['quantity'] = int(quantity)
        else:
            self.cart[item_id]['quantity'] += int(quantity)

        self.session.modified = True
        self.sync_abandoned_cart()

    def remove(self, product, size=''):
        item_id = f"{product.id}_{size}" if size else str(product.id)
        if item_id in self.cart:
            del self.cart[item_id]
            self.session.modified = True
            self.sync_abandoned_cart()

    def clear(self):
        self.session['session_key'] = {}
        self.session.modified = True
        self.sync_abandoned_cart()

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values() if isinstance(item, dict) and 'quantity' in item)

    def __iter__(self):
        valid_items = {k: v for k, v in self.cart.items() if isinstance(v, dict) and 'product_id' in v}

        product_ids = [item['product_id'] for item in valid_items.values()]
        products = Product.objects.filter(id__in=product_ids)

        product_dict = {str(p.id): p for p in products}

        cart = valid_items.copy()

        for item_id, item_data in cart.items():
            product = product_dict.get(item_data['product_id'])
            if product:
                item_data['product'] = product
                item_data['price'] = float(item_data['price'])
                item_data['total_price'] = item_data['price'] * item_data['quantity']
                yield item_data

    def get_total_price(self):
        return sum(float(item['price']) * item['quantity'] for item in self.cart.values() if
                   isinstance(item, dict) and 'price' in item and 'quantity' in item)