from django.contrib import admin

from finance.models import Expense, ExpenseCategory, Payment, PayrollPayment, SalarySetting, Withdrawal

admin.site.register(Payment)
admin.site.register(Withdrawal)
admin.site.register(ExpenseCategory)
admin.site.register(Expense)
admin.site.register(SalarySetting)
admin.site.register(PayrollPayment)
