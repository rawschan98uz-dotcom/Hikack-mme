import axios from 'axios';

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
  (response) => response,
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

export interface ApiEnvelope<T> {
  status: number;
  success: boolean;
  data: T;
  message?: string;
}

export default client;
