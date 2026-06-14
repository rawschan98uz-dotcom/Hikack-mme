<script setup lang="ts">
import { ref } from 'vue';

import client, { type ApiEnvelope } from '../api/client';
import { downloadTemplate } from '../utils/csvExport';

export interface ImportErrorRow {
  row: number;
  message: string;
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

const fileInput = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);
const uploading = ref(false);
const uploadError = ref('');
const result = ref<ImportResult | null>(null);

function close() {
  emit('update:open', false);
  selectedFile.value = null;
  uploadError.value = '';
  result.value = null;
  if (fileInput.value) {
    fileInput.value.value = '';
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
  uploadError.value = '';
  result.value = null;
}

function downloadSample() {
  downloadTemplate(props.templateFilename, props.templateHeader, props.templateExample);
}

async function submitImport() {
  if (!selectedFile.value) {
    uploadError.value = 'Select a CSV file';
    return;
  }

  uploading.value = true;
  uploadError.value = '';
  try {
    const form = new FormData();
    form.append('file', selectedFile.value);
    const { data } = await client.post<ApiEnvelope<ImportResult>>(props.uploadUrl, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    result.value = data.data;
    if (data.data.created > 0) {
      emit('imported');
    }
  } catch {
    uploadError.value = 'Import failed. Check file format and permissions.';
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-black/40" @click="close" />
    <div class="relative z-10 w-full max-w-lg rounded-xl border border-fb-line bg-fb-card shadow-xl">
      <div class="flex items-center justify-between border-b border-fb-line px-6 py-4">
        <h2 class="text-lg font-semibold text-fb-text">{{ title }}</h2>
        <button type="button" class="text-fb-icon hover:text-fb-secondary" @click="close">✕</button>
      </div>

      <div class="space-y-4 p-6">
        <p class="text-sm text-fb-secondary">{{ columnsHelp }}</p>

        <button
          type="button"
          class="text-sm font-medium text-fb-blue hover:underline"
          @click="downloadSample"
        >
          Download CSV template
        </button>

        <div>
          <label class="mb-1 block text-sm font-medium text-fb-secondary">CSV file</label>
          <input
            ref="fileInput"
            type="file"
            accept=".csv,text/csv"
            class="block w-full text-sm text-fb-secondary file:mr-3 file:rounded-lg file:border file:border-fb-line file:bg-fb-canvas file:px-3 file:py-2 file:text-sm file:font-medium file:text-fb-text"
            @change="onFileChange"
          />
        </div>

        <div v-if="result" class="rounded-lg border border-fb-line bg-fb-canvas p-4 text-sm">
          <p class="font-medium text-fb-text">
            Created: {{ result.created }}, skipped: {{ result.skipped }}
          </p>
          <ul v-if="result.errors.length" class="mt-2 max-h-40 space-y-1 overflow-y-auto text-fb-danger">
            <li v-for="(err, idx) in result.errors" :key="idx">
              Row {{ err.row }}: {{ err.message }}
            </li>
          </ul>
        </div>

        <p v-if="uploadError" class="text-sm text-fb-danger">{{ uploadError }}</p>
      </div>

      <div class="flex justify-end gap-2 border-t border-fb-line px-6 py-4">
        <button type="button" class="rounded-lg border border-fb-line px-4 py-2 text-sm" @click="close">
          Close
        </button>
        <button
          type="button"
          class="rounded-lg bg-fb-blue px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          :disabled="uploading || !selectedFile"
          @click="submitImport"
        >
          {{ uploading ? 'Importing…' : 'Import' }}
        </button>
      </div>
    </div>
  </div>
</template>
