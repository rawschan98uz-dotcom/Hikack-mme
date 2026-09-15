<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import client, { type ApiEnvelope } from '../api/client';
import ImportCsvModal from '../components/ImportCsvModal.vue';
import { useAuthStore } from '../stores/auth';
import { PERM } from '../utils/rbac';
import {
  groupRoute,
  groupsByTeacher,
  hasCreateFlag,
  parseOpenId,
  routeWithoutCreate,
  routeWithoutOpen,
} from '../utils/crossLinks';

interface Branch {
  id: number;
  name: string;
}

interface TeacherGroup {
  id: number;
  name: string;
  course: string;
  branch: string;
  days_label: string;
}

interface Teacher {
  id: number;
  name: string;
  first_name: string;
  last_name: string;
  honorific: string;
  job_title: string;
  phone: string;
  phone_formatted: string;
  groups_count: number;
  groups_label: string;
  branches: Branch[];
  groups?: TeacherGroup[];
}

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const teachers = ref<Teacher[]>([]);
const branches = ref<Branch[]>([]);
const loading = ref(true);
const saving = ref(false);
const showModal = ref(false);
const formError = ref('');
const openMenuId = ref<number | null>(null);
const editingTeacher = ref<Teacher | null>(null);
const showProfile = ref(false);
const profileLoading = ref(false);
const profileTeacher = ref<Teacher | null>(null);
const showImportModal = ref(false);
const showPasswordModal = ref(false);
const generatedPassword = ref('');
const generatedTeacherName = ref('');
const passwordCopied = ref(false);

const searchQuery = ref('');
const selectedBranch = ref('');

const canImportTeachers = computed(() => auth.can(PERM.TEACHERS_WRITE));
const canCreateTeacher = computed(() => auth.can(PERM.TEACHERS_WRITE));
const canEditTeacher = computed(() => auth.can(PERM.TEACHERS_WRITE));

function canDeleteTeacher(teacher: Teacher | null): boolean {
  if (!teacher) return false;
  if (!auth.isCeo) return false;
  return teacher.id !== auth.user?.id;
}

const form = reactive({
  honorific: 'Mr',
  first_name: '',
  last_name: '',
  job_title: '',
  phone: '',
  password: '',
  branches: [] as number[],
});

const filteredTeachers = computed(() => {
  let list = teachers.value;
  if (selectedBranch.value) {
    const branchId = Number(selectedBranch.value);
    list = list.filter((t) => t.branches.some((b) => b.id === branchId));
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase();
    list = list.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.phone.includes(q) ||
        (t.job_title && t.job_title.toLowerCase().includes(q)),
    );
  }
  return list;
});

const quantity = computed(() => filteredTeachers.value.length);
const totalQuantity = computed(() => teachers.value.length);
const modalTitle = computed(() => (editingTeacher.value ? 'Edit teacher' : 'Add teacher'));

const honorifics = ['Mr', 'Ms', 'Mrs'];

function resetForm() {
  form.honorific = 'Mr';
  form.first_name = '';
  form.last_name = '';
  form.job_title = '';
  form.phone = '';
  form.password = '';
  form.branches = branches.value.length ? [branches.value[0].id] : [];
  formError.value = '';
  editingTeacher.value = null;
}

function openModal(teacher?: Teacher) {
  resetForm();
  if (teacher) {
    editingTeacher.value = teacher;
    form.honorific = teacher.honorific || 'Mr';
    form.first_name = teacher.first_name;
    form.last_name = teacher.last_name;
    form.job_title = teacher.job_title || '';
    form.phone = teacher.phone;
    form.branches = teacher.branches.map((b) => b.id);
    if (!form.branches.length && branches.value.length) {
      form.branches = [branches.value[0].id];
    }
  }
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
  formError.value = '';
  editingTeacher.value = null;
}

function toggleBranch(branchId: number) {
  if (!auth.isCeo) return;
  const idx = form.branches.indexOf(branchId);
  if (idx >= 0) {
    if (form.branches.length > 1) {
      form.branches.splice(idx, 1);
    }
  } else {
    form.branches.push(branchId);
  }
}

function toggleMenu(teacherId: number) {
  openMenuId.value = openMenuId.value === teacherId ? null : teacherId;
}

function closeMenu() {
  openMenuId.value = null;
}

function onDocumentClick(event: MouseEvent) {
  const target = event.target as HTMLElement;
  if (!target.closest('[data-teacher-menu]')) {
    closeMenu();
  }
}

