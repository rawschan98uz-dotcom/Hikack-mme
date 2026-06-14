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

const canImportTeachers = computed(() => auth.can(PERM.TEACHERS_WRITE));

const form = reactive({
  honorific: 'Mr',
  first_name: '',
  last_name: '',
  phone: '',
  password: '',
  branches: [] as number[],
});

const quantity = computed(() => teachers.value.length);
const modalTitle = computed(() => (editingTeacher.value ? 'Edit teacher' : 'Add teacher'));

const honorifics = ['Mr', 'Ms', 'Mrs'];

function resetForm() {
  form.honorific = 'Mr';
  form.first_name = '';
  form.last_name = '';
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
  if (!editingTeacher.value && !form.password.trim()) {
    formError.value = 'Password is required for new teachers';
    return;
  }
  if (!form.branches.length) {
    formError.value = 'Select at least one branch';
    return;
  }

  saving.value = true;
  try {
    const payload = {
      honorific: form.honorific,
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      phone: form.phone.trim(),
      branches: form.branches,
    };

    if (editingTeacher.value) {
      const body: Record<string, unknown> = { ...payload };
      if (form.password.trim()) {
        body.password = form.password;
      }
      const teacherId = editingTeacher.value.id;
      await client.patch(`/user/teacher/${teacherId}`, body);
      await loadTeachers();
      closeModal();
      if (showProfile.value && profileTeacher.value?.id === teacherId) {
        await openProfile({ id: teacherId } as Teacher);
      }
    } else {
      await client.post<ApiEnvelope<Teacher>>('/user/teacher', {
        ...payload,
        password: form.password,
      });
      await loadTeachers();
      closeModal();
    }
  } catch {
    formError.value = editingTeacher.value
      ? 'Could not update teacher. Check phone is unique.'
      : 'Could not create teacher. Check phone is unique.';
  } finally {
    saving.value = false;
  }
}

