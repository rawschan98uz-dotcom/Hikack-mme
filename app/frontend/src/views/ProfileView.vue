<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import { useAuthStore } from '../stores/auth';

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
const displayName = computed(() => profile.value?.first_name || profile.value?.name || 'Profile');
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
    formError.value = 'Enter first name';
    return;
  }
  if (!form.phone.trim()) {
    formError.value = 'Enter phone number';
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
  } catch {
    formError.value = 'Could not save profile. Check phone is unique.';
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
        Profile
      </div>
    </div>

    <div v-if="loading" class="rounded-xl border border-fb-line bg-fb-card p-10 text-center text-fb-secondary">
      Loading…
    </div>

    <div v-else-if="profile" class="relative rounded-xl border border-fb-line bg-fb-card px-8 py-10 shadow-sm">
      <div class="absolute right-8 top-8 flex flex-col gap-3">
        <button
          type="button"
          class="flex h-11 w-11 items-center justify-center rounded-full bg-fb-blue text-white hover:opacity-90"
          title="Company"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
            <line x1="4" y1="22" x2="4" y2="15" />
          </svg>
        </button>
        <button
          type="button"
          class="flex h-11 w-11 items-center justify-center rounded-full bg-fb-blue text-white hover:opacity-90"
          title="Edit profile"
          @click="openEdit"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
        </button>
        <button
          type="button"
          disabled
          title="Delete account (disabled)"
          class="flex h-11 w-11 cursor-not-allowed items-center justify-center rounded-full bg-fb-danger text-white opacity-60"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 7h16M9 7V5h6v2M7 7l1 14h8l1-14" />
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
          <p class="mb-1 text-fb-icon">Phone</p>
          <p class="text-fb-text">{{ profile.phone_formatted || profile.phone }}</p>
        </div>

        <div>
          <p class="mb-1 text-fb-icon">Job title</p>
          <p class="text-fb-text">{{ profile.job_title || '—' }}</p>
        </div>

        <div>
          <p class="mb-2 text-fb-icon">Roles</p>
          <span class="inline-block rounded-full border border-fb-danger px-4 py-1 text-[14px] font-medium text-fb-danger">
            {{ profile.role_label }}
          </span>
        </div>

        <div>
          <p class="mb-2 text-fb-icon">Branches</p>
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
      </div>
    </div>

    <div v-if="showEdit" class="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4">
      <div class="modal-panel-fb max-w-lg">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-4">
          <h2 class="text-xl font-semibold text-fb-text">Edit profile</h2>
          <button type="button" class="text-2xl leading-none text-fb-icon hover:text-fb-secondary" @click="closeEdit">
            ×
          </button>
        </div>

        <form class="space-y-4 px-6 py-5" @submit.prevent="saveProfile">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">First name</label>
              <input
                v-model="form.first_name"
                type="text"
                required
                class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
              />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium text-fb-secondary">Last name</label>
              <input
                v-model="form.last_name"
                type="text"
                class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Phone</label>
            <input
              v-model="form.phone"
              type="tel"
              required
              class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">Job title</label>
            <input
              v-model="form.job_title"
              type="text"
              placeholder="e.g. Founder"
              class="w-full rounded-lg border border-fb-line px-3 py-2 focus:border-fb-blue focus:outline-none"
            />
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-fb-secondary">New password (optional)</label>
            <input
              v-model="form.password"
              type="password"
              placeholder="Leave blank to keep current"
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
              Cancel
            </button>
            <button
              type="submit"
              class="rounded-lg bg-fb-blue px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
              :disabled="saving"
            >
              {{ saving ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
