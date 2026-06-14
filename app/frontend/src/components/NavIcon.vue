<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  name: string;
  size?: number;
}>();

const iconSize = computed(() => `${props.size ?? 22}px`);

const PNG_MASK_ICONS: Record<string, string> = {
  teachers: '/icons/teacher-mask.png',
  finance: '/icons/finance-mask.png',
  settings: '/icons/settings-mask.png',
  rating: '/icons/rating-mask.png',
};

const PNG_MASK_SCALE: Partial<Record<string, number>> = {
  finance: 1.12,
};

const pngMaskStyle = computed(() => {
  const maskUrl = PNG_MASK_ICONS[props.name];
  if (!maskUrl) return null;

  const scale = PNG_MASK_SCALE[props.name] ?? 1;
  const maskSize = scale === 1 ? 'contain' : `${Math.round(scale * 100)}%`;

  return {
    width: iconSize.value,
    height: iconSize.value,
    WebkitMaskImage: `url(${maskUrl})`,
    maskImage: `url(${maskUrl})`,
    WebkitMaskRepeat: 'no-repeat',
    maskRepeat: 'no-repeat',
    WebkitMaskPosition: 'center',
    maskPosition: 'center',
    WebkitMaskSize: maskSize,
    maskSize,
  };
});

const usesPngMask = computed(() => Boolean(PNG_MASK_ICONS[props.name]));
</script>

