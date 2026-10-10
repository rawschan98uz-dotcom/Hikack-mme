<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import SkeletonBlock from '../components/SkeletonBlock.vue';

import client, { type ApiEnvelope } from '../api/client';
import { t, type MessageKey } from '../i18n';
import { toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';

interface SettingsData {
  name: string;
  phone: string;
  address: string;
  timezone: string;
  currency: string;
  balance_mode?: number;
  sms_enabled: boolean;
  click_service_id?: string;
  click_merchant_id?: string;
  click_secret_key?: string;
  payme_merchant_id?: string;
  payme_secret_key?: string;
  uzum_merchant_id?: string;
  tabs: string[];
}

const settings = ref<SettingsData | null>(null);
const activeTab = ref('General settings');
const loading = ref(true);
const saving = ref(false);
const copiedField = ref('');

// Tab names come from the server in English; show them in the interface language
const TAB_LABELS: Record<string, MessageKey> = {
  'General settings': 'settingsTab.general',
  'Payment methods': 'settingsTab.payment',
  'Sign in': 'settingsTab.signIn',
  'Lead form': 'settingsTab.leadForm',
  Communication: 'settingsTab.communication',
  Integrations: 'settingsTab.integrations',
  Exams: 'settingsTab.exams',
  Invoice: 'settingsTab.invoice',
  'Accrual and payment': 'settingsTab.accrual',
  'Landing page': 'settingsTab.landing',
};

function tabLabel(tab: string) {
  const key = TAB_LABELS[tab];
  return key ? t(key) : tab;
}

function copyText(val: string, label: string) {
  if (!val) return;
  void navigator.clipboard.writeText(val);
  toast.success(t('common.copied'));
  copiedField.value = label;
  setTimeout(() => {
    copiedField.value = '';
  }, 2000);
}

const clickWebhookUrl = computed(() => {
  return `${window.location.origin}/v1/payments/click/webhook`;
});

const paymeWebhookUrl = computed(() => {
  return `${window.location.origin}/v1/payments/payme/webhook`;
});

async function load() {
  loading.value = true;
  try {
    const { data } = await client.get<ApiEnvelope<SettingsData>>('/company/settings');
    settings.value = data.data;
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (!settings.value) return;
  saving.value = true;
  try {
    await client.post('/company/settings', settings.value);
    toast.success(t('toast.saved'));
  } catch (err: unknown) {
    toast.error(apiErrorMessage(err, t('errors.saveFailed')));
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold text-fb-text">{{ t('nav.settings') }}</h1>

    <SkeletonBlock v-if="loading" variant="lines" :rows="6" />

    <template v-else-if="settings">
      <div class="flex flex-wrap gap-2 border-b border-fb-line pb-2">
        <button
          v-for="tab in settings.tabs"
          :key="tab"
          type="button"
          class="px-3 py-1.5 rounded-lg text-sm"
          :class="activeTab === tab ? 'bg-fb-hover text-fb-blue font-medium' : 'text-fb-secondary hover:bg-fb-canvas'"
          @click="activeTab = tab"
        >
          {{ tabLabel(tab) }}
        </button>
      </div>

      <!-- General settings tab -->
      <div v-if="activeTab === 'General settings'" class="bg-fb-card rounded-xl border border-fb-line p-6 space-y-4 max-w-xl">
        <div>
          <label class="block text-sm font-medium text-fb-secondary mb-1">{{ t('settings.centerName') }}</label>
          <input v-model="settings.name" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
        </div>
        <div>
          <label class="block text-sm font-medium text-fb-secondary mb-1">{{ t('common.phone') }}</label>
          <input v-model="settings.phone" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
        </div>
        <div>
          <label class="block text-sm font-medium text-fb-secondary mb-1">{{ t('settings.address') }}</label>
          <input v-model="settings.address" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
        </div>
        <label class="flex items-center gap-2 text-sm text-fb-text">
          <input v-model="settings.sms_enabled" type="checkbox" class="rounded border-fb-line" />
          {{ t('settings.smsEnabled') }}
        </label>
        <div class="flex items-center gap-3 pt-2">
          <button
            type="button"
            class="px-5 py-2 rounded-lg bg-fb-blue text-white text-sm font-medium disabled:opacity-60 hover:opacity-90"
            :disabled="saving"
            @click="save"
          >
            {{ saving ? t('common.saving') : t('common.save') }}
          </button>
        </div>
      </div>

      <!-- Payment methods tab -->
      <div v-else-if="activeTab === 'Payment methods'" class="bg-fb-card rounded-xl border border-fb-line p-6 space-y-6 max-w-2xl">
        <div>
          <h3 class="text-base font-semibold text-fb-text flex items-center gap-2">
            <span>💳</span>
            <span>{{ t('settings.paymentTitle') }}</span>
          </h3>
          <p class="text-xs text-fb-secondary mt-1">
            {{ t('settings.paymentHint') }}
          </p>
        </div>

        <!-- Click Section -->
        <div class="rounded-xl border border-fb-line bg-fb-canvas/60 p-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="font-semibold text-sm text-fb-text flex items-center gap-2">
              <span class="inline-block h-3 w-3 rounded-full bg-indigo-500" />
              <span>Click Merchant</span>
            </span>
            <span v-if="settings.click_service_id && settings.click_merchant_id" class="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
              {{ t('settings.connected') }}
            </span>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-medium text-fb-secondary mb-1">Service ID</label>
              <input v-model="settings.click_service_id" :placeholder="t('settings.example', { value: '12345' })" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
            </div>
            <div>
              <label class="block text-xs font-medium text-fb-secondary mb-1">Merchant ID</label>
              <input v-model="settings.click_merchant_id" :placeholder="t('settings.example', { value: '67890' })" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-fb-secondary mb-1">{{ t('settings.secretKey') }}</label>
            <input v-model="settings.click_secret_key" type="password" :placeholder="t('settings.clickSecretPlaceholder')" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
          </div>
          <div class="rounded-lg bg-white border border-fb-line p-3 text-xs">
            <span class="font-medium text-fb-secondary block mb-1">{{ t('settings.clickWebhook') }}</span>
            <div class="flex items-center justify-between gap-2">
              <code class="text-[11px] text-fb-blue break-all font-mono">{{ clickWebhookUrl }}</code>
              <button type="button" class="shrink-0 text-fb-blue hover:underline font-medium text-xs" @click="copyText(clickWebhookUrl, 'click')">
                {{ copiedField === 'click' ? t('common.copied') : t('common.copy') }}
              </button>
            </div>
          </div>
        </div>

        <!-- Payme Section -->
        <div class="rounded-xl border border-fb-line bg-fb-canvas/60 p-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="font-semibold text-sm text-fb-text flex items-center gap-2">
              <span class="inline-block h-3 w-3 rounded-full bg-cyan-500" />
              <span>Payme Business</span>
            </span>
            <span v-if="settings.payme_merchant_id" class="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
              {{ t('settings.connected') }}
            </span>
          </div>
          <div>
            <label class="block text-xs font-medium text-fb-secondary mb-1">{{ t('settings.paymeMerchant') }}</label>
            <input v-model="settings.payme_merchant_id" :placeholder="t('settings.paymeMerchantPlaceholder')" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
          </div>
          <div>
            <label class="block text-xs font-medium text-fb-secondary mb-1">{{ t('settings.paymeKey') }}</label>
            <input v-model="settings.payme_secret_key" type="password" :placeholder="t('settings.paymeKeyPlaceholder')" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
          </div>
          <div class="rounded-lg bg-white border border-fb-line p-3 text-xs">
            <span class="font-medium text-fb-secondary block mb-1">{{ t('settings.paymeWebhook') }}</span>
            <div class="flex items-center justify-between gap-2">
              <code class="text-[11px] text-fb-blue break-all font-mono">{{ paymeWebhookUrl }}</code>
              <button type="button" class="shrink-0 text-fb-blue hover:underline font-medium text-xs" @click="copyText(paymeWebhookUrl, 'payme')">
                {{ copiedField === 'payme' ? t('common.copied') : t('common.copy') }}
              </button>
            </div>
          </div>
        </div>

        <!-- Uzum Bank Section -->
        <div class="rounded-xl border border-fb-line bg-fb-canvas/60 p-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="font-semibold text-sm text-fb-text flex items-center gap-2">
              <span class="inline-block h-3 w-3 rounded-full bg-purple-600" />
              <span>Uzum Bank</span>
            </span>
            <span v-if="settings.uzum_merchant_id" class="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
              {{ t('settings.connected') }}
            </span>
          </div>
          <div>
            <label class="block text-xs font-medium text-fb-secondary mb-1">Merchant ID / Service Code</label>
            <input v-model="settings.uzum_merchant_id" :placeholder="t('settings.uzumPlaceholder')" class="w-full rounded-lg border border-fb-line px-3 py-2 text-sm focus:border-fb-blue focus:outline-none" />
          </div>
        </div>

        <div class="flex items-center gap-3 pt-2">
          <button
            type="button"
            class="px-6 py-2.5 rounded-lg bg-fb-blue text-white text-sm font-semibold disabled:opacity-60 hover:opacity-90 transition-opacity"
            :disabled="saving"
            @click="save"
          >
            {{ saving ? t('common.saving') : t('settings.savePayment') }}
          </button>
        </div>
      </div>

      <div v-else class="bg-fb-card rounded-xl border border-fb-line p-8 text-fb-secondary">
        {{ t('settings.tabSoon', { tab: tabLabel(activeTab) }) }}
      </div>
    </template>
  </div>
</template>
