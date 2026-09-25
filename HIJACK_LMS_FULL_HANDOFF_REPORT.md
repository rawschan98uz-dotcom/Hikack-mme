# ПОЛНЫЙ ХЕНДОФ-ОТЧЁТ И ЕДИНЫЙ РЕЕСТР ВСЕХ ОШИБОК (P0 — P4) ДЛЯ HIJACK LMS

> **ИНСТРУКЦИЯ ДЛЯ ПЕРЕДАЧИ В НОВЫЙ ЧАТ**:  
> Скопируйте данный документ целиком в первый промпт нового чата (или прикрепите файлом `HIJACK_LMS_FULL_HANDOFF_REPORT.md`).  
> Документ содержит исчерпывающий перечень **всех обнаруженных ошибок и задач аудита** (от P0 до P4) с явным указанием статуса: **что уже сделано и протестировано** (Блоки 1 и 2 — 100%), а **что ещё предстоит выполнить** (Блоки 3, 4 и Уровень P4).

---

## 1. АРХИТЕКТУРНЫЙ КОНТЕКСТ И ПРАВИЛА ВЛАДЕЛЬЦА

- **Проект**: HiJack LMS — специализированная LMS+CRM платформа для учебных центров (Узбекистан, валюта UZS).
- **Стек**:
  - **Бэкенд**: Python 3.12, Django 5.2, Django REST Framework (DRF), SQLite (разработка) / PostgreSQL (продакшн). Расположение: `app/backend/`. Приложения: `accounts`, `org`, `crm`, `finance`, `operations`, `api`.
  - **Фронтенд**: Vue 3, Vite, Pinia, Vue Router, TailwindCSS. Расположение: `app/frontend/`.
- **Рабочая директория (Workspace)**: `d:\Projects\HiJackLMS` (интерпретатор: `app\backend\.venv\Scripts\python.exe`).
- **Часовой пояс**: Строго **`Asia/Tashkent` (UTC+5)** во всей бизнес-логике, фильтрах дат и времени.
- **Мультиарендность (Multi-tenancy)**: Практически все таблицы изолированы по внешнему ключу `company = ForeignKey('org.Company')`. Изоляция обязательна на уровне всех запросов.

### 10 Непреложных Решений Владельца (НЕ ОСПАРИВАТЬ И НЕ МЕНЯТЬ):
1. **Интеграция с Uzum**: Отложена на будущее, сейчас не реализовывать.
2. **Ключи платёжек (Click, Payme)**: В БД хранятся как есть (тестовые), шифрование в БД сейчас не требуется (только маскирование в API для не-CEO).
3. **Telegram-бот**: Отдельная задача в бэклоге, текущие вызовы экранированы безопасными блоками `try-except`.
4. **Часовой пояс**: Всегда `Asia/Tashkent` (UTC+5).
5. **`Company.balance_mode`**: Признано устаревшим и **полностью удалено из модели Company в Блоке 2** (в ответах API сохраняется заглушка `balance_mode: 1` для совместимости со строгими типами Vue/TS).
6. **Членство студента в группе**: Источником истины является **FK `Student.group`**. Таблица `GroupEnrollment` — теневой журнал истории перемещений.
7. **Редактирование профиля**: Пользователь может менять только свой телефон и пароль (с обязательной проверкой старого пароля). Своё имя, фамилию, роль, ставку менять запрещено (только CEO/Admin). Пользователь **никогда не может удалить свой собственный аккаунт**.
8. **Флаг `paid_this_month`**: Вспомогательный флаг, реальный статус должника рассчитывается на лету (`today > next_due`).
9. **Формула `payment_offset` при разморозке**: Гасит **только реально потреблённые месяцы** студента:
   $$\text{offset} = \min(\text{всего\_оплачено\_месяцев},\; \text{потреблённых\_месяцев\_до\_заморозки})$$
   Предоплаченные месяцы при разморозке ни в коем случае не стираются!
10. **Политика удаления**: Филиалы защищаются `PROTECT` от случайного сноса вместе со студентами и группами. Студенты архивируются (`status = LEFT`), а не удаляются физически.

---

## 2. СВОДНЫЙ РЕЕСТР ВСЕХ ОШИБОК И ЗАДАЧ (P0 — P4)

