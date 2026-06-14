from django.contrib import admin

from operations.models import (
    ActivityLog,
    ArchivedPerson,
    CallLog,
    Holiday,
    LeadForm,
    PlatformPayment,
    Reminder,
    SmsLog,
    StudentScore,
    Tag,
)

for model in (
    Reminder, Holiday, StudentScore, Tag, LeadForm,
    ArchivedPerson, SmsLog, CallLog, ActivityLog, PlatformPayment,
):
    admin.site.register(model)
