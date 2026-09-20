from django.db import models
from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.core.validators import MinValueValidator, MaxValueValidator

User = get_user_model()


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True)

    class Meta:
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    logo = models.ImageField(upload_to='brands/', blank=True)

    def __str__(self):
        return self.name


class Size(models.Model):
    name = models.CharField(max_length=20, unique=True, help_text="যেমন: S, M, L, XL অথবা 40, 41, 42")

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stock = models.IntegerField()
    is_available = models.BooleanField(default=True)

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')

    sizes = models.ManyToManyField(Size, blank=True, related_name='products')

    frequently_bought_together = models.ManyToManyField('self', blank=True, symmetrical=False,
                                                        help_text="এই প্রোডাক্টের সাথে কাস্টমাররা আর কী কী কিনতে পারে (যেমন: জার্সির সাথে প্যান্ট)")

    # === NEW: বান্ডেল ডিসকাউন্ট পার্সেন্টেজ (অ্যাডমিন কন্ট্রোল করবে) ===
    bundle_discount = models.IntegerField(default=0,
                                          help_text="বান্ডেল হিসেবে কিনলে কত % ছাড় দিতে চান? (যেমন: 10, 15)")
    # ========================================================

    image = models.ImageField(upload_to='products/')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('product_detail', args=[self.slug])

    def get_discount_percent(self):
        if self.discount_price and self.price and self.price > self.discount_price and self.price > 0:
            percent = ((self.price - self.discount_price) / self.price) * 100
            return int(percent)
        return 0

    def get_average_rating(self):
        avg = self.reviews.aggregate(models.Avg('rating'))['rating__avg']
        if avg is None:
            return 0
        return round(avg, 1)

    def get_review_count(self):
        return self.reviews.count()


class Order(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='orders')

    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Processing', 'Processing'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
    )
    PAYMENT_CHOICES = (
        ('Cash on Delivery', 'Cash on Delivery'),
        ('bKash', 'bKash'),
        ('Nagad', 'Nagad'),
    )

    full_name = models.CharField(max_length=250)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20)
    address = models.TextField()

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='Cash on Delivery')
    sender_number = models.CharField(max_length=20, blank=True, null=True, help_text="যে নম্বর থেকে টাকা পাঠানো হয়েছে")
    trx_id = models.CharField(max_length=100, blank=True, null=True, help_text="বিকাশ/নগদ ট্রানজেকশন আইডি")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order {self.id} - {self.full_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    size = models.CharField(max_length=50, blank=True, null=True)

    @property
    def total_price(self):
        return self.price * self.quantity

    def __str__(self):
        return f"Item {self.id} - {self.product.name} (x{self.quantity})"


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.first_name} - {self.product.name}"


class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True, help_text="কুপন কোড (যেমন: WELCOME20)")
    discount_percentage = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="ডিসকাউন্টের পরিমাণ শতকরা (%) হিসেবে"
    )
    is_active = models.BooleanField(default=True, help_text="কুপনটি অ্যাক্টিভ রাখতে টিক দিন")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


# --- Product Review & Rating Model ---
class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.IntegerField(
        default=5,
        choices=[(i, str(i)) for i in range(1, 6)],
        help_text="১ থেকে ৫ এর মধ্যে রেটিং"
    )
    comment = models.TextField(blank=True, null=True, help_text="কাস্টমারের মতামত")

    # === NEW: কাস্টমারের ছবি আপলোডের ফিল্ড ===
    image = models.ImageField(upload_to='review_images/', blank=True, null=True, help_text="কাস্টমারের দেওয়া আসল ছবি")
    # =======================================

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.first_name} - {self.product.name} ({self.rating} Star)"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_gallery/', help_text="প্রোডাক্টের অন্যান্য ছবি আপলোড করুন")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.product.name}"


