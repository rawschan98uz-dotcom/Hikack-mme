<script setup lang="ts">
import { ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { downloadTemplate } from '../utils/csvExport';

export interface ImportErrorRow {
  row: number;
  message: string;
}

export interface PreviewRow {
  row: number;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  formatted_phone: string;
  branch_name: string;
  group_name: string;
  status_label: string;
  balance: number;
  school: string;
  parent_telegram?: string;
  is_valid: boolean;
  message: string;
}

export interface PreviewResult {
  dry_run: boolean;
  total: number;
  valid: number;
  skipped: number;
  errors: ImportErrorRow[];
  rows: PreviewRow[];
}

export interface ImportResult {
  created: number;
  skipped: number;
  errors: ImportErrorRow[];
}

const props = defineProps<{
  open: boolean;
  title: string;
  uploadUrl: string;
  templateFilename: string;
  templateHeader: string[];
  templateExample?: string[];
  columnsHelp: string;
}>();

const emit = defineEmits<{
  'update:open': [value: boolean];
  imported: [];
}>();

type ImportStep = 'select' | 'preview' | 'success';

const step = ref<ImportStep>('select');
const fileInput = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);
const analyzing = ref(false);
const committing = ref(false);
const uploadError = ref('');

const previewData = ref<PreviewResult | null>(null);
const finalResult = ref<ImportResult | null>(null);

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function close() {
  emit('update:open', false);
  selectedFile.value = null;
  uploadError.value = '';
  previewData.value = null;
  finalResult.value = null;
  step.value = 'select';
  if (fileInput.value) {
    fileInput.value.value = '';
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
  uploadError.value = '';
  previewData.value = null;
  finalResult.value = null;
}

function downloadSample() {
  downloadTemplate(props.templateFilename, props.templateHeader, props.templateExample);
}

function goBackToSelect() {
  step.value = 'select';
  uploadError.value = '';
}

async function analyzeFile() {
  if (!selectedFile.value) {
    uploadError.value = 'Выберите Excel (.xlsx, .xls) или CSV файл для импорта';
    return;
  }

  analyzing.value = true;
  uploadError.value = '';
  try {
    const form = new FormData();
    form.append('file', selectedFile.value);
    form.append('dry_run', '1');

    const { data } = await client.post<ApiEnvelope<PreviewResult | ImportResult>>(
      props.uploadUrl,
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      },
    );

    const payload = data.data;
    if ('rows' in payload && payload.rows) {
      previewData.value = payload as PreviewResult;
      step.value = 'preview';
    } else {
      finalResult.value = payload as ImportResult;
      step.value = 'success';
      if ((payload as ImportResult).created > 0) {
        emit('imported');
      }
    }
  } catch (err: any) {
    uploadError.value = err?.response?.data?.message || 'Ошибка анализа файла. Проверьте формат файла.';
  } finally {
    analyzing.value = false;
  }
}

