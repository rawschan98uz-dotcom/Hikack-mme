<script setup lang="ts">

import { ref } from 'vue';

import { useRouter } from 'vue-router';



import { useAuthStore } from '../stores/auth';



interface DemoAccount {

  label: string;

  role: string;

  phone: string;

  password: string;

}



const demoAccounts: DemoAccount[] = [

  { label: 'CEO', role: 'Full access', phone: '903708242', password: '50608991Zz!' },

  { label: 'Teacher', role: 'Own groups & students', phone: '901001001', password: 'demo1234' },

  { label: 'Administrator', role: 'Office operations', phone: '901002001', password: 'demo1234' },

  { label: 'Marketer', role: 'Leads only', phone: '901002002', password: 'demo1234' },

  { label: 'Cashier', role: 'Students & finance', phone: '901002003', password: 'demo1234' },

];



const auth = useAuthStore();

const router = useRouter();

const phone = ref('903708242');

const password = ref('50608991Zz!');

const selectedDemo = ref('CEO');



function applyDemo(account: DemoAccount) {

  selectedDemo.value = account.label;

  phone.value = account.phone;

  password.value = account.password;

}



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

      <div class="text-center">

        <h1 class="text-2xl font-bold text-fb-blue">Hi Jack LMS</h1>

        <p class="text-sm text-fb-secondary mt-1">Sign in — your role depends on the account</p>

      </div>



      <div class="rounded-lg border border-fb-line bg-fb-canvas/60 p-3 space-y-2">

        <p class="text-xs font-semibold uppercase tracking-wide text-fb-icon">Demo accounts</p>

        <div class="flex flex-wrap gap-2">

          <button

            v-for="account in demoAccounts"

            :key="account.label"

            type="button"

            class="rounded-md border px-2.5 py-1.5 text-xs transition-colors"

            :class="selectedDemo === account.label

              ? 'border-fb-blue bg-fb-blue/10 text-fb-blue font-semibold'

              : 'border-fb-line text-fb-secondary hover:border-fb-blue/40'"

            @click="applyDemo(account)"

          >

            {{ account.label }}

          </button>

        </div>

        <p class="text-xs text-fb-icon">

          {{ demoAccounts.find((a) => a.label === selectedDemo)?.role }}

        </p>

      </div>



      <div>

        <label class="block text-sm font-medium text-fb-secondary mb-1">Phone</label>

        <input

          v-model="phone"

          type="tel"

          required

          class="w-full rounded-lg border border-fb-line px-3 py-2 focus:outline-none focus:ring-2 focus:ring-fb-blue/30 focus:border-fb-blue"

        />

      </div>



      <div>

        <label class="block text-sm font-medium text-fb-secondary mb-1">Password</label>

        <input

          v-model="password"

          type="password"

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

        {{ auth.loading ? 'Signing in…' : 'Sign in' }}

      </button>

    </form>

  </div>

</template>