<template>
  <span
    v-if="usesPngMask"
    class="inline-block shrink-0 bg-current"
    :style="pngMaskStyle ?? undefined"
    aria-hidden="true"
  />
  <svg
    v-else
    :width="size ?? 22"
    :height="size ?? 22"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.35"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- Groups: stacked layers -->
    <template v-if="name === 'groups'">
      <path d="M12 4L4 8l8 4 8-4-8-4z" />
      <path d="M4 12l8 4 8-4" />
      <path d="M4 16l8 4 8-4" />
    </template>

    <!-- Students: graduation caps -->
    <template v-else-if="name === 'students'">
      <path d="M4 10l8-4 8 4-8 4-8-4z" />
      <path d="M6 12v3c0 1.5 2.7 3 6 3s6-1.5 6-3v-3" />
      <path d="M20 10v3" />
      <path d="M16 8l4-2" />
    </template>

    <!-- Reminders: clock -->
    <template v-else-if="name === 'reminders'">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4l3 2" />
    </template>

    <!-- Reminders: clock -->
    <template v-else-if="name === 'attendance'">
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M8 3v4M16 3v4M4 10h16" />
      <circle cx="9" cy="14" r="1" fill="currentColor" stroke="none" />
      <circle cx="12" cy="14" r="1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="14" r="1" fill="currentColor" stroke="none" />
      <circle cx="9" cy="17" r="1" fill="currentColor" stroke="none" />
      <circle cx="12" cy="17" r="1" fill="currentColor" stroke="none" />
    </template>

    <!-- Reports: pie chart -->
    <template v-else-if="name === 'reports'">
      <path d="M12 3v9h9a9 9 0 00-9-9z" />
      <circle cx="12" cy="12" r="9" />
    </template>

    <!-- Reports: pie chart -->
    <template v-else-if="name === 'leads'">
      <path d="M16 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
      <circle cx="10" cy="8" r="4" />
      <path d="M19 8v6M22 11h-6" />
    </template>

    <!-- Dashboard -->
    <template v-else-if="name === 'dashboard'">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </template>

    <!-- Coins (payments / withdraw) -->
    <template v-else-if="name === 'coins'">
      <ellipse cx="12" cy="8" rx="6" ry="2.5" />
      <path d="M6 8v4c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V8" />
      <ellipse cx="12" cy="14" rx="6" ry="2.5" />
      <path d="M6 14v3c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5v-3" />
    </template>

    <!-- Expenses pie -->
    <template v-else-if="name === 'expenses'">
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4v8l6 4" />
    </template>

    <!-- Salaries scroll -->
    <template v-else-if="name === 'salaries'">
      <path d="M8 4h10a2 2 0 012 2v14l-4-2-4 2-4-2-4 2V6a2 2 0 012-2z" />
      <path d="M10 8h6M10 12h6" />
    </template>

    <!-- Debtors warning -->
    <template v-else-if="name === 'debtors'">
      <path d="M12 4l9 16H3L12 4z" />
      <path d="M12 10v4M12 18h.01" />
    </template>

    <!-- Conversion -->
    <template v-else-if="name === 'conversion'">
      <path d="M4 18V6M4 18h16M8 14l3-3 3 2 4-5" />
    </template>

    <!-- Leads report -->
    <template v-else-if="name === 'leads-report'">
      <path d="M4 6h16M4 12h10M4 18h14" />
      <circle cx="18" cy="12" r="2" />
    </template>

    <!-- Staff -->
    <template v-else-if="name === 'staff'">
      <path d="M17 21v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2" />
      <circle cx="10" cy="8" r="4" />
      <path d="M20 8v6M23 11h-6" />
    </template>

    <!-- Courses -->
    <template v-else-if="name === 'courses'">
      <path d="M4 6h16v12H4z" />
      <path d="M8 6V4h8v2" />
      <path d="M8 10h8M8 14h5" />
    </template>

    <!-- Rooms -->
    <template v-else-if="name === 'rooms'">
      <path d="M4 10h16v10H4z" />
      <path d="M2 20h20M9 10V6h6v4" />
    </template>

    <!-- Holidays -->
    <template v-else-if="name === 'holidays'">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2" />
    </template>

    <!-- Archive -->
    <template v-else-if="name === 'archive'">
      <rect x="4" y="6" width="16" height="14" rx="1" />
      <path d="M8 6V4h8v2M10 11h4" />
    </template>

    <!-- Tags -->
    <template v-else-if="name === 'tags'">
      <path d="M4 12l8-8h6v6l-8 8-6-6z" />
      <circle cx="14" cy="6" r="1" fill="currentColor" stroke="none" />
    </template>

    <!-- Forms -->
    <template v-else-if="name === 'forms'">
      <path d="M6 4h12v16H6z" />
      <path d="M9 8h6M9 12h6M9 16h4" />
    </template>

    <!-- Billing -->
    <template v-else-if="name === 'billing'">
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <path d="M3 10h18" />
    </template>

    <!-- SMS -->
    <template v-else-if="name === 'sms'">
      <path d="M4 6h16v10H8l-4 4V6z" />
      <path d="M8 10h8" />
    </template>

    <!-- Call -->
    <template v-else-if="name === 'call'">
      <path d="M6 4h4l2 5-3 2a11 11 0 005 5l2-3 5 2v4a2 2 0 01-2 2A15 15 0 014 6a2 2 0 012-2z" />
    </template>

    <!-- Logs -->
    <template v-else-if="name === 'logs'">
      <path d="M6 4h12v16H6z" />
      <path d="M9 8h6M9 12h6M9 16h4" />
      <path d="M4 8h2M4 12h2M4 16h2" />
    </template>

    <!-- Auto SMS -->
    <template v-else-if="name === 'auto-sms'">
      <path d="M4 6h16v8H8l-4 4V6z" />
      <circle cx="17" cy="7" r="3" />
      <path d="M16 7h2M17 6v2" />
    </template>

    <!-- VoIP headset -->
    <template v-else-if="name === 'voip'">
      <path d="M4 14v-2a8 8 0 0116 0v2" />
      <path d="M6 14v2a2 2 0 002 2h1M18 14v2a2 2 0 01-2 2h-1" />
      <path d="M10 20h4" />
    </template>

    <!-- Grade star -->
    <template v-else-if="name === 'grade'">
      <path d="M12 3l2.6 5.8 6.4.6-4.8 4.2 1.4 6.2L12 17.8 6.4 20.8l1.4-6.2L3 9.4l6.4-.6L12 3z" />
    </template>

    <!-- Roadmap rocket -->
    <template v-else-if="name === 'roadmap'">
      <path d="M12 3c3 4 4 8 4 12-2 0-3-1-4-2-1 1-2 2-4 2 0-4 1-8 4-12z" />
      <circle cx="12" cy="11" r="1.5" fill="currentColor" stroke="none" />
      <path d="M8 19l2-2M16 19l-2-2" />
    </template>

    <!-- Left students -->
    <template v-else-if="name === 'left-students'">
      <path d="M4 10l8-4 8 4-8 4-8-4z" />
      <path d="M8 14v3M16 14v3" />
      <path d="M6 20h12" />
    </template>

    <!-- Blog -->
    <template v-else-if="name === 'blog'">
      <path d="M6 4h12v16H6z" />
      <path d="M9 8h6M9 12h6M9 16h4" />
      <path d="M4 8h2M4 12h2" />
    </template>

    <!-- Puzzle / forms -->
    <template v-else-if="name === 'puzzle'">
      <path d="M8 4h3a2 2 0 014 0h3v3a2 2 0 010 4v3H8v-3a2 2 0 010-4V4z" />
    </template>

    <!-- Fallback -->
    <template v-else>
      <circle cx="12" cy="12" r="8" />
    </template>
  </svg>
</template>