async function confirmImport() {
  if (!selectedFile.value) return;

  committing.value = true;
  uploadError.value = '';
  try {
    const form = new FormData();
    form.append('file', selectedFile.value);
    form.append('dry_run', '0');

    const { data } = await client.post<ApiEnvelope<ImportResult>>(props.uploadUrl, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    finalResult.value = data.data;
    step.value = 'success';
    if (data.data.created > 0) {
      emit('imported');
    }
  } catch (err: any) {
    uploadError.value = err?.response?.data?.message || 'Ошибка сохранения данных в базу.';
  } finally {
    committing.value = false;
  }
}
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="close" />

    <div
      class="relative z-10 w-full transition-all rounded-2xl border border-fb-line bg-fb-card shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
      :class="step === 'preview' ? 'max-w-5xl' : 'max-w-xl'"
    >
      <!-- Modal Header -->
      <div class="flex items-center justify-between border-b border-fb-line px-6 py-4 bg-fb-canvas/50">
        <div>
          <h2 class="text-lg font-semibold text-fb-text">
            {{ step === 'preview' ? 'Предварительный просмотр перед загрузкой' : title }}
          </h2>
          <p class="text-xs text-fb-secondary mt-0.5">
            {{ step === 'select' ? 'Шаг 1 из 2: Выбор файла' : step === 'preview' ? 'Шаг 2 из 2: Проверка данных' : 'Завершено' }}
          </p>
        </div>
        <button
          type="button"
          class="flex h-8 w-8 items-center justify-center rounded-lg text-fb-icon hover:bg-fb-line hover:text-fb-text transition-colors"
          @click="close"
        >
          ✕
        </button>
      </div>

      <!-- Modal Body -->
      <div class="p-6 overflow-y-auto space-y-5">
        <!-- STEP 1: SELECT FILE -->
        <template v-if="step === 'select'">
          <p class="text-sm text-fb-secondary leading-relaxed">
            {{ columnsHelp }}
          </p>

          <div class="flex items-center justify-between rounded-xl border border-fb-line bg-fb-canvas/40 p-3.5">
            <div class="flex items-center gap-3">
              <span class="text-xl">📥</span>
              <div class="text-xs">
                <div class="font-medium text-fb-text">Нужен готовый образец?</div>
                <div class="text-fb-secondary">Скачайте шаблон со всеми нужными полями</div>
              </div>
            </div>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-lg border border-fb-line bg-fb-card px-3 py-1.5 text-xs font-medium text-fb-blue shadow-sm hover:bg-fb-hover transition-colors"
              @click="downloadSample"
            >
              Скачать шаблон CSV
            </button>
          </div>

          <div>
            <label class="mb-2 block text-sm font-medium text-fb-text">
              Выберите файл таблицы (Excel .xlsx, .xls или .csv)
            </label>
            <div class="relative">
              <input
                ref="fileInput"
                type="file"
                accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                class="block w-full text-sm text-fb-secondary file:mr-4 file:cursor-pointer file:rounded-lg file:border-0 file:bg-fb-blue file:px-4 file:py-2.5 file:text-sm file:font-medium file:text-white hover:file:opacity-90 transition-all cursor-pointer rounded-xl border border-dashed border-fb-line bg-fb-canvas/30 p-4"
                @change="onFileChange"
              />
            </div>
            <div v-if="selectedFile" class="mt-2.5 flex items-center gap-2 text-xs text-emerald-700 bg-emerald-50 rounded-lg p-2 border border-emerald-200">
              <span>📄</span>
              <span class="font-medium truncate">{{ selectedFile.name }}</span>
              <span class="text-emerald-600">({{ formatFileSize(selectedFile.size) }})</span>
            </div>
          </div>

          <p v-if="uploadError" class="rounded-lg bg-red-50 p-3 text-sm text-fb-danger border border-red-200">
            {{ uploadError }}
          </p>
        </template>

        <!-- STEP 2: PREVIEW TABLE -->
        <template v-else-if="step === 'preview' && previewData">
          <!-- Stats badges -->
          <div class="grid grid-cols-3 gap-3">
            <div class="rounded-xl border border-fb-line bg-fb-canvas/40 p-3 text-center">
              <div class="text-xs text-fb-secondary">Всего найдено строк</div>
              <div class="text-xl font-bold text-fb-text">{{ previewData.total }}</div>
            </div>
            <div class="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3 text-center">
              <div class="text-xs text-emerald-700 font-medium">Готовы к загрузке</div>
              <div class="text-xl font-bold text-emerald-700">{{ previewData.valid }}</div>
            </div>
            <div class="rounded-xl border border-amber-200 bg-amber-50/60 p-3 text-center">
              <div class="text-xs text-amber-700 font-medium">Ошибки / пропуски</div>
              <div class="text-xl font-bold text-amber-700">{{ previewData.skipped }}</div>
            </div>
          </div>

          <div class="rounded-xl border border-sky-200 bg-sky-50/70 p-3 text-xs text-sky-800 flex items-start gap-2.5">
            <span class="text-base">💡</span>
            <div>
              <strong>Проверьте результат:</strong> ниже показано, как система распознала и очистила данные. Номера телефонов приведены к единому стандарту, имена и фамилии разделены по ячейкам. Если всё корректно — нажмите кнопку <strong>«Подтвердить и загрузить в базу»</strong>.
            </div>
          </div>

          <!-- Preview Table -->
          <div class="rounded-xl border border-fb-line overflow-hidden shadow-sm">
            <div class="max-h-[380px] overflow-y-auto overflow-x-auto">
              <table class="w-full text-left text-xs border-collapse">
                <thead class="sticky top-0 bg-fb-canvas text-fb-secondary uppercase tracking-wider font-semibold border-b border-fb-line">
                  <tr>
                    <th class="py-2.5 px-3 w-12 text-center">#</th>
                    <th class="py-2.5 px-3">Статус</th>
                    <th class="py-2.5 px-3">Распознанное ФИО</th>
                    <th class="py-2.5 px-3">Телефон</th>
                    <th class="py-2.5 px-3">Группа</th>
                    <th class="py-2.5 px-3">Школа</th>
                    <th class="py-2.5 px-3">Баланс</th>
                    <th class="py-2.5 px-3">Филиал</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-fb-line bg-fb-card">
                  <tr
                    v-for="row in previewData.rows"
                    :key="row.row"
                    :class="row.is_valid ? 'hover:bg-fb-canvas/50' : 'bg-red-50/40 hover:bg-red-50/70'"
                  >
                    <td class="py-2.5 px-3 text-center text-fb-secondary font-mono">{{ row.row }}</td>
                    <td class="py-2.5 px-3 whitespace-nowrap">
                      <span
                        v-if="row.is_valid"
                        class="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800"
                      >
                        ✓ Готов
                      </span>
                      <span
                        v-else
                        class="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-[11px] font-medium text-red-800"
                        :title="row.message"
                      >
                        ✕ {{ row.message || 'Ошибка' }}
                      </span>
                    </td>
                    <td class="py-2.5 px-3 font-medium text-fb-text">
                      <div class="font-semibold">{{ row.full_name || '—' }}</div>
                      <div v-if="row.first_name && row.last_name" class="text-[10px] text-fb-secondary font-normal">
                        Имя: {{ row.first_name }} | Фамилия: {{ row.last_name }}
                      </div>
                    </td>
                    <td class="py-2.5 px-3 font-mono text-fb-text whitespace-nowrap">
                      {{ row.formatted_phone }}
                    </td>
                    <td class="py-2.5 px-3 text-fb-secondary whitespace-nowrap">
                      {{ row.group_name }}
                    </td>
                    <td class="py-2.5 px-3 text-fb-secondary">
                      {{ row.school }}
                    </td>
                    <td class="py-2.5 px-3 font-medium text-fb-text whitespace-nowrap">
                      {{ Number(row.balance).toLocaleString() }} сум
                    </td>
                    <td class="py-2.5 px-3 text-fb-secondary whitespace-nowrap">
                      {{ row.branch_name }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <p v-if="uploadError" class="rounded-lg bg-red-50 p-3 text-sm text-fb-danger border border-red-200">
            {{ uploadError }}
          </p>
        </template>

        <!-- STEP 3: SUCCESS -->
        <template v-else-if="step === 'success' && finalResult">
          <div class="py-6 text-center space-y-3">
            <div class="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-2xl text-emerald-700 shadow-sm">
              ✓
            </div>
            <h3 class="text-xl font-bold text-fb-text">Импорт успешно завершен!</h3>
            <p class="text-sm text-fb-secondary max-w-sm mx-auto">
              В базу данных успешно загружено <strong>{{ finalResult.created }}</strong> учеников.
              <span v-if="finalResult.skipped > 0"> Пропущено строк: {{ finalResult.skipped }}.</span>
            </p>

            <div v-if="finalResult.errors.length" class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-left text-xs max-w-md mx-auto">
              <div class="font-semibold text-amber-900 mb-1.5">Замечания по строкам:</div>
              <ul class="space-y-1 text-amber-800 max-h-32 overflow-y-auto">
                <li v-for="(err, idx) in finalResult.errors" :key="idx">
                  Строка {{ err.row }}: {{ err.message }}
                </li>
              </ul>
            </div>
          </div>
        </template>
      </div>

      <!-- Modal Footer -->
      <div class="flex items-center justify-between border-t border-fb-line px-6 py-4 bg-fb-canvas/50">
        <template v-if="step === 'select'">
          <button
            type="button"
            class="rounded-xl border border-fb-line bg-fb-card px-4 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-hover transition-colors"
            @click="close"
          >
            Отмена
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-xl bg-fb-blue px-5 py-2 text-sm font-medium text-white shadow-sm hover:opacity-90 disabled:opacity-50 transition-all"
            :disabled="analyzing || !selectedFile"
            @click="analyzeFile"
          >
            <span v-if="analyzing" class="inline-block animate-spin">⏳</span>
            {{ analyzing ? 'Анализ файла…' : 'Проверить и предпросмотр →' }}
          </button>
        </template>

        <template v-else-if="step === 'preview'">
          <button
            type="button"
            class="rounded-xl border border-fb-line bg-fb-card px-4 py-2 text-sm font-medium text-fb-secondary hover:bg-fb-hover transition-colors"
            :disabled="committing"
            @click="goBackToSelect"
          >
            ← Выбрать другой файл
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-xl bg-fb-blue px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-50 transition-all"
            :disabled="committing || !previewData || previewData.valid === 0"
            @click="confirmImport"
          >
            <span v-if="committing" class="inline-block animate-spin">⏳</span>
            {{ committing ? 'Загрузка в базу…' : `Подтвердить и загрузить в базу (${previewData?.valid ?? 0} уч.)` }}
          </button>
        </template>

        <template v-else-if="step === 'success'">
          <div class="w-full flex justify-end">
            <button
              type="button"
              class="rounded-xl bg-fb-blue px-6 py-2 text-sm font-medium text-white shadow-sm hover:opacity-90 transition-colors"
              @click="close"
            >
              Готово
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

