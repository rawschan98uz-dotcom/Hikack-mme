<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import SkeletonBlock from '../components/SkeletonBlock.vue';

import { locale, localeOptions, t, tMaybe } from '../i18n';
import { useAuthStore } from '../stores/auth';
import { toast } from '../ui/feedback';
import { apiErrorMessage } from '../utils/apiError';

const auth = useAuthStore();
const loading = ref(true);
const saving = ref(false);
const showEdit = ref(false);
const formError = ref('');

const form = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  job_title: '',
  password: '',
});

const profile = computed(() => auth.user);
const displayName = computed(() => profile.value?.first_name || profile.value?.name || t('profile.title'));
const roleLabel = computed(() => (profile.value ? tMaybe(`roles.${profile.value.role}`, profile.value.role_label) : ''));
const userInitial = computed(() => (displayName.value[0] ?? 'U').toUpperCase());

function fillForm() {
  if (!profile.value) return;
  form.first_name = profile.value.first_name;
  form.last_name = profile.value.last_name;
  form.phone = profile.value.phone;
  form.job_title = profile.value.job_title;
  form.password = '';
  formError.value = '';
}

function openEdit() {
  fillForm();
  showEdit.value = true;
}

function closeEdit() {
  showEdit.value = false;
  formError.value = '';
}

async function saveProfile() {
  formError.value = '';
  if (!form.first_name.trim()) {
    formError.value = t('errors.enterName');
    return;
  }
  if (!form.phone.trim()) {
    formError.value = t('errors.enterPhone');
    return;
  }

  saving.value = true;
  try {
    const payload: {
      first_name: string;
      last_name: string;
      phone: string;
      job_title: string;
      password?: string;
    } = {
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      phone: form.phone.trim(),
      job_title: form.job_title.trim(),
    };
    if (form.password.trim()) {
      payload.password = form.password;
    }
    await auth.updateProfile(payload);
    closeEdit();
    toast.success(t('toast.saved'));
  } catch (err: unknown) {
    formError.value = apiErrorMessage(err, t('profile.saveFailed'));
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  try {
    await auth.fetchMe();
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <div>
      <h1 class="text-[32px] font-normal text-fb-text">{{ displayName }}</h1>
      <div class="mt-4 inline-block border-b-[3px] border-fb-blue pb-2 text-[13px] font-semibold uppercase tracking-wide text-fb-blue">
        {{ t('profile.title') }}
      </div>
    </div>

    <div v-if="loading" class="rounded-xl border border-fb-line bg-fb-card">
      <SkeletonBlock variant="detail" :rows="3" />
    </div>

    <div v-else-if="profile" class="relative rounded-xl border border-fb-line bg-fb-card px-8 py-10 shadow-sm">
      <div class="absolute right-8 top-8 flex flex-col gap-3">
        <button
          type="button"
          class="flex h-11 w-11 items-center justify-center rounded-full bg-fb-blue text-white hover:opacity-90"
          :title="t('profile.company')"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
            <line x1="4" y1="22" x2="4" y2="15" />
          </svg>
        </button>
        <button
          type="button"
          class="flex h-11 w-11 items-center justify-center rounded-full bg-fb-blue text-white hover:opacity-90"
          :title="t('profile.edit')"
          @click="openEdit"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
        </button>
      </div>

      <div class="mb-8 flex items-start gap-4">
        <div
          class="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-fb-canvas text-xl font-semibold text-fb-icon"
        >
          {{ userInitial }}
        </div>
        <div class="flex-1 pt-2 text-center text-[28px] font-normal text-fb-text">
          {{ profile.first_name || profile.name }}
        </div>
      </div>

      <div class="grid max-w-xl gap-6 text-[16px]">
        <div>
          <p class="mb-1 text-fb-icon">{{ t('common.phone') }}</p>
          <p class="text-fb-text">{{ profile.phone_formatted || profile.phone }}</p>
        </div>

        <div>
          <p class="mb-1 text-fb-icon">{{ t('profile.jobTitle') }}</p>
          <p class="text-fb-text">{{ profile.job_title || '—' }}</p>
        </div>

        <div>
          <p class="mb-2 text-fb-icon">{{ t('profile.roles') }}</p>
          <span class="inline-block rounded-full border border-fb-danger px-4 py-1 text-[14px] font-medium text-fb-danger">
            {{ roleLabel }}
          </span>
        </div>

        <div>
          <p class="mb-2 text-fb-icon">{{ t('profile.branches') }}</p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="branch in profile.branches"
              :key="branch.id"
              class="inline-block rounded-full border border-fb-danger px-4 py-1 text-[14px] font-medium text-fb-danger"
            >
              {{ branch.name }}
            </span>
            <span v-if="!profile.branches.length" class="text-fb-text">—</span>
          </div>
        </div>

        <div>
          <p class="mb-2 text-fb-icon">{{ t('layout.language') }}</p>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="option in localeOptions"
              :key="option.code"
              type="button"
              class="rounded-full border px-4 py-1 text-[14px] font-medium"
              :class="locale === option.code ? 'border-fb-blue bg-fb-hover text-fb-blue' : 'border-fb-line text-fb-secondary hover:border-fb-blue hover:text-fb-blue'"
              :aria-pressed="locale === option.code"
              @click="locale = option.code"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showEdit" class="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4">
      <div class="modal-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4">
          <h2 class="text-xl font-semibold text-fb-text">{{ t('profile.edit') }}</h2>
          <button type="button" class="text-2xl leading-none text-fb-icon hover:text-fb-secondary" :aria-label="t('common.close')" @click="closeEdit">
            ×
          </button>
        </div>

        <form class="space-y-4 px-6 py-5" @submit.prevent="saveProfile">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.firstName') }}</label>
              <input
                v-model="form.first_name"
                type="text"
                required
                class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.lastName') }}</label>
              <input
                v-model="form.last_name"
                type="text"
                class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('common.phone') }}</label>
            <input
              v-model="form.phone"
              type="tel"
              required
              class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('profile.jobTitle') }}</label>
            <input
              v-model="form.job_title"
              type="text"
              :placeholder="t('profile.jobTitlePlaceholder')"
              class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">{{ t('profile.newPassword') }}</label>
            <input
              v-model="form.password"
              type="password"
              :placeholder="t('profile.newPasswordPlaceholder')"
              class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <p v-if="formError" class="text-sm text-fb-danger">{{ formError }}</p>

          <div class="flex justify-end gap-3 pt-2">
            <button
              type="button"
              class="rounded-lg border border-fb-line px-5 py-2 text-sm text-fb-secondary hover:bg-fb-canvas"
              @click="closeEdit"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              type="submit"
              class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
              :disabled="saving"
            >
              {{ saving ? t('common.saving') : t('common.save') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