async function loadTeachers() {
  const { data } = await client.get<ApiEnvelope<Teacher[]>>('/user', {
    params: { user_type: 'teacher' },
  });
  teachers.value = data.data;
}

async function loadBranches() {
  const { data } = await client.get<ApiEnvelope<Branch[]>>('/branch');
  branches.value = data.data;
}

onMounted(async () => {
  document.addEventListener('click', onDocumentClick);
  try {
    await Promise.all([loadTeachers(), loadBranches()]);
    await maybeOpenFromRoute();
    maybeCreateFromRoute();
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick);
});

async function submitTeacher() {
  formError.value = '';
  if (!form.first_name.trim() || !form.phone.trim()) {
    formError.value = 'Fill in first name and phone';
    return;
  }
  if (!form.branches.length) {
    formError.value = 'Select at least one branch';
    return;
  }

  saving.value = true;
  try {
    const payload: Record<string, unknown> = {
      honorific: form.honorific,
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      job_title: form.job_title.trim(),
      phone: form.phone.trim(),
    };
    if (auth.isCeo || !editingTeacher.value) {
      payload.branches = form.branches;
    }

    if (editingTeacher.value) {
      // Only CEO can change password
      if (form.password.trim() && auth.isCeo) {
        payload.password = form.password;
      }
      const teacherId = editingTeacher.value.id;
      await client.patch(`/user/teacher/${teacherId}`, payload);
      await loadTeachers();
      closeModal();
      if (showProfile.value && profileTeacher.value?.id === teacherId) {
        await openProfile({ id: teacherId } as Teacher);
      }
    } else {
      // Create — password auto-generated on backend
      const { data } = await client.post<ApiEnvelope<any>>('/user/teacher', payload);
      const created = data.data;
      await loadTeachers();
      closeModal();
      // Show generated password
      if (created.generated_password) {
        generatedTeacherName.value = created.name || `${form.first_name} ${form.last_name}`.trim();
        generatedPassword.value = created.generated_password;
        passwordCopied.value = false;
        showPasswordModal.value = true;
      }
    }
  } catch (err: any) {
    formError.value =
      err.response?.data?.message ||
      err.response?.data?.error ||
      (editingTeacher.value ? 'Could not update teacher.' : 'Could not create teacher.');
  } finally {
    saving.value = false;
  }
}

async function copyPassword() {
  try {
    await navigator.clipboard.writeText(generatedPassword.value);
    passwordCopied.value = true;
  } catch {
    // Fallback for older browsers
    const textarea = document.createElement('textarea');
    textarea.value = generatedPassword.value;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    passwordCopied.value = true;
  }
}

async function deleteTeacher(teacher: Teacher) {
  closeMenu();
  if (!canDeleteTeacher(teacher)) return;
  if (!window.confirm(`Delete ${teacher.name}?`)) return;
  try {
    await client.delete(`/user/teacher/${teacher.id}`);
    if (profileTeacher.value?.id === teacher.id) {
      closeProfile();
    }
    await loadTeachers();
  } catch (err: any) {
    window.alert(err.response?.data?.message || 'Could not delete teacher');
  }
}

async function archiveTeacher(teacher: Teacher) {
  closeMenu();
  if (!window.confirm(`Move teacher "${teacher.name}" to archive?`)) return;
  try {
    await client.post('/archive/list', {
      name: teacher.name,
      phone: teacher.phone,
      roles: 'teacher',
      reason: 'Archived from teachers directory',
    });
    // Deactivate the user account so they can no longer log in
    try {
      await client.patch(`/user/teacher/${teacher.id}`, { is_active: false });
    } catch {
      // Archive record was created; deactivation is best-effort
    }
    if (profileTeacher.value?.id === teacher.id) {
      closeProfile();
    }
    await loadTeachers();
  } catch (err: any) {
    window.alert(err.response?.data?.message || 'Could not archive teacher');
  }
}

function editTeacher(teacher: Teacher) {
  closeMenu();
  closeProfile();
  openModal(teacher);
}

async function openProfile(teacher: Teacher) {
  closeMenu();
  showProfile.value = true;
  profileLoading.value = true;
  profileTeacher.value = null;
  try {
    const { data } = await client.get<ApiEnvelope<Teacher>>(`/user/teacher/${teacher.id}`);
    profileTeacher.value = data.data;
  } finally {
    profileLoading.value = false;
  }
}

