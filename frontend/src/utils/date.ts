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

/**
 * 사람이 말하듯 읽는 시각. "오늘 새벽 2시 58분" / "어제 저녁 7시 10분" / "8월 3일 오후 2시".
 *
 * 왜 formatDateTime 과 따로 두는가
 *   기존 표기는 "2026년 8월 10일 (월) 02:58" 이다. 정확하지만, 보호자가 카드를 읽을 때
 *   필요한 정보는 연도도 요일도 아니고 "얼마나 최근인가" 하나다. 연·월·일·요일을 다 적으면
 *   그 하나를 사람이 직접 계산해야 한다 — 오늘인지 그저께인지를 날짜를 빼서 알아내야 한다.
 *
 *   formatRelativeTime("8시간 전")도 답이 아니다. 새벽에 있었던 일인지 저녁이었는지가
 *   건강 관련 발화에서는 의미를 갖는데, 상대 시각은 그걸 지운다.
 */
export const formatSpokenDateTime = (
  value: DateLike,
  referenceDate: DateLike = new Date(),
): string => {
  const date = toValidDate(value);
  if (!date) {
    return "시각 미확인";
  }

  const hour = Number(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: BOMI_TIME_ZONE,
      hour: "2-digit",
      hour12: false,
    }).format(date),
  );
  const minute = Number(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: BOMI_TIME_ZONE,
      minute: "2-digit",
    }).format(date),
  );

  // 경계는 어림값이다. 정확히 몇 시부터 '아침'인지에 정답은 없고, 여기서 필요한 것은
  // 분류가 아니라 "언제쯤이었는지"가 한 번에 읽히는 것뿐이다.
  const partOfDay =
    hour < 6 ? "새벽" : hour < 12 ? "아침" : hour < 18 ? "오후" : "저녁";
  const hour12 = hour % 12 === 0 ? 12 : hour % 12;
  const clock = minute === 0 ? `${hour12}시` : `${hour12}시 ${minute}분`;

  const reference = toValidDate(referenceDate) ?? new Date();
  const yesterday = new Date(reference.getTime() - 24 * 60 * 60 * 1000);

  if (isSameLocalDate(date, reference)) return `오늘 ${partOfDay} ${clock}`;
  if (isSameLocalDate(date, yesterday)) return `어제 ${partOfDay} ${clock}`;

  return `${formatWith(date, { month: "long", day: "numeric" })} ${partOfDay} ${clock}`;
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
