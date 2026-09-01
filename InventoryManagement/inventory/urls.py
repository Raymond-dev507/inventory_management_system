from django.contrib import admin
from django.urls import path, include
from . import views
from . import reports
from . import ai_report
from . import user
from . import Telegram
urlpatterns = [
    path("test-email-connection/",views.test_email_connection),
    path("", views.dashboard, name="dashboard"),
    path('category',views.category,name='category'),
    path('all_categories',views.all_categories,name='all_categories'),
    path('remove_category<int:id>',views.remove_category,name='remove_category'),
    path('edit_category<int:id>',views.edit_category,name='edit_category'),
    path('update_category<int:id>',views.update_category,name='update_category'),


    path('supplier',views.supplier,name='supplier'),
    path('all_supplier',views.all_supplier,name='all_supplier'),
    path("edit_supplier<int:id>", views.edit_supplier, name="edit_supplier"),
    path("remove_supplier<int:id>", views.remove_supplier, name="remove_supplier"),
    path('update_supplier<int:id>',views.update_supplier,name='update_supplier'),

    path('product',views.product,name='product'),
    path('all_product',views.all_product,name='all_product'),
    path('edit_product<int:id>',views.edit_product,name='edit_product'),
    path('remove_product<int:id>',views.remove_product,name='remove_product'),
    path('update_product<int:id>',views.update_product,name='update_product'),

    path('stock',views.add_stock,name='stock'),
    path("stock-list", views.stock_list, name="stock_list"),


    path('stock_out',views.stock_out,name='stock_out'),
    path('stock_out_list',views.stock_out_list,name='stock_out_list'),


    path('create_sale',views.create_sale,name='create_sale'),
    path('remove-from-cart<int:product_id>',views.remove_from_cart,name='remove_from_cart'),
    path('increase_quantity<int:product_id>',views.increase_quantity,name='increase_quantity'),
    path('decrease_quantity<int:product_id>',views.decrease_quantity,name='decrease_quantity'),
    path('clear_cart',views.clear_cart,name='clear_cart'),


    path('complete_sale',views.complete_sale,name='complete_sale'),
    path('sale-receipt<int:sale_id>',views.sale_receipt,name='sale_receipt'),


    path('global_search',views.global_search,name='global_search'),

    path("sale_records",views.sale_records,name="sale_records"),
    path("sale-records<int:sale_id>/",views.sale_detail,name="sale_detail"),

    path('reports',reports.reports,name='reports'),
    path('export_sales_pdf',reports.export_sales_pdf,name='export_sales_pdf'),

    path('ai-report',ai_report.generate_ai_report,name='ai_report'),

    path("test-telegram",ai_report.test_telegram,name="test_telegram"),

    path("telegram/webhook", Telegram.telegram_webhook, name="telegram_webhook"),

    path("users", user.users, name="users"),
    path("add_users", user.add_user, name="add_user"),
    path("edit-user<int:user_id>/",user.edit_user,name="edit_user"),
    path("deactivate_user<int:user_id>/", user.deactivate_user, name="deactivate_user"),
    path("delete_user<int:user_id>/", user.delete_user, name="delete_user"),
    path('restore_user<int:user_id>/',user.restore_user,name="restore_user"),

    path("settings",user.settings_view,name="settings"),


]