<script setup lang="ts">
import { ref, watch } from 'vue';

import client, { type ApiEnvelope } from '../api/client';

export interface StudentPaymentLinkTarget {
  id: number;
  full_name: string;
  phone: string;
  group?: string | null;
  course_price?: number;
  parent_telegram?: string;
}

interface GatewayLink {
  url: string;
  configured: boolean;
}

interface PaymentLinksData {
  student_id: number;
  student_name: string;
  amount: number;
  click: GatewayLink;
  payme: GatewayLink;
  uzum: GatewayLink;
}

const props = defineProps<{
  open: boolean;
  student: StudentPaymentLinkTarget | null;
}>();

const emit = defineEmits<{
  'update:open': [value: boolean];
}>();

const months = ref(1);
const customAmount = ref(0);
const loading = ref(false);
const error = ref('');
const linksData = ref<PaymentLinksData | null>(null);

const copiedType = ref('');
const sendingTg = ref(false);
const tgMessage = ref('');
const tgSuccess = ref(false);

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen && props.student) {
      months.value = 1;
      customAmount.value = props.student.course_price || 0;
      tgMessage.value = '';
      tgSuccess.value = false;
      error.value = '';
      void loadLinks();
    }
  },
);

function onMonthsChange() {
  if (months.value < 1) months.value = 1;
  const unitPrice = props.student?.course_price || 0;
  if (unitPrice > 0) {
    customAmount.value = unitPrice * months.value;
  }
  void loadLinks();
}

function onAmountChange() {
  void loadLinks();
}

async function loadLinks() {
  if (!props.student) return;
  loading.value = true;
  error.value = '';
  try {
    const { data } = await client.get<ApiEnvelope<PaymentLinksData>>(
      `/students/${props.student.id}/payment-links`,
      { params: { amount: customAmount.value || undefined } },
    );
    linksData.value = data.data;
  } catch {
    error.value = 'Не удалось загрузить ссылки на оплату';
  } finally {
    loading.value = false;
  }
}

function copyLink(url: string, type: string) {
  if (!url) return;
  navigator.clipboard.writeText(url);
  copiedType.value = type;
  setTimeout(() => {
    copiedType.value = '';
  }, 2000);
}

async function sendToTelegram() {
  if (!props.student) return;
  sendingTg.value = true;
  tgMessage.value = '';
  try {
    const { data } = await client.post<{ data: { message: string; sent: boolean } }>(
      `/students/${props.student.id}/send-payment-link`,
      { amount: customAmount.value },
    );
    tgSuccess.value = true;
    tgMessage.value = data.data.message || 'Ссылка успешно отправлена родителю!';
  } catch (err: any) {
    tgSuccess.value = false;
    tgMessage.value = err.response?.data?.message || err.response?.data?.error || 'Не удалось отправить ссылку в Telegram';
  } finally {
    sendingTg.value = false;
  }
}

function close() {
  emit('update:open', false);
}
</script>

