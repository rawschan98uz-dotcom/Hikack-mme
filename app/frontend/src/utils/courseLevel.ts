export type CefrLevel = 'A1' | 'A2' | 'B1' | 'B2' | 'C1' | 'C2';

const CEFR_LEVELS: CefrLevel[] = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];

/** Colors from CEFR reference chart. */
export const CEFR_LEVEL_COLORS: Record<CefrLevel, string> = {
  A1: '#b1a3fa',
  A2: '#15b8db',
  B1: '#bbcd2a',
  B2: '#ffd33e',
  C1: '#f3983e',
  C2: '#e86fd6',
};

export const CEFR_LEVEL_STARS: Record<CefrLevel, number> = {
  A1: 1,
  A2: 2,
  B1: 3,
  B2: 4,
  C1: 5,
  C2: 6,
};

const LEVEL_PATTERN = /(A1|A2|B1|B2|C1|C2)/i;

export function normalizeCourseCode(code: string): string {
  return code.trim().toLowerCase();
}

/** Level and card styling are driven only by Code Course. */
export function parseLevelFromCourseCode(code: string): CefrLevel | null {
  const normalized = normalizeCourseCode(code);
  if (!normalized) {
    return null;
  }

  if (/^(a1|a2|b1|b2|c1|c2)$/.test(normalized)) {
    return normalized.toUpperCase() as CefrLevel;
  }

  const match = normalized.match(LEVEL_PATTERN);
  if (match) {
    return match[1].toUpperCase() as CefrLevel;
  }

  return null;
}

export function courseLevelColor(level: CefrLevel | null): string {
  if (level) {
    return CEFR_LEVEL_COLORS[level];
  }
  return '#898F9C';
}

export function courseLevelStars(level: CefrLevel | null): number {
  if (level) {
    return CEFR_LEVEL_STARS[level];
  }
  return 0;
}

export function isValidCourseCode(code: string): boolean {
  return parseLevelFromCourseCode(code) !== null;
}

export interface CourseCardDisplay {
  code: string;
  level: CefrLevel | null;
  levelColor: string;
  starCount: number;
  cardTitle: string;
  badgeLabel: string;
  watermarkLabel: string;
}

export function buildCourseCardDisplay(code: string): CourseCardDisplay {
  const normalizedCode = normalizeCourseCode(code);
  const level = parseLevelFromCourseCode(normalizedCode);

  return {
    code: normalizedCode,
    level,
    levelColor: courseLevelColor(level),
    starCount: courseLevelStars(level),
    cardTitle: normalizedCode,
    badgeLabel: level ?? '—',
    watermarkLabel: normalizedCode || (level ? level.toLowerCase() : ''),
  };
}

export function courseCodeHint(): string {
  return `Use a CEFR code: ${CEFR_LEVELS.join(', ')}`;
}
