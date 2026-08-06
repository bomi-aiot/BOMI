import { useMemo, useState, type ChangeEvent } from 'react'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from '../components'
import { useBomi } from '../state/BomiContext'
import type {
  ConversationPreference,
  MemoryType,
  MemoryVerificationStatus,
  MemoryVisibility,
} from '../types/domain'
import { formatDateTime } from '../utils/date'

type PreferenceTypeFilter = 'ALL' | MemoryType

const MEMORY_TYPE_LABELS: Record<MemoryType, string> = {
  PERSONAL_RELATIONSHIP: '중요한 사람',
  PREFERENCE: '선호',
  HOBBY: '취미·관심사',
  DAILY_ROUTINE: '일상 습관',
  LIFE_EVENT: '삶의 사건',
  FAMILY_MEMORY: '가족 기억',
  EMOTIONAL_EVENT: '정서적 경험',
  CONVERSATION_SUMMARY: '대화 요약',
  OTHER: '기타',
}

const FILTERABLE_MEMORY_TYPES: readonly MemoryType[] = [
  'PREFERENCE',
  'HOBBY',
  'DAILY_ROUTINE',
  'PERSONAL_RELATIONSHIP',
  'LIFE_EVENT',
  'FAMILY_MEMORY',
  'EMOTIONAL_EVENT',
  'OTHER',
]

const SOURCE_LABELS: Record<ConversationPreference['source'], string> = {
  USER: '어르신 말씀',
  GUARDIAN: '보호자 입력',
  ROBOT: '로봇 대화',
  AI: 'AI 제안',
  SYSTEM: '출처 확인 중',
}

const VERIFICATION_LABELS: Record<MemoryVerificationStatus, string> = {
  UNVERIFIED: '확인 전',
  AUTO_ACCEPTED: 'AI 임시 반영',
  USER_CONFIRMED: '어르신 확인',
  GUARDIAN_CONFIRMED: '보호자 확인',
  REJECTED: '반영 안 함',
}

const VISIBILITY_LABELS: Record<MemoryVisibility, string> = {
  PRIVATE: '어르신 대화에만 사용',
  SHARED_WITH_PRIMARY: '주 보호자와 공유',
  SHARED_WITH_GUARDIANS: '등록 보호자와 공유',
}

