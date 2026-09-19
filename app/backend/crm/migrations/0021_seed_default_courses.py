from django.db import migrations

DEFAULT_COURSES = [
    ('Английский', 'ENG', 600000),
    ('Математика', 'MATH', 500000),
    ('Немецкий', 'GER', 600000),
    ('Китайский', 'CHN', 650000),
]

def seed_courses(apps, schema_editor):
    Company = apps.get_model('org', 'Company')
    Course = apps.get_model('crm', 'Course')

    for company in Company.objects.all():
        for name, code, price in DEFAULT_COURSES:
            if not Course.objects.filter(company=company, name=name).exists():
                Course.objects.create(
                    company=company,
                    name=name,
                    code=code,
                    price=price,
                    lesson_duration=90,
                    course_duration=12,
                    description=f'Курс {name}',
                )

def reverse_func(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0020_lead_branch_lead_course_lead_source_alter_lead_stage'),
        ('org', '0005_company_click_merchant_id_company_click_secret_key_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_courses, reverse_func),
    ]
