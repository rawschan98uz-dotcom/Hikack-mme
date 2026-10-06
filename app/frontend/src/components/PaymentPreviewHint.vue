<script setup lang="ts">
/**
 * What the sum typed in a payment form will do: which months of the student it closes and what is still
 * owed afterwards. Asked from the server (the same code that counts a real payment); nothing is saved.
 */
import { onBeforeUnmount, ref, watch } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { formatSum } from '../utils/wallet';

interface PreviewLine {
  period_start: string;
  period_end: string;
  price: number;
  discount: number;
  amount: number;
  paid_before: number;
  pays: number;
  left_after: number;
  ahead: boolean;
}

interface Preview {
  debt_before: number;
  debt_after: number;
  closes: PreviewLine[];
  months_closed: number;
  waiting: number;
  next_payment_date: string;
  discount_error: string | null;
  month_price: number;
}

const props = defineProps<{
  studentId: number | null | undefined;
  amount: number | null | undefined;
  discount?: number | null;
  months?: number | null;
  date?: string | null;
}>();

const preview = ref<Preview | null>(null);
let timer: ReturnType<typeof setTimeout> | null = null;
let ticket = 0;

function day(iso: string) {
  const [year, month, date] = iso.split('-');
  return `${date}.${month}.${year}`;
}

async function load() {
  const current = ++ticket;
  if (!props.studentId || !props.amount || props.amount <= 0) {
    preview.value = null;
    return;
  }
  try {
    const { data } = await client.post<ApiEnvelope<Preview>>(`/students/${props.studentId}/payment-preview`, {
      amount: props.amount,
      discount_amount: props.discount || 0,
      months_covered: props.months || 1,
      payment_date: props.date || undefined,
    });
    if (current === ticket) preview.value = data.data;
  } catch {
    if (current === ticket) preview.value = null;
  }
}

watch(
  () => [props.studentId, props.amount, props.discount, props.months, props.date],
  () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(load, 350);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer);
});
</script>

<template>
  <div v-if="preview" class="mt-1 space-y-1 text-xs">
    <p v-if="preview.discount_error" class="rounded-md bg-red-50 px-2 py-1 text-red-700">
      {{ preview.discount_error }}
    </p>
    <div v-if="preview.closes.length" class="rounded-md bg-emerald-50 px-2 py-1.5 text-emerald-900">
      <div class="font-medium">Эта оплата закроет:</div>
      <ul class="mt-0.5 space-y-0.5">
        <li v-for="line in preview.closes" :key="line.period_start">
          {{ day(line.period_start) }} — {{ day(line.period_end) }}:
          <strong>{{ formatSum(line.pays) }}</strong>
          <span v-if="line.left_after"> из {{ formatSum(line.amount - line.paid_before) }}, останется {{ formatSum(line.left_after) }}</span>
          <span v-else> — полностью</span>
          <span v-if="line.discount"> (скидка {{ formatSum(line.discount) }})</span>
          <span v-if="line.ahead" class="text-sky-800"> · вперёд</span>
        </li>
      </ul>
      <div v-if="preview.debt_before" class="mt-1">
        Долг сейчас {{ formatSum(preview.debt_before) }} → после оплаты
        <strong>{{ formatSum(preview.debt_after) }}</strong>
      </div>
    </div>
    <p v-if="preview.waiting" class="rounded-md bg-amber-50 px-2 py-1 text-amber-800">
      {{ formatSum(preview.waiting) }} сум не на что зачислить — они останутся в копилке
      <template v-if="!preview.month_price">(у ученика нет группы с ценой курса)</template>
      <template v-else>(оплата больше чем на два года вперёд — проверьте сумму)</template>.
    </p>
  </div>
</template>
