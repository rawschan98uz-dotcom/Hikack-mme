<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';

import AppLogo from '../components/AppLogo.vue';
import { locale, localeOptions, t, type MessageKey } from '../i18n';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const router = useRouter();
// Fields start empty: no demo accounts or credentials on the login page
const HERO_POINTS: MessageKey[] = ['login.point1', 'login.point2', 'login.point3'];

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
  <div class="flex min-h-screen bg-fb-canvas">
    <!-- Brand side: only on wide screens -->
    <aside class="login-hero relative hidden w-[46%] max-w-[640px] flex-col justify-between overflow-hidden p-12 text-white lg:flex">
      <AppLogo :size="44" inverse />
      <div class="relative z-10 max-w-md">
        <h2 class="text-[34px] font-bold leading-tight">{{ t('login.heroTitle') }}</h2>
        <p class="mt-4 text-[17px] leading-relaxed text-indigo-100">{{ t('login.heroText') }}</p>
        <ul class="mt-8 space-y-3 text-[16px] text-indigo-50">
          <li v-for="key in HERO_POINTS" :key="key" class="flex items-start gap-3">
            <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/15" aria-hidden="true">✓</span>
            <span>{{ t(key) }}</span>
          </li>
        </ul>
      </div>
      <p class="relative z-10 text-sm text-indigo-200">© HiJack LMS</p>
    </aside>

    <!-- Sign-in form -->
    <div class="flex flex-1 items-center justify-center px-4 py-10">
      <form class="w-full max-w-[400px] space-y-5" @submit.prevent="submit">
        <div class="flex justify-center lg:hidden">
          <AppLogo :size="44" />
        </div>

        <div>
          <h1 class="text-[28px] font-bold text-fb-text">{{ t('login.welcome') }}</h1>
          <p class="mt-1 text-[15px] text-fb-secondary">{{ t('login.subtitle') }}</p>
        </div>

        <div>
          <label class="mb-1 block text-sm font-medium text-fb-secondary" for="login-phone">{{ t('common.phone') }}</label>
          <input
            id="login-phone"
            v-model="phone"
            type="tel"
            name="username"
            autocomplete="username"
            required
            class="input-fb h-12"
          />
        </div>

        <div>
          <label class="mb-1 block text-sm font-medium text-fb-secondary" for="login-password">{{ t('login.password') }}</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            name="password"
            autocomplete="current-password"
            required
            class="input-fb h-12"
          />
        </div>

        <p v-if="auth.error" class="rounded-lg bg-red-50 px-3 py-2 text-sm text-fb-danger">{{ auth.error }}</p>

        <button
          type="submit"
          class="h-12 w-full rounded-lg bg-fb-blue font-semibold text-white hover:bg-fb-blue-dark disabled:opacity-60"
          :disabled="auth.loading"
        >
          {{ auth.loading ? t('login.signingIn') : t('login.signIn') }}
        </button>

        <div class="flex justify-center gap-1 pt-2" role="group" :aria-label="t('layout.language')">
          <button
            v-for="option in localeOptions"
            :key="option.code"
            type="button"
            class="rounded-full px-3 py-1 text-sm"
            :class="locale === option.code ? 'bg-fb-hover font-semibold text-fb-blue' : 'text-fb-secondary hover:bg-fb-card'"
            :aria-pressed="locale === option.code"
            @click="locale = option.code"
          >
            {{ option.label }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-hero {
  background:
    radial-gradient(circle at 85% 15%, rgb(255 255 255 / 0.14) 0, transparent 38%),
    radial-gradient(circle at 10% 90%, rgb(139 92 246 / 0.45) 0, transparent 45%),
    linear-gradient(150deg, #4f46e5 0%, #4338ca 55%, #3730a3 100%);
}
</style>
