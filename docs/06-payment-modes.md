# Payment Modes (To'lov rejimlari)

From GitBook + modme.uz demo form + dashboard (tenant: By day).

## Enum Values (`balance_mode`)

| ID | Uzbek | Russian | English |
|----|-------|---------|---------|
| 1 | Kunlik | Ежедневный | By day |
| 2 | Kalendar | Ежемесячный | Monthly (calendar) |
| 3 | Guruh boshlanish sanasi | Дата начала группы | Group start date |
| 4 | To'liq Kurs | Весь курс | Full course |
| 5 | Modul | Модуль | Module |
| 6 | Individual | Индивидуальный | Individual |

## Mode Details (from modme.uz marketing copy)

### 1 — Daily (Kunlik)
- Charge per lesson from activation date
- Frozen students are not charged
- No refund needed when moving between groups

### 2 — Monthly / Calendar (Kalendar)
- Full month price regardless of lesson count
- Billing on 1st of each month
- Good for debtor tracking and fixed teacher salaries

### 3 — Group Start Date
- Billing date = group opening date each month
- Full monthly course price

### 4 — Full Course
- One payment for entire course duration at activation
- Suited for online courses / prepaid models

### 5 — Module
- Charge every N lessons (configurable `lessons_per_module`)
- Independent of calendar month length (12 vs 13 lessons)

### 6 — Individual
- Monthly billing on the same day student was activated

## Implementation Notes for Clone

- Payment mode is set at **company/tenant level** during demo creation
- Changing mode requires contacting ModMe support (per GitBook)
- Frontend shows current mode in footer: "Payment mode: By day"
- Backend needs: `write_off`, `next_write_off_date`, `last_write_off_date` on groups (see API docs)

Source: https://modme-crm.gitbook.io/modme-crm/get-started/tolov-rejimini-tanlash
