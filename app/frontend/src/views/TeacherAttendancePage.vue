<script setup lang="ts">
import { useAuthStore } from '../stores/auth';
import MyAttendanceView from './MyAttendanceView.vue';
import TeacherAttendanceReportsView from './TeacherAttendanceReportsView.vue';

// A teacher sees only own attendance calendar; office staff keep the full report
const auth = useAuthStore();
</script>

<template>
  <MyAttendanceView v-if="auth.role === 'teacher'" />
  <TeacherAttendanceReportsView v-else />
</template>
