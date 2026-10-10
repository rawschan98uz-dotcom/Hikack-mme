<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';

import { locale, localeOptions, t } from '../i18n';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const router = useRouter();
// Fields start empty: no demo accounts or credentials on the login page
const phone = ref('');
const password = ref('');

async function submit() {
  try {
    await auth.login(phone.value, password.value);
    await router.push('/dashboard/default');
  } catch {
    /* error shown in store */
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-fb-canvas px-4">
    <form
      class="w-full max-w-md rounded-xl border border-fb-line bg-fb-card p-8 shadow-fb-card space-y-5"
      @submit.prevent="submit"
    >
      <div class="flex justify-center gap-1" role="group" :aria-label="t('layout.language')">
        <button
          v-for="option in localeOptions"
          :key="option.code"
          type="button"
          class="rounded-full px-3 py-1 text-sm"
          :class="locale === option.code ? 'bg-fb-hover font-semibold text-fb-blue' : 'text-fb-secondary hover:bg-fb-canvas'"
          :aria-pressed="locale === option.code"
          @click="locale = option.code"
        >
          {{ option.label }}
        </button>
      </div>

      <div class="text-center">
        <h1 class="text-2xl font-bold text-fb-blue">Hi Jack LMS</h1>
        <p class="text-sm text-fb-secondary mt-1">{{ t('login.subtitle') }}</p>
      </div>

      <div>
        <label class="block text-sm font-medium text-fb-secondary mb-1">{{ t('common.phone') }}</label>
        <input
          v-model="phone"
          type="tel"
          name="username"
          autocomplete="username"
          required
          class="w-full rounded-lg border border-fb-line px-3 py-2 focus:outline-none focus:ring-2 focus:ring-fb-blue/30 focus:border-fb-blue"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-fb-secondary mb-1">{{ t('login.password') }}</label>
        <input
          v-model="password"
          type="password"
          name="password"
          autocomplete="current-password"
          required
          class="w-full rounded-lg border border-fb-line px-3 py-2 focus:outline-none focus:ring-2 focus:ring-fb-blue/30 focus:border-fb-blue"
        />
      </div>

      <p v-if="auth.error" class="text-sm text-fb-danger">{{ auth.error }}</p>

      <button
        type="submit"
        class="w-full rounded-lg bg-fb-blue hover:bg-fb-blue-dark text-white font-semibold py-2.5 disabled:opacity-60"
        :disabled="auth.loading"
      >
        {{ auth.loading ? t('login.signingIn') : t('login.signIn') }}
      </button>
    </form>
  </div>
</template>
