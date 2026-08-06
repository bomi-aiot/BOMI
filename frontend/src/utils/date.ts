const KOREAN_LOCALE = "ko-KR";
export const BOMI_TIME_ZONE = "Asia/Seoul";

type DateLike = string | number | Date;

const toValidDate = (value: DateLike): Date | null => {
  const parsed = value instanceof Date ? new Date(value.getTime()) : new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const formatWith = (
  value: DateLike,
  options: Intl.DateTimeFormatOptions,
  fallback = "-",
): string => {
  const date = toValidDate(value);
  if (!date) {
    return fallback;
  }

  return new Intl.DateTimeFormat(KOREAN_LOCALE, {
    timeZone: BOMI_TIME_ZONE,
    ...options,
  }).format(date);
};

export const formatDate = (value: DateLike): string =>
  formatWith(value, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

export const formatShortDate = (value: DateLike): string =>
  formatWith(value, {
    month: "short",
    day: "numeric",
    weekday: "short",
  });

export const formatDateWithWeekday = (value: DateLike): string =>
  formatWith(value, {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  });

export const formatTime = (value: DateLike): string =>
  formatWith(value, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

export const formatDateTime = (value: DateLike): string =>
  formatWith(value, {
    year: "numeric",
    month: "short",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

export const formatMonthDayTime = (value: DateLike): string =>
  formatWith(value, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

export const formatBirthDate = (birthDate: string): string =>
  formatWith(birthDate, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

export const calculateAge = (
  birthDate: string,
  referenceDate: DateLike = new Date(),
): number | null => {
  const birth = toValidDate(birthDate);
  const reference = toValidDate(referenceDate);
  if (!birth || !reference || birth > reference) {
    return null;
  }

  const birthParts = getDateParts(birth);
  const referenceParts = getDateParts(reference);
  let age = referenceParts.year - birthParts.year;

  const birthdayHasPassed =
    referenceParts.month > birthParts.month ||
    (referenceParts.month === birthParts.month &&
      referenceParts.day >= birthParts.day);

  if (!birthdayHasPassed) {
    age -= 1;
  }

  return age;
};

interface DateParts {
  year: number;
  month: number;
  day: number;
}

const getDateParts = (value: DateLike): DateParts => {
  const date = toValidDate(value);
  if (!date) {
    return { year: 0, month: 0, day: 0 };
  }

  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: BOMI_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);

  const part = (type: Intl.DateTimeFormatPartTypes): number =>
    Number(parts.find((item) => item.type === type)?.value ?? 0);

  return {
    year: part("year"),
    month: part("month"),
    day: part("day"),
  };
};

export const isSameLocalDate = (left: DateLike, right: DateLike): boolean => {
  if (!toValidDate(left) || !toValidDate(right)) {
    return false;
  }
  const leftParts = getDateParts(left);
  const rightParts = getDateParts(right);

  return (
    leftParts.year === rightParts.year &&
    leftParts.month === rightParts.month &&
    leftParts.day === rightParts.day
  );
};

export const isToday = (
  value: DateLike,
  referenceDate: DateLike = new Date(),
): boolean => isSameLocalDate(value, referenceDate);

export const formatRelativeTime = (
  value: DateLike,
  referenceDate: DateLike = new Date(),
): string => {
  const date = toValidDate(value);
  const reference = toValidDate(referenceDate);
  if (!date || !reference) {
    return "-";
  }

  const differenceSeconds = Math.round((date.getTime() - reference.getTime()) / 1000);
  const absoluteSeconds = Math.abs(differenceSeconds);

  if (absoluteSeconds < 45) {
    return differenceSeconds >= 0 ? "곧" : "방금 전";
  }

  const relativeFormatter = new Intl.RelativeTimeFormat(KOREAN_LOCALE, {
    numeric: "auto",
  });

  if (absoluteSeconds < 60 * 60) {
    return relativeFormatter.format(Math.round(differenceSeconds / 60), "minute");
  }

  if (absoluteSeconds < 60 * 60 * 24) {
    return relativeFormatter.format(Math.round(differenceSeconds / 3600), "hour");
  }

  if (absoluteSeconds < 60 * 60 * 24 * 7) {
    return relativeFormatter.format(Math.round(differenceSeconds / 86400), "day");
  }

  return formatShortDate(date);
};

export const toDateInputValue = (value: DateLike): string => {
  const { year, month, day } = getDateParts(value);
  if (!year || !month || !day) {
    return "";
  }
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
};

export const toDateTimeLocalInputValue = (value: DateLike): string => {
  const date = toValidDate(value);
  if (!date) {
    return "";
  }

  const datePart = toDateInputValue(date);
  const timePart = new Intl.DateTimeFormat("en-GB", {
    timeZone: BOMI_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);

  return `${datePart}T${timePart}`;
};

export const fromKoreanDateTimeLocalInput = (value: string): string => {
  const normalized = value.trim();
  const match = normalized.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/,
  );
  if (!match) {
    throw new Error("날짜와 시간을 확인해 주세요.");
  }

  const seconds = match[6] ?? "00";
  const koreanDateTime = `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:${seconds}+09:00`;
  const parsed = new Date(koreanDateTime);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("유효한 날짜와 시간을 입력해 주세요.");
  }
  return parsed.toISOString();
};

export const sortByDateAscending = <T>(
  items: T[],
  getDate: (item: T) => DateLike,
): T[] =>
  [...items].sort((left, right) => {
    const leftDate = toValidDate(getDate(left))?.getTime() ?? Number.MAX_SAFE_INTEGER;
    const rightDate =
      toValidDate(getDate(right))?.getTime() ?? Number.MAX_SAFE_INTEGER;
    return leftDate - rightDate;
  });
