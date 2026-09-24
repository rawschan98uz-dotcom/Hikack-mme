import os, sys, django
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from org.models import Company, Branch, Room
from accounts.models import User
from crm.models import Course, Group, Student, Lead, AttendanceRecord
from finance.models import Payment, PayrollPayment, SalarySetting

company = Company.objects.first()
print('=' * 60)
print('РЕЗУЛЬТАТЫ ВЕРИФИКАЦИИ ДАННЫХ В HIJACK LMS')
print('=' * 60)
print(f'Компания: {company.name}')
print(f'Всего студентов: {Student.objects.filter(company=company).count()}')
print(f'Студентов со статусом STUDYING (1, Обучается): {Student.objects.filter(company=company, status=Student.Status.STUDYING).count()}')

debtors = Student.objects.filter(company=company, paid_this_month=False)
print(f'Должников (paid_this_month=False): {debtors.count()}')
for s in debtors:
    print(f'   -> Должник: {s.full_name} | Баланс: {s.balance:,} UZS | Группа: {s.group.name if s.group else "Без группы"}')

print(f'\nВсего лидов: {Lead.objects.filter(company=company).count()}')
for stage in ['trial_booked', 'attended', 'rejected']:
    cnt = Lead.objects.filter(company=company, stage=stage).count()
    print(f'   -> Этап {stage}: {cnt} лидов')

print(f'\nУчителей: {User.objects.filter(company=company, user_type=User.UserType.TEACHER).count()}')
for t in User.objects.filter(company=company, user_type=User.UserType.TEACHER):
    sal = SalarySetting.objects.filter(teacher=t).first()
    pay = PayrollPayment.objects.filter(teacher=t).first()
    print(f'   -> Учитель: {t.display_name()} | Оклад: {sal.amount:,} UZS | Выплачено: {pay.amount:,} UZS')

print(f'\nАудиторий: {Room.objects.filter(branch__company=company).count()}')
for r in Room.objects.filter(branch__company=company):
    print(f'   -> {r.name} (вместимость: {r.capacity})')

print(f'\nГрупп: {Group.objects.filter(company=company).count()}')
for g in Group.objects.filter(company=company):
    print(f'   -> Группа: {g.name} | Студентов: {g.students.count()} | Преподаватель: {g.teacher.display_name()} | Кабинет: {g.room.name}')

print(f'\nПлатежей студентов: {Payment.objects.filter(company=company).count()}')
print(f'Записей в журнале посещаемости: {AttendanceRecord.objects.filter(company=company).count()}')

print('\n' + '=' * 60)
print('ПРОВЕРКА СВЯЗОК РОДСТВЕННИКОВ')
print('=' * 60)
karimovs = Student.objects.filter(company=company, phone='901112233')
print(f'1. Семья Каримовых (общий номер 901112233, адрес Чиланзар-9): {[s.full_name for s in karimovs]}')

umarovs = Student.objects.filter(company=company, phone='935551122')
print(f'2. Семья Умаровых (общий номер 935551122, адрес Юнусабад-11): {[s.full_name for s in umarovs]}')

s_aliev = Student.objects.filter(company=company, phone='946663344').first()
l_alieva = Lead.objects.filter(company=company, phone='946663344').first()
print(f'3. Семья Алиевых (общий номер 946663344): Студент: {s_aliev.full_name} | Лид: {l_alieva.full_name} (этап {l_alieva.stage})')

rakhimov_leads = Lead.objects.filter(company=company, phone='978884455')
print(f'4. Лиды-родственники Рахимовы (общий номер 978884455): {[(l.full_name, l.stage) for l in rakhimov_leads]}')

print('\n' + '=' * 60)
print('ПРОВЕРКА ТЁЗОК И ОДНОФАМИЛЬЦЕВ')
print('=' * 60)
jasurs = Student.objects.filter(company=company, first_name='Жасур', last_name='Юлдашев')
print(f'1. Полные тёзки Жасур Юлдашев (разные ID и номера):')
for j in jasurs:
    print(f'   -> ID {j.id}: {j.full_name}, Тел: {j.phone}, Группа: {j.group.name if j.group else None}')

print(f'2. Однофамильцы Каримовы из разных семей:')
for k in Student.objects.filter(company=company, last_name='Каримов'):
    print(f'   -> ID {k.id}: {k.full_name}, Тел: {k.phone}, Адрес: {k.address}')
for k in Student.objects.filter(company=company, last_name='Каримова'):
    print(f'   -> ID {k.id}: {k.full_name}, Тел: {k.phone}, Адрес: {k.address}')

st_makhmudov = Student.objects.filter(company=company, first_name='Алишер', last_name='Махмудов').first()
lead_makhmudov = Lead.objects.filter(company=company, first_name='Алишер', last_name='Махмудов').first()
print(f'3. Студент и Лид с одинаковым именем Алишер Махмудов (разные номера):')
print(f'   -> Студент: {st_makhmudov.full_name}, Тел: {st_makhmudov.phone}, Группа: {st_makhmudov.group.name}')
print(f'   -> Лид: {lead_makhmudov.full_name}, Тел: {lead_makhmudov.phone}, Этап: {lead_makhmudov.stage}, Комментарий: {lead_makhmudov.comment}')
print('=' * 60)