class FlashSale(models.Model):
    title = models.CharField(max_length=200, default="মেগা ফ্ল্যাশ সেল!")
    description = models.CharField(max_length=500, default="টপ প্রোডাক্টগুলোতে স্পেশাল ডিসকাউন্ট। অফার শেষ হতে বাকি:")
    end_time = models.DateTimeField(help_text="ফ্ল্যাশ সেল কখন শেষ হবে তার তারিখ ও সময় দিন")
    is_active = models.BooleanField(default=False, help_text="টিক দিলে ওয়েবসাইটে ব্যানার শো করবে")
    products = models.ManyToManyField(Product, blank=True, related_name='flash_sales',
                                      help_text="এই সেলে যে প্রোডাক্টগুলো রাখতে চান তা সিলেক্ট করুন")

    def __str__(self):
        return self.title


class StoreSetting(models.Model):
    is_free_shipping_active = models.BooleanField(default=True, help_text="ফ্রি শিপিং অফার চালু রাখতে টিক দিন")
    free_shipping_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=3000.00,
                                                  help_text="কত টাকার শপিং করলে ফ্রি ডেলিভারি পাবে?")
    
    # Abandoned Cart Recovery Settings
    abandoned_cart_active = models.BooleanField(default=True, verbose_name="অ্যাবানডনড কার্ট রিকভারি চালু রাখুন",
                                                help_text="কাস্টমার কার্টে পণ্য রেখে চলে গেলে রিকভারি ইমেইল পাঠাতে টিক দিন")
    abandoned_cart_wait_hours = models.PositiveIntegerField(default=2, verbose_name="কত ঘণ্টা পর ইমেইল যাবে",
                                                           help_text="কার্ট রেখে যাওয়ার কত ঘণ্টা পর ইমেইল পাঠাবে (ডিফল্ট: ২ ঘণ্টা)")
    abandoned_cart_discount_percent = models.PositiveIntegerField(default=5, verbose_name="রিকভারি ডিসকাউন্ট (%)",
                                                                 help_text="ইমেইলে কত শতাংশ ডিসকাউন্টের কুপন দেওয়া হবে (০ দিলে ডিসকাউন্ট ছাড়া শুধু রিমাইন্ডার যাবে)")
    abandoned_cart_email_subject = models.CharField(max_length=255, 
                                                    default="আপনার কার্টের পছন্দের পণ্যগুলো আপনার জন্য অপেক্ষা করছে!",
                                                    verbose_name="রিকভারি ইমেইল সাবজেক্ট",
                                                    help_text="কাস্টমার যে সাবজেক্ট লাইনের ইমেইল পাবে")

    def __str__(self):
        return "Store Settings"


class AbandonedCart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='abandoned_carts')
    email = models.EmailField(blank=True, null=True, verbose_name="ইমেইল")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="ফোন")
    cart_data = models.JSONField(default=dict, verbose_name="কার্ট ডাটা")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="মোট মূল্য")
    coupon_code = models.CharField(max_length=50, blank=True, null=True, verbose_name="কুপন কোড")
    discount_percent = models.PositiveIntegerField(default=0, verbose_name="ডিসকাউন্ট %")
    is_email_sent = models.BooleanField(default=False, verbose_name="ইমেইল পাঠানো হয়েছে?")
    email_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="ইমেইল পাঠানোর সময়")
    is_recovered = models.BooleanField(default=False, verbose_name="রিকভার হয়েছে? (অর্ডার সম্পন্ন)")
    recovered_at = models.DateTimeField(null=True, blank=True, verbose_name="রিকভারির সময়")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="তৈরির সময়")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="সর্বশেষ আপডেট")

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Abandoned Cart"
        verbose_name_plural = "Abandoned Carts"

    def __str__(self):
        customer = self.email or (self.user.email if self.user else f"Guest #{self.id}")
        return f"Cart #{self.id} - {customer} (৳{self.total_price})"

    @property
    def item_count(self):
        if not self.cart_data:
            return 0
        return sum(item.get('quantity', 1) for item in self.cart_data.values() if isinstance(item, dict))