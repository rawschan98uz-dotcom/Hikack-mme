<script setup lang="ts">
import { computed } from 'vue';

export interface ReceiptPayment {
  id: number;
  date: string;
  student_name: string;
  amount: number;
  months_covered?: number;
  method?: string;
  method_pay?: string;
  teacher?: string;
  teacher_name?: string;
  comment?: string;
  creator?: string;
}

const props = withDefaults(
  defineProps<{
    open: boolean;
    payment: ReceiptPayment | null;
    companyName?: string;
    companyPhone?: string;
    companyAddress?: string;
  }>(),
  {
    companyName: 'HiJack LMS Educational Center',
    companyPhone: '',
    companyAddress: '',
  },
);

const emit = defineEmits<{
  'update:open': [value: boolean];
}>();

const methodLabel = computed(() => {
  const m = (props.payment?.method_pay || props.payment?.method || '').toLowerCase();
  if (m === 'cash') return 'Наличные (Cash)';
  if (m === 'card') return 'Банковская карта (Card)';
  if (m === 'transfer') return 'Банковский перевод (Transfer)';
  return props.payment?.method_pay || props.payment?.method || 'Наличные';
});

const formattedAmount = computed(() => {
  if (!props.payment) return '0';
  return props.payment.amount.toLocaleString();
});

function close() {
  emit('update:open', false);
}

function printReceipt() {
  window.print();
}
</script>

<template>
  <div v-if="open && payment" class="fixed inset-0 z-50 flex items-center justify-center p-4 print:p-0">
    <!-- Backdrop (hidden on print) -->
    <div class="fixed inset-0 bg-black/50 no-print" @click="close" />

    <!-- Modal Card -->
    <div class="relative w-full max-w-lg rounded-2xl border border-fb-line bg-white p-6 shadow-2xl print:max-w-none print:border-none print:p-8 print:shadow-none">
      <!-- Actions Bar (hidden on print) -->
      <div class="mb-4 flex items-center justify-between border-b border-fb-line pb-3 no-print">
        <div class="flex items-center gap-2 text-sm font-semibold text-fb-text">
          <span class="text-lg">🧾</span>
          <span>Квитанция об оплате</span>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-1.5 rounded-lg bg-fb-blue px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-fb-hoverBtn transition-colors"
            @click="printReceipt"
          >
            <span>🖨️</span>
            <span>Печать</span>
          </button>
          <button
            type="button"
            class="rounded-lg p-1.5 text-fb-secondary hover:bg-fb-canvas hover:text-fb-text transition-colors"
            @click="close"
          >
            ✕
          </button>
        </div>
      </div>

      <!-- Printable Receipt Sheet -->
      <div class="receipt-body rounded-xl border border-dashed border-gray-300 p-6 text-gray-800 print:border-solid print:border-gray-800">
        <!-- Header -->
        <div class="border-b-2 border-gray-800 pb-4 text-center">
          <h2 class="text-lg font-bold tracking-tight text-gray-900 uppercase">
            {{ companyName || 'Учебный Центр' }}
          </h2>
          <div v-if="companyAddress || companyPhone" class="mt-1 text-xs text-gray-600 space-x-2">
            <span v-if="companyAddress">{{ companyAddress }}</span>
            <span v-if="companyAddress && companyPhone">•</span>
            <span v-if="companyPhone">Тел: {{ companyPhone }}</span>
          </div>
          <div class="mt-2 text-xs font-bold uppercase tracking-widest text-emerald-700">
            Квитанция к приходному ордеру № {{ payment.id }}
          </div>
        </div>

        <!-- Meta Grid -->
        <div class="mt-4 space-y-2.5 text-xs">
          <div class="flex justify-between py-1 border-b border-gray-100">
            <span class="text-gray-500">Дата и время:</span>
            <span class="font-medium">{{ payment.date }}</span>
          </div>
          <div class="flex justify-between py-1 border-b border-gray-100">
            <span class="text-gray-500">Плательщик (Ученик):</span>
            <span class="font-bold text-gray-900 text-sm">{{ payment.student_name }}</span>
          </div>
          <div v-if="payment.teacher || payment.teacher_name" class="flex justify-between py-1 border-b border-gray-100">
            <span class="text-gray-500">Преподаватель:</span>
            <span class="font-medium">{{ payment.teacher || payment.teacher_name }}</span>
          </div>
          <div class="flex justify-between py-1 border-b border-gray-100">
            <span class="text-gray-500">Оплаченный период:</span>
            <span class="font-semibold text-fb-blue">
              {{ payment.months_covered || 1 }} мес.
            </span>
          </div>
          <div class="flex justify-between py-1 border-b border-gray-100">
            <span class="text-gray-500">Форма оплаты:</span>
            <span class="font-medium">{{ methodLabel }}</span>
          </div>
          <div v-if="payment.comment" class="flex justify-between py-1 border-b border-gray-100">
            <span class="text-gray-500">Назначение / Примечание:</span>
            <span class="italic text-gray-700">{{ payment.comment }}</span>
          </div>
        </div>

        <!-- Total Box -->
        <div class="mt-5 rounded-lg bg-gray-50 p-3.5 text-center border border-gray-200">
          <div class="text-[11px] font-medium uppercase tracking-wider text-gray-500">Сумма к оплате</div>
          <div class="mt-0.5 text-2xl font-black text-gray-900">
            {{ formattedAmount }} <span class="text-sm font-semibold">UZS</span>
          </div>
        </div>

        <!-- Footer / Signatures -->
        <div class="mt-6 pt-3 border-t border-gray-200 grid grid-cols-2 gap-4 text-xs">
          <div>
            <div class="text-gray-500">Кассир / Администратор:</div>
            <div class="mt-1 font-medium">{{ payment.creator || 'Администратор' }}</div>
            <div class="mt-4 border-b border-gray-400 w-32" />
            <div class="text-[10px] text-gray-400 mt-0.5">(подпись)</div>
          </div>
          <div class="text-right flex flex-col items-end">
            <div class="text-gray-500">М.П. (Место печати)</div>
            <div class="mt-3 h-10 w-20 rounded-full border border-dashed border-gray-300 flex items-center justify-center text-[10px] text-gray-400">
              Печать
            </div>
          </div>
        </div>

        <div class="mt-4 text-center text-[10px] text-gray-400">
          Спасибо за обучение! Сохраняйте квитанцию до окончания оплаченного периода.
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@media print {
  .no-print {
    display: none !important;
  }
  body * {
    visibility: hidden;
  }
  .receipt-body,
  .receipt-body * {
    visibility: visible;
  }
  .receipt-body {
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
    margin: 0;
    padding: 24px;
    border: 1px solid #111 !important;
  }
}
</style>
