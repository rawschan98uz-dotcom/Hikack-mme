import type { LocationQuery, RouteLocationNormalizedLoaded } from 'vue-router';

type QueryExtra = Record<string, string>;

function buildQuery(extra?: QueryExtra, openId?: number): LocationQuery {
  const query: LocationQuery = { ...extra };
  if (openId != null) {
    query.open = String(openId);
  }
  return query;
}

export function parseOpenId(query: LocationQuery): number | null {
  const raw = query.open;
  if (raw == null || raw === '') return null;
  const value = Array.isArray(raw) ? raw[0] : raw;
  const id = parseInt(String(value), 10);
  return Number.isFinite(id) && id > 0 ? id : null;
}

export function hasCreateFlag(query: LocationQuery): boolean {
  const raw = query.create;
  if (raw == null || raw === '' || raw === '0' || raw === 'false') return false;
  return true;
}

export function routeWithoutOpen(route: RouteLocationNormalizedLoaded) {
  const query = { ...route.query };
  delete query.open;
  return { path: route.path, query };
}

export function routeWithoutCreate(route: RouteLocationNormalizedLoaded) {
  const query = { ...route.query };
  delete query.create;
  return { path: route.path, query };
}

export function withCreateQuery(path: string) {
  return { path, query: { create: '1' } };
}

export function studentRoute(id?: number, extra?: QueryExtra) {
  return { path: '/students', query: buildQuery(extra, id) };
}

export function studentsByGroup(groupId: number) {
  return { path: '/students', query: { group_id: String(groupId) } };
}

export function groupRoute(id?: number, extra?: QueryExtra) {
  return { path: '/groups', query: buildQuery(extra, id) };
}

export function groupsByTeacher(teacherId: number) {
  return { path: '/groups', query: { teacher_id: String(teacherId) } };
}

export function teacherRoute(id?: number) {
  return { path: '/teachers', query: buildQuery(undefined, id) };
}