| № | ID в аудите | Приоритет | Краткое описание дефекта | Статус | Где находится / Что сделано |
|---|---|---|---|---|---|
| 1 | **A1 / #1** | **P0 (Безопасность)** | Анонимные запросы проходили `RbacPermission` (`return True`) + обход через `@permission_classes([IsAuthenticated])` | **СДЕЛАНО ✅** | `api/permissions.py`, очищены оверрайды во всех views |
| 2 | **A3** | **P0 (Безопасность)** | Неизвестный маршрут API открыт всем (дефолт `PERM_DASHBOARD_VIEW`) | **СДЕЛАНО ✅** | `accounts/rbac.py` (`PERM_DENIED`), `api/rbac_routes.py` (закрыт дефолт, роут `expense_types/<id>`) |
| 3 | **A2 / #19** | **P0 (Безопасность)** | Студент и staff без роли получали роль `ADMINISTRATOR` (эскалация прав) | **СДЕЛАНО ✅** | `accounts/rbac.py` (`ROLE_STUDENT`, дефолт `ROLE_LIMITED_ADMIN`) |
| 4 | **#32** | **P0 (Безопасность)** | Настройки компании и ключи платёжек доступны любому юзеру без маскирования и проверки прав | **СДЕЛАНО ✅** | `views_extended.py` (`company_settings`), маскирование `'***'`, запись только CEO |
| 5 | **#33** | **P0 (Безопасность)** | Изменение/удаление платежа без прав финансов, удаление платежей с возвратами | **СДЕЛАНО ✅** | `views_extended.py` (`payment_detail`), проверка `PERM_FINANCE_WRITE`/CEO, `transaction.atomic()` |
| 6 | **#17,18,34**| **P0 (Безопасность)** | Дефолтный пароль `946263200` при создании сотрудников/учителей, невалидные телефоны | **СДЕЛАНО ✅** | `views_extended.py`, автогенерация паролей, `normalize_phone` |
| 7 | **E2 / #8** | **P0 (Безопасность)** | Пользователь мог изменить своё имя, роль, зарплату через `auth_me` | **СДЕЛАНО ✅** | `views.py` (`auth_me`), запрет смены имени не-CEO (403), проверка `old_password` |
| 8 | **A5 / #2** | **P0 (Безопасность)** | Дефолтные креды CEO опубликованы в `README.md`, небезопасный `SECRET_KEY` | **СДЕЛАНО ✅** | Очищен `README.md`, runtime-проверка в `config/settings.py` |
| 9 | **B1 / #11** | **P1 (Финансы)** | `sync_student_paid_this_month` и выборки платежей считали возвраты как оплату | **СДЕЛАНО ✅** | `crm/services.py`, `views.py`, фильтр `PAYMENT` и `reversals__isnull=True` |
| 10 | **#3, #35** | **P1 (Финансы)** | Выручка в Dashboard и P&L складывала возвраты с оплатами вместо вычитания | **СДЕЛАНО ✅** | `views.py` (`dashboard`), `views_extended.py` (`report_pnl`), чистая выручка `paid - refunded` |
| 11 | **#13, §7.3**| **P1 (Финансы)** | All payments пуст: обработчик GET `/v1/replenishments` лежал после return в `payment_refund` | **СДЕЛАНО ✅** | `views_extended.py` (`replenishments`), GET возвращает список платежей с фильтрами |
| 12 | **B4 / #12** | **P1 (Финансы)** | `payment_offset` при разморозке списывал все оплаченные месяцы (потеря денег) | **СДЕЛАНО ✅** | `crm/models.py` (`frozen_at`), `views.py` (`_calculate_unfreeze_offset`) |
| 13 | **B3 / #5,6,36**| **P1 (Финансы)** | Двойной возврат, возврат больше суммы платежа, баг `months_covered: 0 or 1 -> 1` | **СДЕЛАНО ✅** | `views_extended.py` (`payment_refund`), `select_for_update`, atomic, `months_covered=0` |
| 14 | **B2** | **P1 (Финансы)** | У платежа `Payment` отсутствовала реальная дата платежа `payment_date` | **СДЕЛАНО ✅** | `finance/models.py`, миграция `finance.0007`, поддержка в API и P&L |
| 15 | **A6** | **P1 (Финансы)** | Дубли транзакций вебхуков Click/Payme из-за отсутствия UniqueConstraint | **СДЕЛАНО ✅** | `finance/models.py`, `UniqueConstraint(company, provider, trans_id)`, `student` SET_NULL |
| 16 | **#4, #37** | **P1 (Финансы)** | Приём отрицательных и нулевых сумм в платежах, возвратах, расходах, списаниях | **СДЕЛАНО ✅** | `views_extended.py` (`replenishments`, `refund`, `withdraws`, `expense`), валидация `amount <= 0` |
| 17 | **B7 / #25** | **P1 (Финансы)** | `balance_mode` в `Company` — легаси, засоряющее модели и настройки | **СДЕЛАНО ✅** | `org/models.py`, миграция `org.0006`, сохранена заглушка `1` для фронтенда |
| 18 | **C1 / #20,21**| **P1–P2 (Архитектура)** | `GroupEnrollment` — теневой журнал с дырами синхронизации (Excel, Lead, Archive, Delete) | **СДЕЛАНО ✅** | `crm/signals.py` (post_save Student → `sync_student_group_enrollment`), команда `manage.py sync_enrollments` |
| 19 | **C2 / #22** | **P1–P2 (Архитектура)** | Расписание: хардкод CUSTOM `[0, 2, 4]` и ложные конфликты в `days_overlap()` | **СДЕЛАНО ✅** | `Group.weekdays` (миграция `crm.0030`), `group_weekdays()`/`days_overlap()` в `crm/services.py`, выбор дней в `GroupsView.vue` |
| 20 | **C3** | **P1–P2 (Архитектура)** | Опасные алиасы статусов Student (`Status.DEBTOR = Status.STUDYING` и др.) | **СДЕЛАНО ✅** | Алиасы удалены из `crm/models.py`, вызовы заменены на `STUDYING` |
| 21 | **C4** | **P1–P2 (Архитектура)** | Удаление `Branch` каскадно уничтожает студентов и группы (нужен `PROTECT`) | **СДЕЛАНО ✅** | `PROTECT` в `crm/models.py` (миграция `crm.0030`); API удаления филиала нет, защита на уровне БД/админки |
| 22 | **C5** | **P1–P2 (Архитектура)** | Два параллельных журнала аудита (`ActivityLog` и `AuditLogRecord`) | **СДЕЛАНО ✅** | `ActivityLog` удалён (миграция `operations.0007`), `/history/logs` читает `AuditLogRecord` |
| 23 | **C6** | **P1–P2 (Архитектура)** | Баги в `sync_student_group_enrollment` (LEFT $\to$ FROZEN, потеря при возврате) | **СДЕЛАНО ✅** | `sync_student_group_enrollment` переписана как идемпотентная сверка состояния |
| 24 | **A4 / #10,26,27**| **P2 (Безопасность)** | Tenant isolation в `archive_list`, `company_platform_payments`, расхождения архивации | **СДЕЛАНО ✅** | `archive_list(company_id)`, `company_platform_payments` → 404 для чужой компании; общий `api/archive.py:archive_teacher` |
| 25 | **B5** | **P2 (Бизнес-логика)** | Двухуровневая система скидок: поле `salary_base_amount` в `Payment` | **НЕ СДЕЛАНО ⏳** | Добавить поле в `Payment`, фиксировать снапшот базы ЗП при создании платежа |
| 26 | **B6** | **P2 (Бизнес-логика)** | Неровное деление цены курса на уроки: функция `split_monthly` | **СДЕЛАНО ✅** | `finance/billing.py:split_monthly` (пока не используется — поурочного списания в коде нет) |
| 27 | **D1** | **P2 (Целостность)** | Отсутствие UniqueConstraints: `Branch`, `Tag`, `StudentScore`, `Holiday`, `GroupEnrollment` | **СДЕЛАНО ✅** | Ограничения + дедупликация в миграциях `org.0007`, `operations.0008`, `finance.0008`, `crm.0031`; проверки дублей в API |
| 28 | **D2 / #24** | **P2 (Целостность)** | У модели `Room` нет прямого поля FK `company` (только property через branch) | **СДЕЛАНО ✅** | `Room.company` (миграция `org.0007`), запросы без `branch__company` |
| 29 | **D3** | **P2 (Целостность)** | Неконсистентность `Lead`: `attended_trial` не сбрасывается, `stage=CONVERTED` без Student | **СДЕЛАНО ✅** | `Lead.save()` сбрасывает `attended_trial` при TRIAL_BOOKED; создание лида сразу CONVERTED запрещено |
| 30 | **D4** | **P2 (Целостность)** | `match_student_to_lead` и `enrich_student_from_lead` привязывают конвертированные лиды | **СДЕЛАНО ✅** | `match_student_to_lead` исключает CONVERTED |
| 31 | **D5** | **P2 (Целостность)** | Отсутствие `transaction.atomic()` при массовой посещаемости и автосписаниях | **СДЕЛАНО ✅** | Массовая посещаемость в `transaction.atomic()`; автосписаний в коде нет |
| 32 | **D6** | **P2 (Целостность)** | Валидация `AttendanceRecord.clean()` обходится при `bulk_create` / `update_or_create` | **СДЕЛАНО ✅** | Массовая отметка — только студенты группы; PATCH: проверка группы только при переносе, защита от дубля даты |
| 33 | **D7 / #23** | **P2 (Целостность)** | Статус напоминаний `Reminder.status` устаревает в БД (OVERDUE/TODAY/FUTURE) | **СДЕЛАНО ✅** | `Reminder.current_status` вычисляется на лету; в БД хранится только DONE |
| 34 | **D8** | **P2 (Целостность)** | Перекрывающиеся периоды ставок зарплат преподавателя `SalarySetting` | **СДЕЛАНО ✅** | `finance/salary.py`: запрет пересечений + единое правило старшинства для сводки и выплаты |
| 35 | **D9 / #25** | **P2 (Целостность)** | Неполный охват нормализации телефонов узбекского формата | **СДЕЛАНО ✅** | Импорт из Excel использует общий `normalize_phone` (убирает 998) |
| 36 | **D10 / #24**| **P2 (Целостность)** | Вместимость аудитории `Room.capacity` нигде не валидируется | **СДЕЛАНО ✅** | `crm/services.py:group_capacity_error` — студент, лид→студент, смена аудитории группы |
| 37 | **E1 / #9,14,28,30**| **P2 (RBAC)** | Серверная изоляция данных учителя (учитель видит чужие группы, балансы, ставит оценки) | **СДЕЛАНО ✅** | `api/scope.py:strip_for_teacher`, дашборд без финансов, платежи студента 403, оценки только своим группам |
| 38 | **E3 / #25** | **P2 (RBAC)** | `BRANCH_DIRECTOR` видит данные всех филиалов компании в `_user_branches` | **НЕ СДЕЛАНО ⏳** | Ограничить видимость филиалов в скоупе привязанного филиала |
| 39 | **#29** | **P2 (Надёжность)** | Ошибка 500 в `scores_branch` при нечисловом параметре `?limit=abc` | **СДЕЛАНО ✅** | `limit` защищён try/except, ограничен 1..500 |
| 40 | **Раздел 7 п.11**| **P2 (Удобство)** | Капитализация имён ломает узбекские частицы (`og'li`, `qizi` превращаются в `Og'Li`) | **СДЕЛАНО ✅** | `api/utils.py:capitalize_name`, применяется при импорте студентов |
| 41 | **Раздел 7 п.12**| **P2 (Удобство)** | Дубли категорий расходов (`ExpenseCategory`) | **СДЕЛАНО ✅** | Слияние дублей в миграции `finance.0008`, проверка в API (`name_taken`, работает с кириллицей) |
| 42 | **P4-1 (E4)**| **P4 (Маршруты)** | Удалить неиспользуемые пермишены (`SETTINGS_INTEGRATIONS`, `SETTINGS_GRADE`, `GROUPS_EXPORT`), дубли роутов (`holidayRecalculation`, `reminder/index`, `users/trashed`), дубль `POST ^company/settings$` | **СДЕЛАНО ✅** (2026-09-25) | Дубли роутов удалены, `HolidaysView` ходит на `/holidays`. Пермишены ОСТАВЛЕНЫ — они используются во фронтенде (меню SMS/VoIP/Grade, кнопка экспорта групп). Дубля `company/settings` уже не было |
| 43 | **P4-2 (F1–F6)**| **P4 (Гигиена бэкенда)**| Заменить `unique_together` на `UniqueConstraint`, унифицировать Choices, `Course.course_duration`, `BigIntegerField` для UZS, `Student.save()` | **СДЕЛАНО ✅ кроме F2** (2026-09-25) | F1: UniqueConstraint (+`TeacherBranch`); F3: README; F4: BigIntegerField для всех сумм; F5: verbose_name (месяцы/минуты/UZS); F6: без SELECT при `update_fields` без `status`. Миграции `*_p4_hygiene`. F2 (язык Choices) — не трогали: подписи видны в интерфейсе, решает владелец |
| 44 | **P4-3 (Фронтенд)**| **P4 (Интерфейс)** | 1. Скрыть в UI финансовые разделы, балансы и кнопки удаления для учителей.<br>2. Вычистить обращения к алиасам DEBTOR и TRIAL.<br>3. Сборка `npm run build` и синхронизация `sync-app.ps1`. | **СДЕЛАНО ✅** (2026-09-25) | `StudentsView` (оплаты/даты оплат/кнопки по правам), `DashboardView` (карточки по доступу, без денег у учителя). Алиасов во фронтенде не было. `dist` пересобран; `sync-app.ps1` на этом ПК не используется |

