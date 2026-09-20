from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # --- Store Front (হোমপেজ / প্রোডাক্টস) ---
    path('', views.product_list, name='product_list'),
    path('products/', views.product_list, name='product_list_alt'),

    # --- Authentication (লগইন এবং রেজিস্ট্রেশন) ---
    path('login/', views.user_login, name='login'),
    path('register/', views.user_register, name='register'),
    path('logout/', views.user_logout, name='logout'),

    # --- Password Reset ---
    # আপনার urls.py ফাইলের Password Reset সেকশনের প্রথম লাইনটা মুছে এটা বসান:
    path('reset_password/', auth_views.PasswordResetView.as_view(
        template_name="store/password_reset.html",
        html_email_template_name="store/password_reset_email.html"
        # <-- এই ম্যাজিক লাইনটা ওয়ার্ল্ড ক্লাস ইমেইল পাঠাবে!
    ), name="reset_password"),
    path('reset_password_sent/', auth_views.PasswordResetDoneView.as_view(template_name="store/password_reset_sent.html"), name="password_reset_done"),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name="store/password_reset_form.html"), name="password_reset_confirm"),
    path('reset_password_complete/', auth_views.PasswordResetCompleteView.as_view(template_name="store/password_reset_done.html"), name="password_reset_complete"),

    # --- Store / Products ---
    path('category/<slug:category_slug>/', views.product_list, name='product_list_by_category'),
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),
    path('search-products/', views.search_products, name='search_products'),

    # --- Cart ---
    path('cart/', views.cart_summary, name='cart_summary'),
    path('cart/add/<int:product_id>/', views.cart_add, name='cart_add'),
    path('cart/add-bundle/<int:product_id>/', views.cart_add_bundle, name='cart_add_bundle'),
    path('cart/decrement/<int:product_id>/', views.cart_decrement, name='cart_decrement'),
    path('cart/remove/<int:product_id>/', views.cart_remove, name='cart_remove'),

    # --- Wishlist ---
    path('wishlist/', views.wishlist_view, name='wishlist'),
    path('wishlist/toggle/<int:product_id>/', views.toggle_wishlist, name='toggle_wishlist'),

    # --- Checkout & Orders ---
    path('checkout/', views.checkout, name='checkout'),
    path('track-order/', views.track_order, name='track_order'),
    path('order-history/', views.order_history, name='order_history'),
    path('invoice/<int:order_id>/', views.generate_invoice, name='generate_invoice'),

    # --- User Profile ---
    path('profile/', views.user_profile, name='profile'),
    path('address/', views.user_address, name='user_address'),
    path('apply-coupon/', views.apply_coupon, name='apply_coupon'),
    path('submit-review/<int:product_id>/', views.submit_review, name='submit_review'),
    path('search/', views.search_products, name='search_api'),
]