function closeProfile() {
  showProfile.value = false;
  profileTeacher.value = null;
  if (route.query.open) {
    router.replace(routeWithoutOpen(route));
  }
}

function goGroups(teacher?: Teacher) {
  const id = teacher?.id ?? profileTeacher.value?.id;
  if (id) {
    router.push(groupsByTeacher(id));
    return;
  }
  router.push('/groups');
}

function goGroup(groupId: number) {
  router.push(groupRoute(groupId));
}

async function maybeOpenFromRoute() {
  const id = parseOpenId(route.query);
  if (id == null || showProfile.value) return;
  await openProfile({ id } as Teacher);
}

function maybeCreateFromRoute() {
  if (!hasCreateFlag(route.query) || showModal.value || !canCreateTeacher.value) return;
  openModal();
  router.replace(routeWithoutCreate(route));
}

watch(
  () => route.fullPath,
  async () => {
    await maybeOpenFromRoute();
    maybeCreateFromRoute();
  },
);
</script>

<template>
  <div class="space-y-5">
    <!-- Page header -->
    <div class="flex items-start justify-between gap-4">
      <div class="flex items-baseline gap-3 flex-wrap">
        <h1 class="!mb-0">Teachers</h1>
        <span class="text-[18px] text-fb-secondary font-normal">
          Quantity — {{ quantity }}<span v-if="quantity !== totalQuantity"> of {{ totalQuantity }}</span>
        </span>
      </div>
      <div class="flex gap-3 shrink-0">
        <button
          v-if="canImportTeachers"
          type="button"
          class="px-5 py-2.5 rounded-lg border border-fb-blue text-fb-blue text-[15px] font-semibold bg-fb-card hover:bg-fb-hover flex items-center gap-2"
          @click="showImportModal = true"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 8v8m0 0l-4-4m4 4l4-4M4 20h16" />
          </svg>
          Import
        </button>
        <button
          v-if="canCreateTeacher"
          type="button"
          class="px-6 py-2.5 rounded-lg bg-fb-blue text-white text-[15px] font-bold hover:opacity-90"
          @click="openModal()"
        >
          ADD NEW
        </button>
      </div>
    </div>

    <!-- Filters & Search -->
    <div class="flex flex-wrap items-center gap-3">
      <div class="relative flex-1 min-w-[220px]">
        <input
          v-model="searchQuery"
          type="search"
          placeholder="Search by name, phone or title…"
          class="w-full h-11 pl-10 pr-4 rounded-xl border border-fb-line bg-fb-card text-[15px] focus:outline-none focus:border-fb-blue"
        />
        <svg class="absolute left-3.5 top-3 text-fb-secondary" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
      </div>
      <select
        v-model="selectedBranch"
        class="h-11 px-4 rounded-xl border border-fb-line bg-fb-card text-[15px] text-fb-text focus:outline-none focus:border-fb-blue"
      >
        <option value="">All branches</option>
        <option v-for="b in branches" :key="b.id" :value="String(b.id)">{{ b.name }}</option>
      </select>
    </div>

    <!-- CEO attention banner -->
    <div v-if="auth.isCeo" class="rounded-xl border border-fb-line bg-fb-hover px-5 py-4 flex gap-4 items-start">
      <div class="w-10 h-10 rounded-full bg-fb-blue flex items-center justify-center shrink-0">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
          <path d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <div>
        <div class="text-fb-text font-bold text-[17px]">Attention!</div>
        <p class="text-fb-secondary text-[16px] mt-1">
          CEO profiles can link teachers to other branches.
        </p>
      </div>
    </div>

    <!-- Teacher list -->
    <div v-if="loading" class="text-fb-secondary text-[16px] py-8">Loading…</div>
    <div v-else-if="!filteredTeachers.length" class="rounded-xl border border-fb-line bg-fb-card p-10 text-center text-fb-icon text-[16px]">
      {{ teachers.length ? 'No teachers match your search.' : 'No teachers yet. Click ADD NEW to create one.' }}
    </div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div
        v-for="teacher in filteredTeachers"
        :key="teacher.id"
        class="relative rounded-xl border border-fb-line bg-fb-card px-5 py-4 flex items-center gap-4 hover:border-fb-line transition-colors shadow-sm overflow-visible cursor-pointer"
        @click="openProfile(teacher)"
      >
        <div class="shrink-0 w-[32%] truncate">
          <div class="text-[17px] font-semibold text-fb-text truncate">{{ teacher.name }}</div>
          <div v-if="teacher.job_title" class="text-[13px] text-fb-secondary truncate font-normal">
            {{ teacher.job_title }}
          </div>
        </div>
        <div class="text-[15px] text-fb-blue font-medium shrink-0 w-[30%] truncate">
          {{ teacher.phone_formatted || teacher.phone }}
        </div>
        <div class="text-[14px] text-fb-secondary flex-1 text-right pr-2 truncate">
          {{ teacher.groups_label }}
        </div>

        <div class="relative shrink-0" data-teacher-menu @click.stop>
          <button
            type="button"
            class="w-10 h-10 rounded-full flex items-center justify-center text-fb-blue transition-colors"
            :class="openMenuId === teacher.id ? 'bg-fb-hover' : 'hover:bg-fb-hover'"
            title="Actions"
            @click.stop="toggleMenu(teacher.id)"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <circle cx="12" cy="5" r="2" />
              <circle cx="12" cy="12" r="2" />
              <circle cx="12" cy="19" r="2" />
            </svg>
          </button>

          <div
            v-if="openMenuId === teacher.id"
            class="absolute right-0 top-full mt-2 w-44 rounded-xl border border-fb-line bg-fb-card shadow-fb z-20 py-2"
            data-teacher-menu
          >
            <span class="absolute -top-2 right-4 w-4 h-4 bg-fb-card border-l border-t border-fb-line rotate-45" />
            <button
              v-if="canEditTeacher"
              type="button"
              class="w-full flex items-center gap-3 px-4 py-2.5 text-[15px] text-fb-text hover:bg-fb-canvas"
              @click="editTeacher(teacher)"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
              </svg>
              Edit
            </button>
            <button
              v-if="canEditTeacher"
              type="button"
              class="w-full flex items-center gap-3 px-4 py-2.5 text-[15px] text-amber-600 hover:bg-amber-50"
              @click="archiveTeacher(teacher)"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4" />
              </svg>
              To Archive
            </button>
            <button
              v-if="canDeleteTeacher(teacher)"
              type="button"
              class="w-full flex items-center gap-3 px-4 py-2.5 text-[15px] text-red-500 hover:bg-red-50"
              @click="deleteTeacher(teacher)"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M4 7h16M9 7V5h6v2M7 7l1 14h8l1-14" />
              </svg>
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Add / edit teacher modal -->
    <div
      v-if="showModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 overflow-y-auto"
      @click.self="closeModal"
    >
      <div class="modal-panel-fb max-w-2xl max-h-[90vh] flex flex-col overflow-hidden my-auto">
        <div class="px-8 py-5 border-b border-fb-line flex items-center justify-between shrink-0">
          <h2 class="text-[24px] font-semibold text-fb-text">{{ modalTitle }}</h2>
          <button type="button" class="text-fb-icon hover:text-fb-secondary text-2xl leading-none" @click="closeModal">
            ×
          </button>
        </div>

        <form class="flex-1 flex flex-col min-h-0 overflow-hidden" @submit.prevent="submitTeacher">
          <div class="px-8 py-6 space-y-5 flex-1 overflow-y-auto">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div>
                <label class="block text-[15px] font-medium text-fb-secondary mb-2">Honorific</label>
                <select
                  v-model="form.honorific"
                  class="w-full h-12 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
                >
                  <option v-for="h in honorifics" :key="h" :value="h">{{ h }}</option>
                </select>
              </div>
              <div>
                <label class="block text-[15px] font-medium text-fb-secondary mb-2">Phone</label>
                <input
                  v-model="form.phone"
                  type="tel"
                  placeholder="90 123 45 67"
                  class="w-full h-12 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
                />
              </div>
              <div>
                <label class="block text-[15px] font-medium text-fb-secondary mb-2">First name</label>
                <input
                  v-model="form.first_name"
                  type="text"
                  required
                  class="w-full h-12 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
                />
              </div>
              <div>
                <label class="block text-[15px] font-medium text-fb-secondary mb-2">Last name</label>
                <input
                  v-model="form.last_name"
                  type="text"
                  class="w-full h-12 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
                />
              </div>
              <div class="sm:col-span-2">
                <label class="block text-[15px] font-medium text-fb-secondary mb-2">Job title / Specialization</label>
                <input
                  v-model="form.job_title"
                  type="text"
                  placeholder="e.g. Senior English Teacher"
                  class="w-full h-12 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
                />
              </div>
              <div v-if="!editingTeacher" class="sm:col-span-2">
                <div class="rounded-lg bg-emerald-50 border border-emerald-200 px-4 py-3">
                  <p class="text-[14px] text-emerald-700">
                    <svg class="inline-block w-4 h-4 mr-1 -mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                    Password will be generated automatically and shown after creation.
                  </p>
                </div>
              </div>
              <div v-else-if="auth.isCeo" class="sm:col-span-2">
                <label class="block text-[15px] font-medium text-fb-secondary mb-2">New password (optional, CEO only)</label>
                <input
                  v-model="form.password"
                  type="password"
                  placeholder="Leave blank to keep current"
                  class="w-full h-12 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
                />
              </div>
            </div>

            <div>
              <label class="block text-[15px] font-medium text-fb-secondary mb-2">Branches</label>
              <p v-if="!auth.isCeo" class="text-[13px] text-amber-600 mb-2">
                Only CEO can assign teachers to multiple branches.
              </p>
              <p v-else class="text-[14px] text-fb-secondary mb-3">
                CEO can assign a teacher to multiple branches.
              </p>
              <div class="flex flex-wrap gap-3">
                <label
                  v-for="branch in branches"
                  :key="branch.id"
                  class="flex items-center gap-2 px-4 py-2.5 rounded-lg border transition-colors"
                  :class="[
                    form.branches.includes(branch.id)
                      ? 'border-fb-blue bg-fb-hover text-fb-blue'
                      : 'border-fb-line text-fb-secondary hover:bg-fb-canvas',
                    auth.isCeo ? 'cursor-pointer' : 'cursor-not-allowed opacity-80',
                  ]"
                >
                  <input
                    type="checkbox"
                    class="rounded border-fb-line text-fb-blue focus:ring-fb-blue disabled:opacity-50"
                    :checked="form.branches.includes(branch.id)"
                    :disabled="!auth.isCeo"
                    @change="toggleBranch(branch.id)"
                  />
                  <span class="text-[15px]">{{ branch.name }}</span>
                </label>
              </div>
            </div>

            <p v-if="formError" class="text-fb-danger text-[15px]">{{ formError }}</p>
          </div>

          <div class="px-8 py-4 border-t border-fb-line flex justify-end gap-3 shrink-0 bg-fb-card">
            <button
              type="button"
              class="px-6 py-2.5 rounded-lg border border-fb-line text-[15px] font-medium text-fb-secondary hover:bg-fb-canvas"
              @click="closeModal"
            >
              Cancel
            </button>
            <button
              type="submit"
              class="px-8 py-2.5 rounded-lg bg-fb-blue text-white text-[15px] font-bold hover:opacity-90 disabled:opacity-60"
              :disabled="saving"
            >
              {{ saving ? 'Saving…' : editingTeacher ? 'Save' : 'Create' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Teacher profile drawer -->
    <div v-if="showProfile" class="fixed inset-0 z-50 flex justify-end">
      <div class="absolute inset-0 bg-black/35" @click="closeProfile" />
      <aside class="drawer-panel-fb max-w-md">
        <div class="flex items-center justify-between border-b border-fb-line px-6 py-5">
          <h2 class="text-[22px] font-semibold text-fb-text">Teacher profile</h2>
          <button type="button" class="text-2xl leading-none text-fb-icon hover:text-fb-secondary" @click="closeProfile">
            ×
          </button>
        </div>

        <div v-if="profileLoading" class="p-8 text-center text-fb-secondary">Loading…</div>
        <div v-else-if="profileTeacher" class="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          <div>
            <p class="text-2xl font-semibold text-fb-text">{{ profileTeacher.name }}</p>
            <p v-if="profileTeacher.job_title" class="text-sm font-medium text-fb-secondary mt-0.5">
              {{ profileTeacher.job_title }}
            </p>
            <p class="mt-1 text-fb-blue font-medium">{{ profileTeacher.phone_formatted || profileTeacher.phone }}</p>
          </div>

          <div>
            <p class="text-sm font-medium text-fb-secondary">Branches</p>
            <p class="mt-1 text-fb-text">
              {{ profileTeacher.branches.map((b) => b.name).join(', ') || '—' }}
            </p>
          </div>

          <div>
            <div class="mb-2 flex items-center justify-between">
              <p class="text-sm font-medium text-fb-secondary">Groups</p>
              <button type="button" class="text-sm text-fb-blue hover:underline" @click="goGroups(profileTeacher)">
                All groups →
              </button>
            </div>
            <div v-if="!profileTeacher.groups?.length" class="rounded-lg bg-fb-canvas py-6 text-center text-fb-icon">
              No groups assigned
            </div>
            <ul v-else class="divide-y divide-fb-line rounded-lg border border-fb-line">
              <li
                v-for="group in profileTeacher.groups"
                :key="group.id"
                class="px-4 py-3"
              >
                <button
                  type="button"
                  class="text-left font-medium text-fb-blue hover:underline"
                  @click="goGroup(group.id)"
                >
                  {{ group.name }}
                </button>
                <p class="text-sm text-fb-secondary">
                  {{ group.course }} · {{ group.branch }} · {{ group.days_label }}
                </p>
              </li>
            </ul>
          </div>

          <div class="flex flex-wrap gap-2 pt-2">
            <button
              v-if="canEditTeacher"
              type="button"
              class="rounded-lg bg-fb-blue px-5 py-2.5 text-sm font-semibold text-white hover:opacity-90"
              @click="editTeacher(profileTeacher)"
            >
              Edit teacher
            </button>
            <button
              v-if="canEditTeacher"
              type="button"
              class="rounded-lg border border-amber-300 px-5 py-2.5 text-sm font-medium text-amber-700 hover:bg-amber-50"
              @click="archiveTeacher(profileTeacher)"
            >
              Archive
            </button>
            <button
              v-if="canDeleteTeacher(profileTeacher)"
              type="button"
              class="rounded-lg border border-red-300 px-5 py-2.5 text-sm font-medium text-red-500 hover:bg-red-50"
              @click="deleteTeacher(profileTeacher)"
            >
              Delete
            </button>
          </div>
        </div>
      </aside>
    </div>

    <!-- Generated password modal -->
    <div
      v-if="showPasswordModal"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
    >
      <div class="bg-fb-card rounded-2xl shadow-2xl max-w-md w-full overflow-hidden">
        <div class="px-8 py-5 border-b border-fb-line">
          <h2 class="text-[20px] font-semibold text-fb-text">Teacher created!</h2>
        </div>
        <div class="px-8 py-6 space-y-4">
          <p class="text-[15px] text-fb-secondary">
            Teacher <strong class="text-fb-text">{{ generatedTeacherName }}</strong> has been created.
            Please save or copy the auto-generated password below.
          </p>
          <div class="flex items-center gap-3 rounded-xl border-2 border-fb-blue bg-fb-hover px-5 py-4">
            <span class="text-[22px] font-mono font-bold text-fb-text tracking-widest flex-1 select-all">
              {{ generatedPassword }}
            </span>
            <button
              type="button"
              class="shrink-0 px-4 py-2 rounded-lg text-[14px] font-semibold transition-colors"
              :class="passwordCopied
                ? 'bg-emerald-100 text-emerald-700 border border-emerald-300'
                : 'bg-fb-blue text-white hover:opacity-90'"
              @click="copyPassword"
            >
              {{ passwordCopied ? '✓ Copied' : 'Copy' }}
            </button>
          </div>
          <div class="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3">
            <p class="text-[13px] text-amber-700">
              <svg class="inline-block w-4 h-4 mr-1 -mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              This password will not be shown again. Only CEO can reset it later.
            </p>
          </div>
        </div>
        <div class="px-8 py-4 border-t border-fb-line flex justify-end bg-fb-card">
          <button
            type="button"
            class="px-8 py-2.5 rounded-lg bg-fb-blue text-white text-[15px] font-bold hover:opacity-90"
            @click="showPasswordModal = false"
          >
            Done
          </button>
        </div>
      </div>
    </div>

    <ImportCsvModal
      v-model:open="showImportModal"
      title="Import teachers"
      upload-url="/user/teacher/import"
      template-filename="teachers-import-template.csv"
      :template-header="['honorific', 'first_name', 'last_name', 'phone', 'password', 'job_title', 'branch_ids']"
      :template-example="['Mr', 'Ali', 'Karimov', '901001010', 'demo1234', 'Teacher', '1']"
      columns-help="Required columns: first_name, phone. Optional: honorific, last_name, password (auto-generated if empty), job_title, branch_ids (comma-separated branch IDs)."
      @imported="loadTeachers"
    />
  </div>
</template>
