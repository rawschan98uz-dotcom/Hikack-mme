/**
 * API Client — добавлена поддержка пагинации
 */

import axios from 'axios';
import { useAuthStore } from '@/stores/auth';

const BASE_URL = import.meta.env.VITE_API_URL || '/v1';

export interface PaginatedResponse<T> {
  count: number;
  has_more: boolean;
  next_offset: number | null;
  results: T[];
}

export interface ApiEnvelope<T> {
  status: number;
  success: boolean;
  data: T;
  message?: string;
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  let authHeaders: Record<string, string> = {};
  try {
    const authStore = useAuthStore();
    if (authStore && typeof authStore.getAuthHeaders === 'function') {
      authHeaders = authStore.getAuthHeaders();
    }
  } catch {
    const token = localStorage.getItem('access_token');
    if (token) {
      authHeaders = { Authorization: `Bearer ${token}` };
    }
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...authHeaders,
    ...(options.headers as Record<string, string>),
  };

  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: 'same-origin',
  });

  if (response.status === 401) {
    localStorage.removeItem('access_token');
    try {
      const authStore = useAuthStore();
      authStore.logout();
    } catch {
      // ignore
    }
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data?.detail || data?.error || `HTTP ${response.status}`);
  }

  return response.json();
}

// ═══ ПАГИНИРОВАННЫЙ ЗАПРОС ═══

export async function apiPaginated<T = any>(
  endpoint: string,
  params: Record<string, string> = {},
  page: { offset?: number; limit?: number } = {},
): Promise<PaginatedResponse<T>> {
  const searchParams = new URLSearchParams({
    ...params,
    offset: String(page.offset ?? 0),
    limit: String(page.limit ?? 200),
  });

  const raw = await apiRequest<any>(
    `${endpoint}?${searchParams.toString()}`,
  );

  if (raw && typeof raw === 'object' && raw.data && 'results' in raw.data) {
    return raw.data as PaginatedResponse<T>;
  }
  return raw as PaginatedResponse<T>;
}

// ═══ CONVENIENCE METHODS ═══

export const api = {
  get: <T>(endpoint: string) => apiRequest<T>(endpoint),
  post: <T>(endpoint: string, body?: any) =>
    apiRequest<T>(endpoint, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(endpoint: string, body?: any) =>
    apiRequest<T>(endpoint, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(endpoint: string) =>
    apiRequest<T>(endpoint, { method: 'DELETE' }),
  paginated: <T>(
    endpoint: string,
    params?: Record<string, string>,
    page?: { offset?: number; limit?: number },
  ) => apiPaginated<T>(endpoint, params, page),
};

// ═══ AXIOS CLIENT (FOR BACKWARD COMPATIBILITY) ═══

const client = axios.create({
  baseURL: '/v1',
  headers: { 'Content-Type': 'application/json' },
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => {
    // Gracefully handle paginated response { count, has_more, next_offset, results }
    // so that legacy views expecting an Array still work seamlessly
    if (
      response.data &&
      response.data.data &&
      typeof response.data.data === 'object' &&
      !Array.isArray(response.data.data) &&
      Array.isArray(response.data.data.results)
    ) {
      const pageData = response.data.data;
      const list = pageData.results.slice();
      (list as any).count = pageData.count;
      (list as any).has_more = pageData.has_more;
      (list as any).next_offset = pageData.next_offset;
      (list as any).results = pageData.results;
      response.data.data = list;
    }
    return response;
  },
  (error) => {
    const status = error.response?.status;
    const isAuthRequest = String(error.config?.url ?? '').includes('/auth/login');
    if (status === 401 && !isAuthRequest) {
      localStorage.removeItem('access_token');
      if (!window.location.pathname.startsWith('/login')) {
        window.location.assign('/login');
      }
    }
    return Promise.reject(error);
  },
);

export default client;
