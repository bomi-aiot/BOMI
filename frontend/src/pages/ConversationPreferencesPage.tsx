import {
  useMemo,
  useState,
  type ChangeEvent,
  type FormEvent,
} from 'react'
import {
  Badge,
  Button,
  Card,
  ConfirmModal,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  PageHeader,
  Toast,
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
type UsageFilter = 'ALL' | 'ENABLED' | 'PAUSED'
type ToastTone = 'success' | 'danger' | 'info'

interface PreferenceDraft {
  title: string
  content: string
  memoryType: MemoryType
  keywords: string
  visibility: MemoryVisibility
}

interface LocalToast {
  open: boolean
  message: string
  tone: ToastTone
  actionLabel?: string
  onAction?: () => void
}

const EMPTY_DRAFT: PreferenceDraft = {
  title: '',
  content: '',
  memoryType: 'PREFERENCE',
  keywords: '',
  visibility: 'SHARED_WITH_PRIMARY',
}

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

const EDITABLE_MEMORY_TYPES: readonly MemoryType[] = [
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
  SYSTEM: '시스템',
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

const messageFromError = (error: unknown): string =>
  error instanceof Error
    ? error.message
    : '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'

const splitKeywords = (value: string): string[] =>
  Array.from(
    new Set(
      value
        .split(',')
        .map((keyword) => keyword.trim())
        .filter(Boolean),
    ),
  )

const draftFromPreference = (
  preference: ConversationPreference,
): PreferenceDraft => ({
  title: preference.title,
  content: preference.content,
  memoryType: preference.memoryType,
  keywords: preference.keywords.join(', '),
  visibility: preference.visibility,
})

export function ConversationPreferencesPage() {
  const {
    elderProfile,
    conversationPreferences,
    isLoading,
    error,
    pendingActionId,
    refresh,
    addConversationPreference,
    updateConversationPreference,
    deleteConversationPreference,
    toggleConversationPreference,
  } = useBomi()

  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] =
    useState<PreferenceTypeFilter>('ALL')
  const [usageFilter, setUsageFilter] = useState<UsageFilter>('ALL')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingPreference, setEditingPreference] =
    useState<ConversationPreference | null>(null)
  const [draft, setDraft] = useState<PreferenceDraft>(EMPTY_DRAFT)
  const [formError, setFormError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] =
    useState<ConversationPreference | null>(null)
  const [localToast, setLocalToast] = useState<LocalToast>({
    open: false,
    message: '',
    tone: 'success',
  })

  const filteredPreferences = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('ko-KR')

    return conversationPreferences.filter((preference) => {
      const matchesQuery =
        normalizedQuery.length === 0 ||
        [
          preference.title,
          preference.content,
          ...preference.keywords,
        ].some((value) =>
          value.toLocaleLowerCase('ko-KR').includes(normalizedQuery),
        )
      const matchesType =
        typeFilter === 'ALL' || preference.memoryType === typeFilter
      const matchesUsage =
        usageFilter === 'ALL' ||
        (usageFilter === 'ENABLED' && preference.isEnabled) ||
        (usageFilter === 'PAUSED' && !preference.isEnabled)

      return matchesQuery && matchesType && matchesUsage
    })
  }, [conversationPreferences, query, typeFilter, usageFilter])

  const actionId = editingPreference
    ? `preference-${editingPreference.id}`
    : 'preference-new'
  const isSubmitting = pendingActionId === actionId

  const openCreateEditor = (): void => {
    setEditingPreference(null)
    setDraft(EMPTY_DRAFT)
    setFormError(null)
    setEditorOpen(true)
  }

  const openEditEditor = (preference: ConversationPreference): void => {
    setEditingPreference(preference)
    setDraft(draftFromPreference(preference))
    setFormError(null)
    setEditorOpen(true)
  }

  const closeEditor = (): void => {
    if (isSubmitting) return
    setEditorOpen(false)
    setEditingPreference(null)
    setFormError(null)
  }

  const updateDraft = (
    field: keyof PreferenceDraft,
    value: PreferenceDraft[keyof PreferenceDraft],
  ): void => {
    setDraft((current) => ({ ...current, [field]: value }))
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const title = draft.title.trim()
    const content = draft.content.trim()

    if (!title || !content) {
      setFormError('제목과 대화에 활용할 내용을 모두 입력해 주세요.')
      return
    }

    const keywords = splitKeywords(draft.keywords)
    setFormError(null)

    try {
      if (editingPreference) {
        await updateConversationPreference(editingPreference.id, {
          title,
          content,
          memoryType: draft.memoryType,
          keywords,
          visibility: draft.visibility,
          verificationStatus: 'GUARDIAN_CONFIRMED',
        })
        setLocalToast({
          open: true,
          message: '맞춤 대화 정보가 수정되었습니다.',
          tone: 'success',
        })
      } else {
        const elderId = elderProfile?.elder.id
        if (!elderId) {
          setFormError('먼저 돌봄 대상 어르신을 등록해 주세요.')
          return
        }

        await addConversationPreference({
          elderId,
          title,
          content,
          memoryType: draft.memoryType,
          keywords,
          visibility: draft.visibility,
          source: 'GUARDIAN',
        })
        setLocalToast({
          open: true,
          message: '새 맞춤 대화 정보가 추가되었습니다.',
          tone: 'success',
        })
      }

      closeEditor()
    } catch (requestError: unknown) {
      setFormError(messageFromError(requestError))
    }
  }

  const handleToggle = async (
    preference: ConversationPreference,
  ): Promise<void> => {
    try {
      const updated = await toggleConversationPreference(preference.id)
      const statusMessage = updated.isEnabled
        ? '대화 활용을 다시 시작했습니다.'
        : '대화 활용을 잠시 멈췄습니다.'

      setLocalToast({
        open: true,
        message: statusMessage,
        tone: 'info',
        actionLabel: '되돌리기',
        onAction: () => {
          void toggleConversationPreference(preference.id)
        },
      })
    } catch (requestError: unknown) {
      setLocalToast({
        open: true,
        message: messageFromError(requestError),
        tone: 'danger',
      })
    }
  }

  const handleDelete = async (): Promise<void> => {
    if (!deleteTarget) return

    try {
      await deleteConversationPreference(deleteTarget.id)
      setDeleteTarget(null)
      setLocalToast({
        open: true,
        message: '맞춤 대화 정보가 삭제되었습니다.',
        tone: 'success',
      })
    } catch (requestError: unknown) {
      setLocalToast({
        open: true,
        message: messageFromError(requestError),
        tone: 'danger',
      })
    }
  }

  if (isLoading && conversationPreferences.length === 0) {
    return (
      <LoadingState
        label="맞춤 대화 정보를 불러오는 중입니다"
        rows={5}
      />
    )
  }

  if (error && conversationPreferences.length === 0) {
    return (
      <ErrorState
        title="맞춤 대화 정보를 불러오지 못했습니다"
        description={error}
        onRetry={() => void refresh()}
      />
    )
  }

  return (
    <div className="page-stack conversation-preferences-page">
      <PageHeader
        eyebrow="개인화 기억"
        title="맞춤 대화 정보"
        description="로봇이 어르신과 자연스럽게 대화할 때 참고할 관심사, 습관, 사람과 선호를 관리합니다."
        metadata={
          <span>
            사용 중 {conversationPreferences.filter((item) => item.isEnabled).length}
            건 · 전체 {conversationPreferences.length}건
          </span>
        }
        actions={<Button onClick={openCreateEditor}>정보 추가</Button>}
      />

      {error ? (
        <div className="page-inline-alert" role="alert">
          <span>{error}</span>
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
              {EDITABLE_MEMORY_TYPES.map((memoryType) => (
                <option key={memoryType} value={memoryType}>
                  {MEMORY_TYPE_LABELS[memoryType]}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            <span className="form-field__label">대화 활용 상태</span>
            <select
              value={usageFilter}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                setUsageFilter(event.target.value as UsageFilter)
              }
            >
              <option value="ALL">전체 상태</option>
              <option value="ENABLED">사용 중</option>
              <option value="PAUSED">일시 중지</option>
            </select>
          </label>
        </div>
      </Card>

      {filteredPreferences.length === 0 ? (
        <EmptyState
          title={
            conversationPreferences.length === 0
              ? '등록된 맞춤 대화 정보가 없습니다'
              : '조건에 맞는 정보가 없습니다'
          }
          description={
            conversationPreferences.length === 0
              ? '어르신이 좋아하는 것부터 하나씩 등록해 보세요.'
              : '검색어 또는 필터를 바꾸어 확인해 주세요.'
          }
          action={
            conversationPreferences.length === 0 ? (
              <Button onClick={openCreateEditor}>첫 정보 추가</Button>
            ) : (
              <Button
                variant="secondary"
                onClick={() => {
                  setQuery('')
                  setTypeFilter('ALL')
                  setUsageFilter('ALL')
                }}
              >
                필터 초기화
              </Button>
            )
          }
          symbol="대화"
        />
      ) : (
        <ul className="preference-grid" aria-label="맞춤 대화 정보 목록">
          {filteredPreferences.map((preference) => {
            const isPending =
              pendingActionId === `preference-${preference.id}`

            return (
              <li key={preference.id}>
                <Card
                  as="article"
                  className={`preference-card${
                    preference.isEnabled
                      ? ''
                      : ' preference-card--paused'
                  }`}
                  heading={preference.title}
                  actions={
                    <Badge
                      tone={preference.isEnabled ? 'success' : 'neutral'}
                      dot
                    >
                      {preference.isEnabled ? '대화에 사용 중' : '일시 중지'}
                    </Badge>
                  }
                >
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

                  <p className="preference-card__content">
                    {preference.content}
                  </p>

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

                  <div className="preference-card__actions">
                    <Button
                      variant="secondary"
                      size="small"
                      onClick={() => openEditEditor(preference)}
                      disabled={isPending}
                    >
                      수정
                    </Button>
                    <Button
                      variant="quiet"
                      size="small"
                      onClick={() => void handleToggle(preference)}
                      isLoading={isPending}
                    >
                      {preference.isEnabled ? '사용 중지' : '다시 사용'}
                    </Button>
                    <Button
                      variant="ghost"
                      size="small"
                      onClick={() => setDeleteTarget(preference)}
                      disabled={isPending}
                    >
                      삭제
                    </Button>
                  </div>
                </Card>
              </li>
            )
          })}
        </ul>
      )}

      <Modal
        open={editorOpen}
        title={
          editingPreference
            ? '맞춤 대화 정보 수정'
            : '맞춤 대화 정보 추가'
        }
        description="확실히 알고 있는 사실만 입력하고, 건강·복약 변경은 별도의 확인 요청에서 관리해 주세요."
        onClose={closeEditor}
        closeOnBackdrop={!isSubmitting}
        closeOnEscape={!isSubmitting}
        closeDisabled={isSubmitting}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={closeEditor}
              disabled={isSubmitting}
            >
              취소
            </Button>
            <Button
              type="submit"
              form="preference-editor-form"
              isLoading={isSubmitting}
            >
              {editingPreference ? '수정 내용 저장' : '정보 추가'}
            </Button>
          </>
        }
      >
        <form
          className="form-grid preference-editor-form"
          id="preference-editor-form"
          onSubmit={(event) => void handleSubmit(event)}
        >
          <label className="form-field">
            <span className="form-field__label">정보 종류</span>
            <select
              value={draft.memoryType}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                updateDraft('memoryType', event.target.value as MemoryType)
              }
            >
              {EDITABLE_MEMORY_TYPES.map((memoryType) => (
                <option key={memoryType} value={memoryType}>
                  {MEMORY_TYPE_LABELS[memoryType]}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            <span className="form-field__label">제목</span>
            <input
              value={draft.title}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                updateDraft('title', event.target.value)
              }
              placeholder="예: 트로트 음악을 좋아해요"
              maxLength={80}
              required
            />
          </label>
          <label className="form-field form-field--wide">
            <span className="form-field__label">대화에 활용할 내용</span>
            <textarea
              value={draft.content}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                updateDraft('content', event.target.value)
              }
              placeholder="로봇이 어떤 맥락에서 어떻게 참고하면 좋은지 적어 주세요."
              rows={5}
              maxLength={600}
              required
            />
            <span className="form-field__help">
              진단이나 약 변경처럼 의료 판단이 필요한 내용은 직접 확정하지
              않습니다.
            </span>
          </label>
          <label className="form-field form-field--wide">
            <span className="form-field__label">키워드</span>
            <input
              value={draft.keywords}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                updateDraft('keywords', event.target.value)
              }
              placeholder="쉼표로 구분: 트로트, 음악, 아침"
            />
          </label>
          <label className="form-field form-field--wide">
            <span className="form-field__label">공유 범위</span>
            <select
              value={draft.visibility}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                updateDraft(
                  'visibility',
                  event.target.value as MemoryVisibility,
                )
              }
            >
              {(
                Object.keys(VISIBILITY_LABELS) as MemoryVisibility[]
              ).map((visibility) => (
                <option key={visibility} value={visibility}>
                  {VISIBILITY_LABELS[visibility]}
                </option>
              ))}
            </select>
          </label>
          {formError ? (
            <p className="form-error form-field--wide" role="alert">
              {formError}
            </p>
          ) : null}
        </form>
      </Modal>

      <ConfirmModal
        open={deleteTarget !== null}
        title="이 정보를 삭제할까요?"
        description={
          deleteTarget
            ? `“${deleteTarget.title}” 정보가 이후 대화에 사용되지 않습니다.`
            : ''
        }
        confirmLabel="삭제"
        tone="danger"
        isLoading={
          deleteTarget !== null &&
          pendingActionId === `preference-${deleteTarget.id}`
        }
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => void handleDelete()}
      />

      <Toast
        open={localToast.open}
        message={localToast.message}
        tone={localToast.tone}
        actionLabel={localToast.actionLabel}
        onAction={localToast.onAction}
        onDismiss={() =>
          setLocalToast((current) => ({ ...current, open: false }))
        }
      />
    </div>
  )
}
