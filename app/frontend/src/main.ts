import { createApp } from 'vue';
import { createPinia } from 'pinia';

import App from './App.vue';
import router from './router';
import './style.css';
import './styles/dark-palette.css';
import './ui/theme';

createApp(App).use(createPinia()).use(router).mount('#app');
