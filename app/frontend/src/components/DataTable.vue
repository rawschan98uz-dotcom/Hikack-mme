<script setup lang="ts" generic="T extends Record<string, unknown>">
defineProps<{
  columns: { key: string; label: string }[];
  rows: T[];
  loading?: boolean;
  emptyText?: string;
}>();
</script>

<template>
  <div class="bg-fb-card rounded-xl border border-fb-line overflow-hidden">
    <div v-if="loading" class="p-8 text-center text-fb-secondary">Loading…</div>
    <div v-else-if="!rows.length" class="p-8 text-center text-fb-icon">
      {{ emptyText ?? 'No data' }}
    </div>
    <table v-else class="w-full text-base">
      <thead class="bg-fb-canvas border-b border-fb-line">
        <tr>
          <th
            v-for="col in columns"
            :key="col.key"
            class="text-left px-5 py-4 font-semibold text-fb-secondary"
          >
            {{ col.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, idx) in rows"
          :key="idx"
          class="table-row-fb"
        >
          <td
            v-for="col in columns"
            :key="col.key"
            class="px-5 py-4 text-fb-secondary"
          >
            {{ row[col.key] ?? '—' }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