// 읽기 전용 화면: 보호자 공유 범위와 활성 상태가 확인된 memory만 조회한다.
export function ConversationPreferencesPage() {
  const { conversationPreferences, isLoading, error, dataErrors, refresh } = useBomi()
  const pageError = dataErrors.conversationPreferences ?? error

  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<PreferenceTypeFilter>('ALL')

  const guardianVisiblePreferences = useMemo(
    () =>
      conversationPreferences.filter(
        (preference) =>
          preference.lifecycleStatus === 'ACTIVE' &&
          preference.memoryType !== 'CONVERSATION_SUMMARY' &&
          preference.memoryType !== 'EMOTIONAL_EVENT' &&
          (preference.visibility === 'SHARED_WITH_PRIMARY' ||
            preference.visibility === 'SHARED_WITH_GUARDIANS'),
      ),
    [conversationPreferences],
  )

  const filteredPreferences = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('ko-KR')

    return guardianVisiblePreferences.filter((preference) => {
      const matchesQuery =
        normalizedQuery.length === 0 ||
        [preference.title, preference.content, ...preference.keywords].some(
          (value) =>
            value.toLocaleLowerCase('ko-KR').includes(normalizedQuery),
        )
      const matchesType =
        typeFilter === 'ALL' || preference.memoryType === typeFilter

      return matchesQuery && matchesType
    })
  }, [guardianVisiblePreferences, query, typeFilter])

  if (isLoading && conversationPreferences.length === 0) {
    return (
      <LoadingState label="대화 정보를 불러오는 중입니다" rows={5} />
    )
  }

  if (pageError && conversationPreferences.length === 0) {
    return (
      <ErrorState
        title="대화 정보를 불러오지 못했습니다"
        description={pageError}
        onRetry={() => void refresh()}
      />
    )
  }

  return (
    <div className="page-stack conversation-preferences-page">
      <PageHeader
        eyebrow="개인화 기억"
        title="대화 정보"
        description="보호자 공유가 허용된 관심사·습관·선호만 보여드려요. 비공개 대화와 대화 원문은 표시하지 않아요."
        metadata={<span>공유된 정보 {guardianVisiblePreferences.length}건</span>}
      />

      {pageError ? (
        <div className="page-inline-alert" role="alert">
          <span>{pageError}</span>
          <Button variant="quiet" size="small" onClick={() => void refresh()}>
            다시 불러오기
          </Button>
        </div>
      ) : null}

      <Card compact>
        <div className="preference-toolbar" role="search">
          <label className="form-field preference-toolbar__search">
            <span className="form-field__label">정보 검색</span>
            <input
              type="search"
              value={query}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setQuery(event.target.value)
              }
              placeholder="제목, 내용, 키워드 검색"
            />
          </label>
          <label className="form-field">
            <span className="form-field__label">정보 종류</span>
            <select
              value={typeFilter}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                setTypeFilter(event.target.value as PreferenceTypeFilter)
              }
            >
              <option value="ALL">전체 종류</option>
              {FILTERABLE_MEMORY_TYPES.map((memoryType) => (
                <option key={memoryType} value={memoryType}>
                  {MEMORY_TYPE_LABELS[memoryType]}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      {filteredPreferences.length === 0 ? (
        <EmptyState
          title={
            guardianVisiblePreferences.length === 0
              ? '아직 보호자에게 공유된 대화 정보가 없습니다'
              : '조건에 맞는 정보가 없습니다'
          }
          description={
            guardianVisiblePreferences.length === 0
              ? '공유 범위가 확인된 정보가 생기면 여기에 표시됩니다.'
              : '검색어 또는 필터를 바꾸어 확인해 주세요.'
          }
          action={
            guardianVisiblePreferences.length === 0 ? undefined : (
              <Button
                variant="secondary"
                onClick={() => {
                  setQuery('')
                  setTypeFilter('ALL')
                }}
              >
                필터 초기화
              </Button>
            )
          }
          symbol="대화"
        />
      ) : (
        <ul className="preference-grid" aria-label="대화 정보 목록">
          {filteredPreferences.map((preference) => (
            <li key={preference.id}>
              <Card as="article" className="preference-card" heading={preference.title}>
                <div className="preference-card__badges">
                  <Badge tone="info">
                    {MEMORY_TYPE_LABELS[preference.memoryType]}
                  </Badge>
                  <Badge>{SOURCE_LABELS[preference.source]}</Badge>
                  <Badge
                    tone={
                      preference.verificationStatus === 'UNVERIFIED' ||
                      preference.verificationStatus === 'AUTO_ACCEPTED'
                        ? 'warning'
                        : 'success'
                    }
                  >
                    {VERIFICATION_LABELS[preference.verificationStatus]}
                  </Badge>
                </div>

                <p className="preference-card__content">{preference.content}</p>

                {preference.keywords.length > 0 ? (
                  <ul className="tag-list" aria-label="관련 키워드">
                    {preference.keywords.map((keyword) => (
                      <li key={keyword}>#{keyword}</li>
                    ))}
                  </ul>
                ) : null}

                <dl className="preference-meta">
                  <div>
                    <dt>공유 범위</dt>
                    <dd>{VISIBILITY_LABELS[preference.visibility]}</dd>
                  </div>
                  <div>
                    <dt>마지막 확인</dt>
                    <dd>
                      {preference.lastConfirmedAt
                        ? formatDateTime(preference.lastConfirmedAt)
                        : '확인 대기'}
                    </dd>
                  </div>
                </dl>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