---

## 3. ДЕТАЛЬНЫЙ ОТЧЁТ: ЧТО УЖЕ СДЕЛАНО (БЛОКИ 1 И 2 — 100%)

Все исправления Блоков 1 и 2 полностью реализованы в кодовой базе, протестированы unit-тестами (78 тестов проходят успешно) и подтверждены проверками Django (`manage.py check` — 0 ошибок).

### Блок 1: Безопасность (P0) — 100% Завершён
1. **P0-1 (A1 + #1) — Закрытие анонимного доступа в RBAC**:
   - `app/backend/api/permissions.py`: в `RbacPermission.has_permission` метод возвращает `False` для неавторизованных пользователей.
   - Очищены оверрайды `@permission_classes([IsAuthenticated])` во всех файлах вьюх (`views.py`, `views_extended.py`, `views_misc.py`, `views_import.py`, `views_payments.py`), которые ломали глобальный кортеж `(IsAuthenticated, RbacPermission)`.
   - Публичные эндпоинты (`auth_login`, `click_webhook`, `payme_webhook`) защищены явным `@permission_classes([AllowAny])`.
2. **P0-2 (A3) — Запрет незарегистрированных маршрутов API**:
   - `app/backend/accounts/rbac.py`: добавлена константа `PERM_DENIED = '__denied__'`. `user_has_permission` принудительно возвращает `False` при передаче `PERM_DENIED`.
   - `app/backend/api/rbac_routes.py`: функция `resolve_permission` возвращает `PERM_DENIED` на любой несовпавший маршрут (вместо прежнего опасного `PERM_DASHBOARD_VIEW`).
   - Добавлено явное правило для `GET ^expense_types/\d+$` (`PERM_FINANCE_VIEW`) и удалено дублирующее правило для `company/settings`.
3. **P0-3 (A2 + #19) — Ликвидация эскалации прав**:
   - `app/backend/accounts/rbac.py`: добавлена роль `ROLE_STUDENT = 'student'` с пустыми правами `frozenset()`.
   - В `get_effective_role(user)`: студент мапится в `ROLE_STUDENT`. Пользователь `STAFF` без роли по умолчанию получает безопасную `ROLE_LIMITED_ADMIN` (вместо полного администратора).
4. **P0-4 (#32) — Защита настроек компании и маскирование секретов**:
   - `app/backend/api/v1/views_extended.py` (`company_settings`):
     - Изменение настроек (`POST`) требует `PERM_SETTINGS_COMPANY` или роль CEO.
     - Обновление секретных ключей (`click_secret_key`, `payme_secret_key`) разрешено только CEO.
     - В `GET`-запросах значения секретных ключей маскируются как `'***'` для не-CEO.
5. **P0-5 (#33) — Защита операций с платежами (`payment_detail`)**:
   - `app/backend/api/v1/views_extended.py` (`payment_detail`):
     - `GET` требует `PERM_FINANCE_VIEW`.
     - `PATCH` и `DELETE` требуют `PERM_FINANCE_WRITE` или роль CEO.
     - Удаление платежей, по которым оформлен возврат, блокируется с кодом `400 Bad Request`.
     - Операции обёрнуты в `transaction.atomic()`, валидируется `amount > 0`.
6. **P0-6 (#17, 18, 34) — Устранение захардкоженных паролей и нормализация телефонов**:
   - В `staff_create_view`, `staff_detail_view`, `teacher_create_view`: убран пароль `'946263200'`.
   - Пароли генерируются криптографически через `_generate_password()`.
   - Номера телефонов валидируются и нормализуются функцией `normalize_phone()`.
7. **P0-7 (E2 + #8) — Защита профиля `auth_me`**:
   - `app/backend/api/v1/views.py` (`auth_me`): не-CEO запрещено менять своё имя, фамилию и должность (возврат 403). Разрешена смена только собственного телефона (с нормализацией) и пароля (с проверкой `old_password`).
8. **P0-8 (A5, #2) — Очистка учетных данных и безопасность SECRET_KEY**:
   - Из `README.md` удалены логины и пароли CEO.
   - В `app/backend/config/settings.py` встроена runtime-проверка, блокирующая запуск в продакшне с дефолтным секретным ключом.

---

### Блок 2: Финансы и Деньги (P1) — 100% Завершён
1. **P1-1 (B1 + #11) — Возвраты не помечают месяц оплаченным**:
   - `app/backend/crm/services.py` (`sync_student_paid_this_month`):
     - Фильтр платежей строго проверяет `transaction_type=Payment.TransactionType.PAYMENT`.
     - Исключены реверсированные платежи: `reversals__isnull=True`.
     - Фильтрация переведена на `payment_date` (с фолбэком на `created_at`).
   - `app/backend/api/v1/views.py` (`_get_student_payments_queryset`, `_company_payments_summary`): применены аналогичные фильтры.
2. **P1-2 (#3, #35) — Чистая выручка в Dashboard и P&L**:
   - `app/backend/api/v1/views.py` (`dashboard`): `finance_chart` вычисляет сумму поступлений за вычетом возвратов: `Sum(amount, filter=PAYMENT) - Sum(amount, filter=REFUND)`.
   - `app/backend/api/v1/views_extended.py` (`report_pnl`): `total_revenue` и `revenue_by_method` считают чистую выручку (`paid - refunded`). Возвраты больше не прибавляются к доходу.
3. **P1-3 (#13, §7.3) — Восстановление эндпоинта GET `/v1/replenishments`**:
   - `app/backend/api/v1/views_extended.py`: устранён критический баг «All payments пуст». GET-блок кода, ошибочно лежавший внутри `payment_refund` после строки `return`, возвращён в функцию `replenishments(request)`.
   - Поддерживает фильтрацию по методу оплаты, ID студента, строке поиска `q` и диапазону дат.
4. **P1-4 (B4 + #12) — Защита предоплаченных месяцев при разморозке**:
   - `app/backend/crm/models.py`: в модель `Student` добавлено поле `frozen_at = models.DateTimeField(null=True, blank=True)`. Значение автоматически устанавливается при переходе в `FROZEN` и сбрасывается при выходе.
   - `app/backend/api/v1/views.py` (`_calculate_unfreeze_offset`):
     - Считает количество фактически потреблённых месяцев обучения до момента заморозки.
     - Смещение вычисляется по формуле владельца: `payment_offset = min(current_paid_months, consumed_months)`.
     - Предоплата за будущее сохраняется на балансе студента (`next_payment_date` сдвигается вперёд).
5. **P1-5 (B3 + #5, 6, 36) — Защита транзакций возврата (`payment_refund`)**:
   - Операция возврата защищена `transaction.atomic()` и `select_for_update()`.
   - Запрещён возврат возвратной записи (`Cannot refund a refund record`, 400).
   - Вычисляется кумулятивная сумма предыдущих возвратов. Запрещён возврат больше остатка платежа.
   - Запись возврата создаётся с `months_covered = 0` (не раздувает счётчик оплат).
   - Исправлен баг в `_serialize_payment`: конструкция `getattr(..., 'months_covered', 1) or 1` приводила к превращению `0` в `1`. Заменена на явную проверку `is not None`.
   - Вызывается `sync_student_paid_this_month` для пересчёта статуса должника.
6. **P1-6 (B2) — Реализация даты платежа `payment_date`**:
   - В модель `finance.Payment` добавлено поле `payment_date = models.DateField(null=True, blank=True, db_index=True)`.
   - Создана и применена миграция `finance.0007` с data-migration, перенёсшей `created_at.date()` в `payment_date` для всех существующих записей в БД.
   - Эндпоинт `replenishments` принимает `payment_date` (дефолт — сегодня), P&L переведён на `payment_date`.
7. **P1-7 (A6) — Устранение дублей транзакций вебхуков Click/Payme**:
   - В `finance.PaymentTransaction` индекс заменён на `UniqueConstraint(fields=['company', 'provider', 'trans_id'])`.
   - Поле `student` переведено на `SET_NULL` (удаление студента не уничтожает финансовую транзакцию).
   - В миграцию `finance.0007` включена автоматическая дедупликация записей.
8. **P1-8 (#4, 37) — Запрет отрицательных и нулевых сумм**:
   - Во всех финансовых эндпоинтах (`replenishments`, `payment_refund`, `withdraws`, `withdrawal_detail`, `expense_list`, `expense_detail`) встроена строгая валидация `if amount <= 0: return fail('Valid positive amount is required', status_code=400)`.
9. **P1-9 (B7 / #25) — Удаление устаревшего `balance_mode`**:
   - Поле `balance_mode` и класс `PaymentMode` удалены из `org/models.py`, `org/admin.py`, и `seed_demo.py` (миграция `org.0006`).
   - В `_serialize_company` сохранена статическая заглушка `'balance_mode': 1` для совместимости со строгими типами Vue 3 / TypeScript.

---

## 4. ДЕТАЛЬНЫЙ ПЛАН ТОГО, ЧТО ЕЩЁ НЕ СДЕЛАНО (БЛОКИ 3, 4 И УРОВЕНЬ P4)

### ✅ БЛОК 3 ЗАВЕРШЁН 2026-09-24 (тесты: `crm/tests_block3.py`, всего 96 тестов OK). Ниже — исходное описание задач C1 — C6

#### 1. Задача C1 (#20, #21): Синхронизация теневого журнала `GroupEnrollment`
- **Проблема**: `Student.group` — истина, но `sync_student_group_enrollment` вызывается точечно. Пропущена в:
  - Конвертации лида в студента (`lead_convert_to_student` в `api/v1/views.py`): студент создаётся с группой, но запись в `GroupEnrollment` не появляется.
  - Мягком удалении студента (`student_detail` DELETE): выставляются `status=LEFT, group=None`, но sync не вызывается.
  - Импорте студентов из Excel (`api/v1/views_import.py`).
  - Восстановлении из архива (`api/v1/views_misc.py`).
- **Решение**: Обеспечить явный вызов `sync_student_group_enrollment` во всех вышеперечисленных точках либо привязать автоматическую синхронизацию к сигналу `post_save` модели `Student` (с проверкой изменений полей `group_id` и `status`).

#### 2. Задача C2 (#22): Расписание — баг CUSTOM и дни недели
- **Файл**: `app/backend/crm/services.py` (`sync_group_schedule_slots`).
- **Проблема**:
  1. Для `Group.Days.CUSTOM` захардкожены дни `[0, 2, 4]` (пн/ср/пт). Кастомная группа получает слоты не в свои дни.
  2. `days_overlap()` для CUSTOM всегда возвращает `True`, вызывая ложные конфликты аудиторий и преподавателей.
- **Решение**: Добавить в модель `Group` сохранение явного списка дней недели `weekdays` для кастомного расписания; в `days_overlap` сравнивать фактические списки пересекающихся дней вместо безусловного `True`.

#### 3. Задача C3: Удаление алиасов статусов Student
- **Файл**: `app/backend/crm/models.py` (`Student.Status`).
- **Проблема**: `Status.ACTIVE = Status.STUDYING`, `Status.TRIAL = Status.STUDYING`, `Status.DEBTOR = Status.STUDYING`, `Status.LEFT_ACTIVE = Status.LEFT`. Любой вызов `filter(status=Status.DEBTOR)` возвращает всех обучающихся студентов.
- **Решение**: Найти и заменить все вызовы `Status.DEBTOR`, `Status.TRIAL`, `Status.LEFT_ACTIVE`, `Student.Status.ACTIVE` на реальные статусы (`STUDYING`, `LEFT`). В `crm/models.py` поставить `default=Status.STUDYING`. Удалить 4 строки алиасов. (`Group.Status.ACTIVE` и `GroupEnrollment.Status.ACTIVE` не трогать!).

#### 4. Задача C4: Каскадное удаление (Branch PROTECT)
- **Проблема**: Удаление филиала сейчас уничтожает студентов, группы, аудитории и посещаемость каскадом (`CASCADE`).
- **Решение**: В `Student.branch` и `Group.branch` выставить `on_delete=models.PROTECT`. Во вьюхе удаления филиала (`branch_detail` DELETE) блокировать операцию и возвращать ошибку 400, если в филиале есть активные группы или студенты. Создать и применить миграцию.

#### 5. Задача C5: Объединение журналов аудита
- **Проблема**: Существуют две модели: `ActivityLog` (текстовая) и `AuditLogRecord` (полноценный аудит со связями и diffs).
- **Решение**: Перевести все операции логирования на `operations.models.AuditLogRecord` (`log_audit()`). Удалить модель `ActivityLog` и старые вьюхи чтения логов.

#### 6. Задача C6: Два бага в `sync_student_group_enrollment`
- **Файл**: `app/backend/crm/services.py`.
- **Проблема**: (1) Студент со статусом `LEFT`, переведённый в новую группу, получает запись со статусом `FROZEN`; (2) Студент, вернувшийся из `LEFT` в `STUDYING` в той же группе: старая запись закрыта, новая не создаётся.
- **Решение**: Заменить функцию на эталонную реализацию из раздела 3 Документа 1 аудита.

---

### ✅ БЛОК 4 ВЫПОЛНЕН 2026-09-25, КРОМЕ B5 и E3 (ждут решения владельца). Тесты: `crm/tests_block4.py`, всего 126 OK. Ниже — исходный план

1. **B5 (Система скидок)**: Добавить `salary_base_amount = models.IntegerField(null=True, blank=True)` в `finance.Payment`. Фиксировать базу для начисления ЗП учителя при создании платежа со скидкой (снапшот).
2. **B6 (Деление цены на уроки)**: Реализовать функцию `split_monthly(price, lesson_dates)` (остаток целочисленного деления добирает последний урок месяца, исключая потерю сумов).
3. **A4 / #10, 26, 27 (Tenant isolation и архивация)**: В `archive_list`, `company_platform_payments` сверять `company_id` из URL со своей компанией; синхронизировать ветки архивации учителя в `teacher_detail_view` и `archive_list`.
4. **D1 (UniqueConstraints)**: Дедуплицировать и добавить ограничения для `Branch(company, name)`, `Tag(company, name)`, `StudentScore(student, group)`, `Holiday(company, branch, holiday_date)`, `GroupEnrollment(student, group)` при `left_date__isnull=True`, `ExpenseCategory(company, name)`.
5. **D2 / #24 (FK company в Room)**: Добавить настоящее поле `company` в `Room`, провести data-migration, убрать лишние `branch__company`.
6. **D3, D4 (Целостность Lead)**: Сбрасывать `attended_trial` в `save()` при откате стадии; в `match_student_to_lead` исключать лиды со стадией `CONVERTED`.
7. **D5 (Транзакции посещаемости)**: Обернуть массовую отметку посещаемости и автосписания в `transaction.atomic()`.
8. **D7 / #23 (Статус напоминаний Reminder)**: Перевести `Reminder.status` в вычисляемое свойство на лету (OVERDUE/TODAY/FUTURE), чтобы они не устаревали в БД.
9. **D8 (Ставки SalarySetting)**: Добавить валидацию перекрывающихся периодов и правило старшинства.
10. **D9 (Нормализация телефонов)**: Проверить и внедрить нормализацию в `Student`, `Lead` и Excel-импорт.
11. **D10 / #24 (Вместимость аудиторий Room.capacity)**: Добавить проверку вместимости при зачислении студентов в группу.
12. **E1 / #9, 14, 28, 30 (Teacher Scope)**: Фильтровать данные только групп преподавателя (`group__teacher=request.user`), вырезать финансовые поля (`balance`, `next_due`, `paid_this_month`, `overdue_days`) через `strip_for_teacher`, запретить учителю ставить оценки (`scores_branch`) чужим группам.
13. **E3 (Branch Director Scope)**: Ограничить видимость филиалов в `_user_branches` для директора филиала.
14. **#29 (Стабильность scores_branch)**: Защитить `limit = int(...)` от нечисловых параметров (`try-except`).
15. **Раздел 7 п.11 (Капитализация имён)**: Реализовать функцию `capitalize_name` со списком узбекских частиц-исключений (`og'li`, `qizi`, `оглы`, `кызы`).
16. **Раздел 7 п.12 (Категории расходов)**: Слить дубликаты `ExpenseCategory` data-миграцией, добавить `UniqueConstraint(company, name)`.

---

### ✅ P4 ВЫПОЛНЕН 2026-09-25 (кроме F2 — язык Choices). Итоги — строки 42–44 в разделе 2. Ниже — исходный план

Завершающий этап приведения кодовой базы и пользовательского интерфейса в полный порядок:

| № | Код задачи | Модуль / Файл | Что конкретно сделать | Зачем / Риск | Статус |
|---|---|---|---|---|---|
| 42 | **P4-1 (E4)** | `api/rbac_routes.py`,<br>`api/v1/urls.py` | 1. Удалить неиспользуемые пермишены (`PERM_SETTINGS_INTEGRATIONS`, `PERM_SETTINGS_GRADE`, `PERM_GROUPS_EXPORT`).<br>2. Удалить дублирующиеся роуты (`holidayRecalculation`, `reminder/index`, `company/<id>/users/trashed`).<br>3. Удалить дублирующееся правило `POST ^company/settings$`. | Очистка мертвого кода и устранение дубликатов в маршрутизации. | **НЕ СДЕЛАНО ⏳** |
| 43 | **P4-2 (F1–F6)** | Модели всех приложений (`operations`, `crm`, `finance`), `README.md` | 1. Заменить устаревший `unique_together` на современный `UniqueConstraint` в `TeacherAttendanceRecord` и `WorklyRecord` (F1).<br>2. Унифицировать язык Choices (русский / английский) (F2).<br>3. Обновить в `README.md` описание архитектуры: Attendance/Schedule живут в `crm/`, а не в `operations/` (F3).<br>4. Перевести денежные суммы с 32-битного IntegerField на `BigIntegerField` во избежание переполнения 2.1 млрд сум (F4).<br>5. Задокументировать единицы измерения длительности курсов (`Course.course_duration`) через verbose_name (F5).<br>6. Оптимизировать `Student.save()` от лишних SELECT-запросов (F6). | Единый стиль моделей Django, защита от переполнения и чистота архитектуры. | **НЕ СДЕЛАНО ⏳** |
| 44 | **P4-3 (Фронтенд)** | `app/frontend/src` | 1. Скрыть в UI финансовые разделы, колонки балансов и кнопки удаления для учителей.<br>2. Вычистить из компонентов обращения к удалённым алиасам `DEBTOR` и `TRIAL`.<br>3. Пересобрать фронтенд (`npm run build`) и синхронизировать с установленной версией через протокол `sync-app.ps1`. | Полная синхронизация пользовательского интерфейса с новыми серверными правилами. | **СДЕЛАНО ✅** |

---

## 5. БАЗА ДАННЫХ, МИГРАЦИИ И ВЕРИФИКАЦИЯ

### Уже применённые миграции в кодовой базе:
1. `crm.0029_student_frozen_at` (поле `frozen_at`)
2. `org.0006_remove_company_balance_mode` (удаление `balance_mode`)
3. `finance.0007_remove_paymenttransaction_finance_pay_company_bcfdc4_idx_and_more` (поле `payment_date`, `UniqueConstraint` транзакций)

### Команды для регулярной проверки:
```powershell
# 1. Проверка моделей и конфигурации Django
app\backend\.venv\Scripts\python.exe app\backend\manage.py check

# 2. Проверка соответствия моделей и миграций
app\backend\.venv\Scripts\python.exe app\backend\manage.py makemigrations --check --dry-run

# 3. Запуск полного набора unit-тестов
app\backend\.venv\Scripts\python.exe app\backend\manage.py test accounts
# Текущий результат: Ran 126 tests -> OK (0 failures, 0 errors).
```

### Памятка по синхронизации с десктопным приложением:
В соответствии с `AGENTS.md` / `GEMINI.md`, если вы тестируете через запущенное приложение:
1. Пересобрать фронтенд: `cd app/frontend; npm run build` (если правился фронт).
2. Запустить синхронизацию: `powershell -ExecutionPolicy Bypass -File "sync-app.ps1"`.
3. В браузере всегда нажимать **`Ctrl + F5`** (или `Ctrl + Shift + R`) для сброса кэша.