<template>
  <div v-if="open && student" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <!-- Backdrop -->
    <div class="fixed inset-0 bg-black/45" @click="close" />

    <!-- Modal Box -->
    <div class="relative w-full max-w-lg rounded-2xl border border-fb-line bg-fb-card p-6 shadow-2xl">
      <div class="flex items-center justify-between border-b border-fb-line pb-3">
        <div>
          <h3 class="text-base font-semibold text-fb-text flex items-center gap-2">
            <span>💳</span>
            <span>Ссылка на онлайн-оплату</span>
          </h3>
          <p class="text-xs text-fb-secondary mt-0.5">{{ student.full_name }} • {{ student.phone }}</p>
        </div>
        <button type="button" class="text-fb-secondary hover:text-fb-text" @click="close">✕</button>
      </div>

      <!-- Content -->
      <div class="mt-4 space-y-4">
        <!-- Controls: Period and Amount -->
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">Период (месяцев)</label>
            <input
              v-model.number="months"
              type="number"
              min="1"
              max="12"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none"
              @change="onMonthsChange"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-fb-secondary">Сумма к оплате (UZS)</label>
            <input
              v-model.number="customAmount"
              type="number"
              min="1000"
              class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm font-semibold text-fb-blue focus:border-fb-blue focus:outline-none"
              @change="onAmountChange"
            />
          </div>
        </div>

        <div v-if="student.course_price" class="text-[11px] text-fb-secondary">
          Базовый тариф курса: {{ student.course_price.toLocaleString() }} UZS / месяц
        </div>

        <div v-if="loading" class="py-6 text-center text-xs text-fb-secondary">
          Генерация ссылок…
        </div>
        <div v-else-if="error" class="text-xs text-fb-danger text-center">
          {{ error }}
        </div>

        <div v-else-if="linksData" class="space-y-3 pt-1">
          <!-- Click Link -->
          <div class="rounded-xl border border-fb-line bg-fb-canvas/50 p-3 space-y-2">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="inline-block h-2.5 w-2.5 rounded-full bg-blue-500" />
                <span class="font-semibold text-xs text-fb-text">Click</span>
                <span
                  class="rounded px-1.5 py-0.5 text-[10px] font-medium"
                  :class="linksData.click.configured ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'"
                >
                  {{ linksData.click.configured ? 'Активен' : 'Демо режим' }}
                </span>
              </div>
              <div class="flex items-center gap-2">
                <a
                  :href="linksData.click.url"
                  target="_blank"
                  rel="noopener"
                  class="text-[11px] font-medium text-fb-blue hover:underline"
                >
                  Открыть ↗
                </a>
                <button
                  type="button"
                  class="rounded-lg border border-fb-line bg-white px-2.5 py-1 text-xs font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
                  @click="copyLink(linksData.click.url, 'click')"
                >
                  {{ copiedType === 'click' ? '✓ Скопировано' : 'Скопировать' }}
                </button>
              </div>
            </div>
            <div class="truncate rounded border border-fb-line bg-white px-2 py-1 text-[11px] font-mono text-fb-secondary">
              {{ linksData.click.url }}
            </div>
          </div>

          <!-- Payme Link -->
          <div class="rounded-xl border border-fb-line bg-fb-canvas/50 p-3 space-y-2">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="inline-block h-2.5 w-2.5 rounded-full bg-cyan-500" />
                <span class="font-semibold text-xs text-fb-text">Payme</span>
                <span
                  class="rounded px-1.5 py-0.5 text-[10px] font-medium"
                  :class="linksData.payme.configured ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'"
                >
                  {{ linksData.payme.configured ? 'Активен' : 'Демо режим' }}
                </span>
              </div>
              <div class="flex items-center gap-2">
                <a
                  :href="linksData.payme.url"
                  target="_blank"
                  rel="noopener"
                  class="text-[11px] font-medium text-fb-blue hover:underline"
                >
                  Открыть ↗
                </a>
                <button
                  type="button"
                  class="rounded-lg border border-fb-line bg-white px-2.5 py-1 text-xs font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
                  @click="copyLink(linksData.payme.url, 'payme')"
                >
                  {{ copiedType === 'payme' ? '✓ Скопировано' : 'Скопировать' }}
                </button>
              </div>
            </div>
            <div class="truncate rounded border border-fb-line bg-white px-2 py-1 text-[11px] font-mono text-fb-secondary">
              {{ linksData.payme.url }}
            </div>
          </div>

          <!-- Uzum Link -->
          <div class="rounded-xl border border-fb-line bg-fb-canvas/50 p-3 space-y-2">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="inline-block h-2.5 w-2.5 rounded-full bg-purple-600" />
                <span class="font-semibold text-xs text-fb-text">Uzum Bank</span>
                <span
                  class="rounded px-1.5 py-0.5 text-[10px] font-medium"
                  :class="linksData.uzum.configured ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'"
                >
                  {{ linksData.uzum.configured ? 'Активен' : 'Демо режим' }}
                </span>
              </div>
              <div class="flex items-center gap-2">
                <a
                  :href="linksData.uzum.url"
                  target="_blank"
                  rel="noopener"
                  class="text-[11px] font-medium text-fb-blue hover:underline"
                >
                  Открыть ↗
                </a>
                <button
                  type="button"
                  class="rounded-lg border border-fb-line bg-white px-2.5 py-1 text-xs font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
                  @click="copyLink(linksData.uzum.url, 'uzum')"
                >
                  {{ copiedType === 'uzum' ? '✓ Скопировано' : 'Скопировать' }}
                </button>
              </div>
            </div>
            <div class="truncate rounded border border-fb-line bg-white px-2 py-1 text-[11px] font-mono text-fb-secondary">
              {{ linksData.uzum.url }}
            </div>
          </div>
        </div>

        <!-- Telegram Action Section -->
        <div class="border-t border-fb-line pt-3">
          <div class="flex items-center justify-between">
            <div class="text-xs text-fb-secondary">
              <span v-if="student.parent_telegram" class="text-emerald-700 font-medium">
                ✓ Telegram родителя: {{ student.parent_telegram }}
              </span>
              <span v-else class="text-amber-700">
                ⚠️ У ученика не указан Telegram родителя
              </span>
            </div>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-sky-700 disabled:opacity-50 transition-colors"
              :disabled="sendingTg || !student.parent_telegram"
              @click="sendToTelegram"
            >
              <span>📲</span>
              <span>{{ sendingTg ? 'Отправка…' : 'Отправить в Telegram' }}</span>
            </button>
          </div>
          <p
            v-if="tgMessage"
            class="mt-2 text-xs font-medium text-center"
            :class="tgSuccess ? 'text-emerald-700' : 'text-fb-danger'"
          >
            {{ tgMessage }}
          </p>
        </div>
      </div>

      <div class="mt-5 flex justify-end border-t border-fb-line pt-3">
        <button
          type="button"
          class="rounded-lg border border-fb-line px-4 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-canvas"
          @click="close"
        >
          Закрыть
        </button>
      </div>
    </div>
  </div>
</template>
