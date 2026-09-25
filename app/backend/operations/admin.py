from django.contrib import admin

from operations.models import (
    ArchivedPerson,
    AuditLogRecord,
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
    ArchivedPerson, SmsLog, CallLog, PlatformPayment,
    AuditLogRecord,
):
    admin.site.register(model)

