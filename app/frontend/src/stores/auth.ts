import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { hasPermission } from '../utils/rbac';

export interface Company {
  id: number;
  name: string;
  subdomain: string;
  balance_mode: number;
  payment_mode_label: string;
}

export interface BranchRef {
  id: number;
  name: string;
}

export interface AuthUser {
  id: number;
  name: string;
  first_name: string;
  last_name: string;
  phone: string;
  phone_formatted: string;
  user_type: string;
  staff_role: string | null;
  role: string;
  job_title: string;
  role_label: string;
  permissions: string[];
  branches: BranchRef[];
  company: Company | null;
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null);
  const token = ref<string | null>(localStorage.getItem('access_token'));
  const loading = ref(false);
  const error = ref('');

  const permissions = computed(() => user.value?.permissions ?? []);
  const role = computed(() => user.value?.role ?? '');
  const isCeo = computed(() => role.value === 'ceo');

  function can(permission: string): boolean {
    if (isCeo.value) return true;
    return hasPermission(permissions.value, permission);
  }

  async function login(phone: string, password: string) {
    loading.value = true;
    error.value = '';
    try {
      const { data } = await client.post<ApiEnvelope<{ access: string; user: AuthUser }>>(
        '/auth/login',
        { phone, password },
      );
      token.value = data.data.access;
      user.value = data.data.user;
      localStorage.setItem('access_token', data.data.access);
    } catch (e: unknown) {
      error.value = 'Invalid phone or password';
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function fetchMe() {
    if (!token.value) return;
    const { data } = await client.post<ApiEnvelope<AuthUser>>('/auth/me');
    user.value = data.data;
  }

  async function updateProfile(payload: {
    first_name?: string;
    last_name?: string;
    job_title?: string;
    phone?: string;
    password?: string;
  }) {
    const { data } = await client.patch<ApiEnvelope<AuthUser>>('/auth/me', payload);
    user.value = data.data;
    return data.data;
  }

  function logout() {
    user.value = null;
    token.value = null;
    localStorage.removeItem('access_token');
  }

  function syncTokenFromStorage() {
    token.value = localStorage.getItem('access_token');
    if (!token.value) {
      user.value = null;
    }
  }

  return {
    user,
    token,
    loading,
    error,
    permissions,
    role,
    isCeo,
    can,
    login,
    fetchMe,
    updateProfile,
    logout,
    syncTokenFromStorage,
  };
});