async function deleteTeacher(teacher: Teacher) {
  closeMenu();
  if (!window.confirm(`Delete ${teacher.name}?`)) return;
  try {
    await client.delete(`/user/teacher/${teacher.id}`);
    if (profileTeacher.value?.id === teacher.id) {
      closeProfile();
    }
    await loadTeachers();
  } catch {
    window.alert('Could not delete teacher');
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
  if (!hasCreateFlag(route.query) || showModal.value) return;
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

function smsTeacher(_teacher: Teacher) {
  closeMenu();
  router.push('/sms');
}
</script>

<template>
  <div class="space-y-5">
    <!-- Page header -->
    <div class="flex items-start justify-between gap-4">
      <div class="flex items-baseline gap-3 flex-wrap">
        <h1 class="!mb-0">Teachers</h1>
        <span class="text-[18px] text-fb-secondary font-normal">Quantity — {{ quantity }}</span>
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
          type="button"
          class="px-6 py-2.5 rounded-lg bg-fb-blue text-white text-[15px] font-bold hover:opacity-90"
          @click="openModal()"
        >
          ADD NEW
        </button>
      </div>
    </div>

    <!-- CEO attention banner -->
    <div class="rounded-xl border border-fb-line bg-fb-hover px-5 py-4 flex gap-4 items-start">
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
    <div v-else-if="!teachers.length" class="rounded-xl border border-fb-line bg-fb-card p-10 text-center text-fb-icon text-[16px]">
      No teachers yet. Click ADD NEW to create one.
    </div>
    <div v-else class="grid grid-cols-2 gap-4">
      <div
        v-for="teacher in teachers"
        :key="teacher.id"
        class="relative rounded-xl border border-fb-line bg-fb-card px-5 py-4 flex items-center gap-4 hover:border-fb-line transition-colors shadow-sm overflow-visible cursor-pointer"
        @click="openProfile(teacher)"
      >
        <div class="text-[18px] font-semibold text-fb-text shrink-0 w-[28%] truncate">{{ teacher.name }}</div>
        <div class="text-[16px] text-fb-blue font-medium shrink-0 w-[32%] truncate">
          {{ teacher.phone_formatted || teacher.phone }}
        </div>
        <div class="text-[15px] text-fb-secondary flex-1 text-right pr-2 truncate">{{ teacher.groups_label }}</div>

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
              type="button"
              class="w-full flex items-center gap-3 px-4 py-2.5 text-[15px] text-fb-blue hover:bg-fb-canvas"
              @click="smsTeacher(teacher)"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M4 6h16v12H8l-4 4V6z" />
              </svg>
              SMS
            </button>
            <button
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
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4"
      @click.self="closeModal"
    >
      <div class="modal-panel-fb max-w-2xl overflow-hidden">
        <div class="px-8 py-6 border-b border-fb-line flex items-center justify-between">
          <h2 class="text-[26px] font-semibold text-fb-text">{{ modalTitle }}</h2>
          <button type="button" class="text-fb-icon hover:text-fb-secondary text-2xl leading-none" @click="closeModal">
            ×
          </button>
        </div>

        <form class="px-8 py-6 space-y-5" @submit.prevent="submitTeacher">
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
                placeholder="91 370 44 90"
                class="w-full h-12 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
              />
            </div>
            <div>
              <label class="block text-[15px] font-medium text-fb-secondary mb-2">First name</label>
              <input
                v-model="form.first_name"
                type="text"
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
            <div v-if="!editingTeacher" class="sm:col-span-2">
              <label class="block text-[15px] font-medium text-fb-secondary mb-2">Password</label>
              <input
                v-model="form.password"
                type="password"
                class="w-full h-12 px-4 rounded-lg border border-fb-line text-[16px] focus:outline-none focus:border-fb-blue"
              />
            </div>
            <div v-else class="sm:col-span-2">
              <label class="block text-[15px] font-medium text-fb-secondary mb-2">New password (optional)</label>
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
            <p class="text-[14px] text-fb-secondary mb-3">
              CEO can assign a teacher to multiple branches.
            </p>
            <div class="flex flex-wrap gap-3">
              <label
                v-for="branch in branches"
                :key="branch.id"
                class="flex items-center gap-2 px-4 py-2.5 rounded-lg border cursor-pointer transition-colors"
                :class="form.branches.includes(branch.id)
                  ? 'border-fb-blue bg-fb-hover text-fb-blue'
                  : 'border-fb-line text-fb-secondary hover:bg-fb-canvas'"
              >
                <input
                  type="checkbox"
                  class="rounded border-fb-line text-fb-blue focus:ring-fb-blue"
                  :checked="form.branches.includes(branch.id)"
                  @change="toggleBranch(branch.id)"
                />
                <span class="text-[15px]">{{ branch.name }}</span>
              </label>
            </div>
          </div>

          <p v-if="formError" class="text-fb-danger text-[15px]">{{ formError }}</p>

          <div class="flex justify-end gap-3 pt-2">
            <button
              type="button"
              class="px-6 py-3 rounded-lg border border-fb-line text-[16px] text-fb-secondary hover:bg-fb-canvas"
              @click="closeModal"
            >
              Cancel
            </button>
            <button
              type="submit"
              class="px-8 py-3 rounded-lg bg-fb-blue text-white text-[16px] font-bold hover:opacity-90 disabled:opacity-60"
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
            <p class="mt-1 text-fb-blue">{{ profileTeacher.phone_formatted || profileTeacher.phone }}</p>
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

          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="rounded-lg bg-fb-blue px-5 py-2.5 text-sm font-semibold text-white hover:opacity-90"
              @click="editTeacher(profileTeacher)"
            >
              Edit teacher
            </button>
            <button
              type="button"
              class="rounded-lg border border-fb-line px-5 py-2.5 text-sm font-medium text-fb-secondary hover:border-fb-blue hover:text-fb-blue"
              @click="smsTeacher(profileTeacher)"
            >
              SMS log
            </button>
          </div>
        </div>
      </aside>
    </div>

    <ImportCsvModal
      v-model:open="showImportModal"
      title="Import teachers"
      upload-url="/user/teacher/import"
      template-filename="teachers-import-template.csv"
      :template-header="['honorific', 'first_name', 'last_name', 'phone', 'password', 'job_title', 'branch_ids']"
      :template-example="['Mr', 'Ali', 'Karimov', '901001010', 'demo1234', 'Teacher', '1']"
      columns-help="Required columns: first_name, phone. Optional: honorific, last_name, password (default demo1234), job_title, branch_ids (comma-separated branch IDs)."
      @imported="loadTeachers"
    />
  </div>
</template>
