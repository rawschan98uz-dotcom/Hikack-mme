<script setup lang="ts">
const updates = [
  {
    date: '2026-06-10',
    title: 'Cross-links between Students, Groups, and Teachers',
    body: 'Click group or teacher names in tables and drawers to jump directly to the related record.',
  },
  {
    date: '2026-06-10',
    title: 'Settings: Archive, Forms, Tags, Roadmap',
    body: 'Archive bulk actions, ModMe-style Forms/Tags tables, and a Roadmap page with milestones.',
  },
  {
    date: '2026-06-09',
    title: 'Finance and Reports modules',
    body: 'Payments, withdrawals, expenses, salaries, conversion, leads, left-students, and Workly reports.',
  },
  {
    date: '2026-06-08',
    title: 'Local MVP clone ready',
    body: 'Django API + Vue frontend with demo seed data for RavvaTech center.',
  },
];
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-[28px] font-normal text-fb-text">What's new</h1>
      <p class="mt-2 text-fb-secondary">
        Release notes for this local ModMe clone. Live updates:
        <a
          href="https://modme.uz"
          target="_blank"
          rel="noopener noreferrer"
          class="text-fb-blue hover:underline"
        >
          modme.uz
        </a>
      </p>
    </div>

    <div class="space-y-4">
      <article
        v-for="item in updates"
        :key="item.title"
        class="rounded-xl border border-fb-line bg-fb-card p-6"
      >
        <time class="text-sm text-fb-icon">{{ item.date }}</time>
        <h2 class="mt-1 text-lg font-semibold text-fb-text">{{ item.title }}</h2>
        <p class="mt-2 text-fb-secondary">{{ item.body }}</p>
      </article>
    </div>
  </div>
</template>
