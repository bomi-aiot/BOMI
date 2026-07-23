import { useEffect, useMemo, useState, type ChangeEvent } from 'react'
import {
  Badge,
  Button,
  Card,
  ErrorState,
  LoadingState,
  PageHeader,
  Toast,
} from '../components'
import { useBomi } from '../state/BomiContext'
import type {
  ConversationSettings,
  ElderProfile,
  Gender,
  HealthProfile,
} from '../types/domain'

const genderLabels: Record<Gender, string> = {
  FEMALE: '여성',
  MALE: '남성',
  OTHER: '기타',
  UNKNOWN: '응답하지 않음',
}

const responseLengthLabels: Record<ConversationSettings['responseLength'], string> = {
  SHORT: '짧고 간단하게',
  MEDIUM: '보통 길이로',
  LONG: '충분히 자세하게',
}

const speechRateLabels: Record<ConversationSettings['speechRate'], string> = {
  SLOW: '천천히',
  NORMAL: '보통',
  FAST: '빠르게',
}

const cloneProfile = (profile: ElderProfile): ElderProfile =>
  structuredClone(profile)

const splitCommaValues = (value: string): string[] =>
  value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)

export function ElderProfilePage() {
  const { elderProfile, isLoading, error, refresh, saveElderProfile } = useBomi()
  const [draft, setDraft] = useState<ElderProfile | null>(null)
  const [isDirty, setIsDirty] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [toast, setToast] = useState<{ open: boolean; message: string; tone: 'success' | 'danger' }>({
    open: false,
    message: '',
    tone: 'success',
  })

  useEffect(() => {
    if (elderProfile && !isDirty) {
      setDraft(cloneProfile(elderProfile))
    }
  }, [elderProfile, isDirty])

  useEffect(() => {
    if (!isDirty) return undefined

    const preventClose = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    const confirmInternalNavigation = (event: Event) => {
      const shouldLeave = window.confirm(
        '저장하지 않은 변경사항이 있습니다. 저장하지 않고 이동할까요?',
      )
      if (!shouldLeave) {
        event.preventDefault()
      }
    }

    window.addEventListener('beforeunload', preventClose)
    window.addEventListener('bomi:before-navigate', confirmInternalNavigation)
    return () => {
      window.removeEventListener('beforeunload', preventClose)
      window.removeEventListener('bomi:before-navigate', confirmInternalNavigation)
    }
  }, [isDirty])

  const updateDraft = (updater: (current: ElderProfile) => ElderProfile) => {
    setDraft((current) => (current ? updater(current) : current))
    setIsDirty(true)
  }

  const updateHealth = (updater: (health: HealthProfile) => HealthProfile) => {
    updateDraft((current) => ({
      ...current,
      healthProfile: updater(current.healthProfile),
    }))
  }

  const age = useMemo(() => {
    if (!draft?.elder.birthDate) return null
    const birth = new Date(draft.elder.birthDate)
    const now = new Date()
    let result = now.getFullYear() - birth.getFullYear()
    if (
      now.getMonth() < birth.getMonth() ||
      (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate())
    ) {
      result -= 1
    }
    return result
  }, [draft?.elder.birthDate])

  const handleSave = async () => {
    if (!draft) return
    if (!draft.elder.name.trim() || !draft.elder.preferredName.trim() || !draft.elder.birthDate) {
      setToast({
        open: true,
        message: '성명, 부르는 이름, 생년월일을 확인해 주세요.',
        tone: 'danger',
      })
      return
    }

    setIsSaving(true)
    try {
      await saveElderProfile(draft)
      setIsDirty(false)
      setToast({ open: true, message: '어르신 정보를 안전하게 저장했습니다.', tone: 'success' })
    } catch {
      setToast({
        open: true,
        message: '저장하지 못했습니다. 잠시 후 다시 시도해 주세요.',
        tone: 'danger',
      })
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancel = () => {
    if (elderProfile) {
      setDraft(cloneProfile(elderProfile))
      setIsDirty(false)
      setToast({ open: true, message: '수정 내용을 취소했습니다.', tone: 'success' })
    }
  }

  if (isLoading && !draft) {
    return <LoadingState label="어르신 정보를 불러오는 중입니다" rows={6} />
  }

  if (!draft) {
    return (
      <ErrorState
        title="어르신 정보를 불러오지 못했습니다"
        description={error ?? '등록된 어르신이 없습니다.'}
        onRetry={() => void refresh()}
      />
    )
  }

  const surveyPercent =
    draft.surveyStatus.totalQuestionCount > 0
      ? Math.round(
          (draft.surveyStatus.completedQuestionCount / draft.surveyStatus.totalQuestionCount) * 100,
        )
      : 0

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="초기 설정 · 보호자 확인"
        title="어르신 프로필"
        description="보미가 자연스럽고 안전하게 대화할 수 있도록 꼭 필요한 정보만 관리합니다."
        metadata={
          <span className="profile-completeness">
            <strong>{surveyPercent}%</strong> 초기 질문 완료
          </span>
        }
        actions={
          <>
            <Button variant="secondary" onClick={handleCancel} disabled={!isDirty || isSaving}>
              변경 취소
            </Button>
            <Button onClick={() => void handleSave()} isLoading={isSaving} disabled={!isDirty}>
              저장하기
            </Button>
          </>
        }
      />

      {isDirty ? (
        <div className="unsaved-notice" role="status">
          <span aria-hidden="true">●</span>
          저장하지 않은 변경사항이 있습니다. 다른 페이지로 이동하기 전에 저장해 주세요.
        </div>
      ) : null}

      <Card
        className="survey-status-card"
        heading="로봇 대화형 초기 질문"
        description="어르신이 보미와 대화하며 답한 내용은 보호자가 이곳에서 확인하고 보완할 수 있습니다."
        actions={
          <Badge tone={draft.surveyStatus.status === 'COMPLETED' ? 'success' : 'warning'} dot>
            {draft.surveyStatus.status === 'COMPLETED' ? '질문 완료' : '진행 중'}
          </Badge>
        }
      >
        <div className="survey-progress">
          <div>
            <strong>
              {draft.surveyStatus.completedQuestionCount}/{draft.surveyStatus.totalQuestionCount}
            </strong>
            <span>문항 응답</span>
          </div>
          <div
            className="progress-track"
            role="progressbar"
            aria-label="초기 질문 완료율"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={surveyPercent}
          >
            <span style={{ width: `${surveyPercent}%` }} />
          </div>
          <p>
            입력 출처: {draft.surveyStatus.source === 'ROBOT' ? '보미 음성 설문' : '보호자 웹'}
          </p>
        </div>
      </Card>

      <div className="form-section-grid">
        <Card heading="1. 기본 정보" description="보미가 어르신을 정확하고 친근하게 부르는 데 사용합니다.">
          <div className="form-grid">
            <label className="field">
              <span>성명 <em>필수</em></span>
              <input
                value={draft.elder.name}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    elder: { ...current.elder, name: event.target.value },
                  }))
                }
                required
              />
            </label>
            <label className="field">
              <span>보미가 부를 이름 <em>필수</em></span>
              <input
                value={draft.elder.preferredName}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    elder: { ...current.elder, preferredName: event.target.value },
                  }))
                }
                required
              />
              <small>예: 봄순 어르신, 어머니</small>
            </label>
            <label className="field">
              <span>생년월일 <em>필수</em></span>
              <input
                type="date"
                value={draft.elder.birthDate}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    elder: { ...current.elder, birthDate: event.target.value },
                  }))
                }
                required
              />
              {age !== null ? <small>만 {age}세</small> : null}
            </label>
            <label className="field">
              <span>성별</span>
              <select
                value={draft.elder.gender}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    elder: { ...current.elder, gender: event.target.value as Gender },
                  }))
                }
              >
                {Object.entries(genderLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field field--wide">
              <span>거주지 주소</span>
              <input
                value={draft.elder.address ?? ''}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    elder: { ...current.elder, address: event.target.value },
                  }))
                }
                placeholder="시·군·구와 도로명 주소"
              />
              <small>지역 날씨 안내와 응급 시 위치 확인에 활용될 수 있습니다.</small>
            </label>
          </div>
        </Card>

        <Card
          heading="2. 건강 참고 정보"
          description="진단을 위한 정보가 아니며, 안전한 대화와 보호자 알림을 위한 참고 정보입니다."
        >
          <div className="medical-notice">
            <strong>의료 정보 안내</strong>
            <p>보미는 진단하거나 처방을 변경하지 않습니다. 복약 변경은 의료진과 확인해 주세요.</p>
          </div>
          <div className="form-grid">
            <label className="field field--wide">
              <span>현재 질환</span>
              <input
                value={draft.healthProfile.conditions.map((item) => item.name).join(', ')}
                onChange={(event) => {
                  const names = splitCommaValues(event.target.value)
                  updateHealth((health) => ({
                    ...health,
                    conditions: names.map((name, index) => ({
                      id: health.conditions[index]?.id ?? `condition-draft-${index}`,
                      recordType: 'HEALTH_CONDITION',
                      name,
                      diagnosedAt: health.conditions[index]?.diagnosedAt,
                      note: health.conditions[index]?.note,
                      sourceType: health.conditions[index]?.sourceType ?? 'GUARDIAN',
                      verificationStatus:
                        health.conditions[index]?.verificationStatus ?? 'GUARDIAN_CONFIRMED',
                      recordedAt: health.conditions[index]?.recordedAt ?? new Date().toISOString(),
                    })),
                  }))
                }}
                placeholder="예: 고혈압, 관절염"
              />
              <small>여러 항목은 쉼표로 구분해 주세요.</small>
            </label>
            <label className="field field--wide">
              <span>알레르기</span>
              <input
                value={draft.healthProfile.allergies.map((item) => item.allergen).join(', ')}
                onChange={(event) => {
                  const allergens = splitCommaValues(event.target.value)
                  updateHealth((health) => ({
                    ...health,
                    allergies: allergens.map((allergen, index) => ({
                      id: health.allergies[index]?.id ?? `allergy-draft-${index}`,
                      recordType: 'ALLERGY',
                      allergen,
                      reaction: health.allergies[index]?.reaction,
                      severity: health.allergies[index]?.severity ?? 'UNKNOWN',
                      sourceType: health.allergies[index]?.sourceType ?? 'GUARDIAN',
                      verificationStatus:
                        health.allergies[index]?.verificationStatus ?? 'GUARDIAN_CONFIRMED',
                      recordedAt: health.allergies[index]?.recordedAt ?? new Date().toISOString(),
                    })),
                  }))
                }}
                placeholder="예: 땅콩, 페니실린"
              />
            </label>
            <label className="field field--wide">
              <span>대표 신체적 불편함</span>
              <textarea
                rows={3}
                value={draft.healthProfile.physicalLimitations[0]?.description ?? ''}
                onChange={(event) =>
                  updateHealth((health) => {
                    const first = health.physicalLimitations[0]
                    const remaining = health.physicalLimitations.slice(1)
                    return {
                      ...health,
                      physicalLimitations: event.target.value.trim()
                        ? [
                            {
                              id: first?.id ?? 'limitation-draft-0',
                              recordType: 'PHYSICAL_LIMITATION',
                              bodyArea: first?.bodyArea ?? '기타',
                              description: event.target.value,
                              severity: first?.severity ?? 'MILD',
                              firstObservedAt: first?.firstObservedAt,
                              lastObservedAt: new Date().toISOString(),
                              sourceType: first?.sourceType ?? 'GUARDIAN',
                              verificationStatus:
                                first?.verificationStatus ?? 'GUARDIAN_CONFIRMED',
                            },
                            ...remaining,
                          ]
                        : remaining,
                    }
                  })
                }
                placeholder="예: 오래 걸으면 허리가 아프다고 말씀하세요."
              />
              {draft.healthProfile.physicalLimitations.length > 1 ? (
                <small>
                  다른 불편함 {draft.healthProfile.physicalLimitations.length - 1}건은 건강 관리
                  화면에 유지됩니다.
                </small>
              ) : null}
            </label>
            <label className="field">
              <span>최근 병원 방문일</span>
              <input
                type="date"
                value={draft.healthProfile.recentHospitalVisitAt?.slice(0, 10) ?? ''}
                onChange={(event) =>
                  updateHealth((health) => ({
                    ...health,
                    recentHospitalVisitAt: event.target.value,
                  }))
                }
              />
            </label>
            <label className="field">
              <span>주 이용 병원</span>
              <input
                value={draft.healthProfile.primaryHospital ?? ''}
                onChange={(event) =>
                  updateHealth((health) => ({
                    ...health,
                    primaryHospital: event.target.value,
                  }))
                }
                placeholder="예: 한마음 정형외과"
              />
            </label>
          </div>
        </Card>

        <Card heading="3. 관심사와 일상" description="다음 대화에서 자연스럽게 활용할 취미와 생활 습관입니다.">
          <div className="preference-editor-list">
            {draft.personalPreferences.map((preference, index) => (
              <div className="preference-editor" key={preference.id}>
                <Badge tone={preference.memoryType === 'HOBBY' ? 'info' : 'neutral'}>
                  {preference.memoryType === 'HOBBY'
                    ? '취미'
                    : preference.memoryType === 'DAILY_ROUTINE'
                      ? '일상'
                      : '선호'}
                </Badge>
                <label className="field">
                  <span>항목</span>
                  <input
                    value={preference.title}
                    onChange={(event) =>
                      updateDraft((current) => ({
                        ...current,
                        personalPreferences: current.personalPreferences.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, title: event.target.value } : item,
                        ),
                      }))
                    }
                  />
                </label>
                <label className="field field--grow">
                  <span>상세 내용</span>
                  <input
                    value={preference.detail}
                    onChange={(event) =>
                      updateDraft((current) => ({
                        ...current,
                        personalPreferences: current.personalPreferences.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, detail: event.target.value } : item,
                        ),
                      }))
                    }
                  />
                </label>
              </div>
            ))}
          </div>
        </Card>

        <Card heading="4. 중요한 사람" description="가족과 지인을 올바른 호칭으로 기억하고 안부를 이어갑니다.">
          <div className="person-grid">
            {draft.importantPeople.map((person, index) => (
              <fieldset className="person-editor" key={person.id}>
                <legend>{person.relationship}</legend>
                <label className="field">
                  <span>이름</span>
                  <input
                    value={person.name}
                    onChange={(event) =>
                      updateDraft((current) => ({
                        ...current,
                        importantPeople: current.importantPeople.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, name: event.target.value } : item,
                        ),
                      }))
                    }
                  />
                </label>
                <label className="field">
                  <span>관계</span>
                  <input
                    value={person.relationship}
                    onChange={(event) =>
                      updateDraft((current) => ({
                        ...current,
                        importantPeople: current.importantPeople.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, relationship: event.target.value } : item,
                        ),
                      }))
                    }
                  />
                </label>
                <label className="field field--wide">
                  <span>보미가 사용할 호칭</span>
                  <input
                    value={person.preferredReference}
                    onChange={(event) =>
                      updateDraft((current) => ({
                        ...current,
                        importantPeople: current.importantPeople.map((item, itemIndex) =>
                          itemIndex === index
                            ? { ...item, preferredReference: event.target.value }
                            : item,
                        ),
                      }))
                    }
                  />
                </label>
              </fieldset>
            ))}
          </div>
        </Card>

        <Card heading="5. 대화 방식" description="어르신이 가장 편안하게 느끼는 말하기 속도와 답변 방식을 설정합니다.">
          <div className="form-grid">
            <label className="field">
              <span>답변 길이</span>
              <select
                value={draft.conversationSettings.responseLength}
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  updateDraft((current) => ({
                    ...current,
                    conversationSettings: {
                      ...current.conversationSettings,
                      responseLength: event.target
                        .value as ConversationSettings['responseLength'],
                    },
                  }))
                }
              >
                {Object.entries(responseLengthLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>말하기 속도</span>
              <select
                value={draft.conversationSettings.speechRate}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    conversationSettings: {
                      ...current.conversationSettings,
                      speechRate: event.target.value as ConversationSettings['speechRate'],
                    },
                  }))
                }
              >
                {Object.entries(speechRateLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>말소리 크기</span>
              <select
                value={draft.conversationSettings.speechVolume}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    conversationSettings: {
                      ...current.conversationSettings,
                      speechVolume: event.target.value as ConversationSettings['speechVolume'],
                    },
                  }))
                }
              >
                <option value="QUIET">조용하게</option>
                <option value="NORMAL">보통 크기로</option>
                <option value="LOUD">크고 또렷하게</option>
              </select>
            </label>
            <label className="field">
              <span>먼저 말 걸기</span>
              <select
                value={draft.conversationSettings.proactiveSpeechLevel}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    conversationSettings: {
                      ...current.conversationSettings,
                      proactiveSpeechLevel: event.target
                        .value as ConversationSettings['proactiveSpeechLevel'],
                    },
                  }))
                }
              >
                <option value="LOW">꼭 필요할 때만</option>
                <option value="MEDIUM">가끔 자연스럽게</option>
                <option value="HIGH">자주 다정하게</option>
              </select>
            </label>
            <label className="field">
              <span>기본 알림 예고 시간</span>
              <select
                value={draft.conversationSettings.defaultReminderLeadMinutes}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    conversationSettings: {
                      ...current.conversationSettings,
                      defaultReminderLeadMinutes: Number(event.target.value),
                    },
                  }))
                }
              >
                <option value={10}>10분 전</option>
                <option value={30}>30분 전</option>
                <option value={60}>1시간 전</option>
                <option value={120}>2시간 전</option>
              </select>
            </label>
            <label className="field">
              <span>건강 관련 제안</span>
              <select
                value={draft.conversationSettings.healthSuggestionSensitivity}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    conversationSettings: {
                      ...current.conversationSettings,
                      healthSuggestionSensitivity: event.target
                        .value as ConversationSettings['healthSuggestionSensitivity'],
                    },
                  }))
                }
              >
                <option value="CAUTIOUS">조심스럽게 안내</option>
                <option value="BALANCED">필요할 때 안내</option>
                <option value="PROACTIVE">적극적으로 안내</option>
              </select>
            </label>
            <fieldset className="time-range-field field--wide">
              <legend>선호 대화 시간</legend>
              <label className="field">
                <span>시작</span>
                <input
                  type="time"
                  value={
                    draft.conversationSettings.preferredConversationWindows[0]?.startTime ??
                    '09:00'
                  }
                  onChange={(event) =>
                    updateDraft((current) => {
                      const windows = [...current.conversationSettings.preferredConversationWindows]
                      const first = windows[0] ?? {
                        id: 'window-primary',
                        daysOfWeek: [1, 2, 3, 4, 5, 6, 7],
                        startTime: '09:00',
                        endTime: '18:00',
                        label: '선호 대화 시간',
                      }
                      windows[0] = { ...first, startTime: event.target.value }
                      return {
                        ...current,
                        conversationSettings: {
                          ...current.conversationSettings,
                          preferredConversationWindows: windows,
                        },
                      }
                    })
                  }
                />
              </label>
              <span aria-hidden="true">부터</span>
              <label className="field">
                <span>종료</span>
                <input
                  type="time"
                  value={
                    draft.conversationSettings.preferredConversationWindows[0]?.endTime ??
                    '18:00'
                  }
                  onChange={(event) =>
                    updateDraft((current) => {
                      const windows = [...current.conversationSettings.preferredConversationWindows]
                      const first = windows[0] ?? {
                        id: 'window-primary',
                        daysOfWeek: [1, 2, 3, 4, 5, 6, 7],
                        startTime: '09:00',
                        endTime: '18:00',
                        label: '선호 대화 시간',
                      }
                      windows[0] = { ...first, endTime: event.target.value }
                      return {
                        ...current,
                        conversationSettings: {
                          ...current.conversationSettings,
                          preferredConversationWindows: windows,
                        },
                      }
                    })
                  }
                />
              </label>
              <span aria-hidden="true">까지</span>
            </fieldset>
            <label className="field field--wide">
              <span>피하고 싶은 대화 주제</span>
              <input
                value={draft.conversationSettings.avoidedTopics.join(', ')}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    conversationSettings: {
                      ...current.conversationSettings,
                      avoidedTopics: splitCommaValues(event.target.value),
                    },
                  }))
                }
                placeholder="여러 항목은 쉼표로 구분"
              />
            </label>
            <label className="switch-field field--wide">
              <input
                type="checkbox"
                checked={draft.conversationSettings.needsRepeatedExplanation}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    conversationSettings: {
                      ...current.conversationSettings,
                      needsRepeatedExplanation: event.target.checked,
                    },
                  }))
                }
              />
              <span>
                <strong>중요한 안내는 한 번 더 설명하기</strong>
                <small>복약과 일정 안내를 이해하기 쉬운 문장으로 반복합니다.</small>
              </span>
            </label>
            <label className="switch-field field--wide">
              <input
                type="checkbox"
                checked={draft.conversationSettings.reminiscenceEnabled}
                onChange={(event) =>
                  updateDraft((current) => ({
                    ...current,
                    conversationSettings: {
                      ...current.conversationSettings,
                      reminiscenceEnabled: event.target.checked,
                    },
                  }))
                }
              />
              <span>
                <strong>좋은 추억을 대화에 활용하기</strong>
                <small>보호자가 확인한 가족·과거 경험을 자연스러운 회상 대화에 활용합니다.</small>
              </span>
            </label>
          </div>
        </Card>
      </div>

      <div className="sticky-save-bar" aria-label="프로필 저장 작업">
        <div>
          <strong>{isDirty ? '변경사항을 저장해 주세요' : '모든 변경사항이 저장되었습니다'}</strong>
          <span>
            마지막 정보 갱신{' '}
            {new Date(draft.updatedAt).toLocaleString('ko-KR', {
              timeZone: 'Asia/Seoul',
            })}
          </span>
        </div>
        <div>
          <Button variant="secondary" onClick={handleCancel} disabled={!isDirty || isSaving}>
            취소
          </Button>
          <Button onClick={() => void handleSave()} isLoading={isSaving} disabled={!isDirty}>
            변경사항 저장
          </Button>
        </div>
      </div>

      <Toast
        open={toast.open}
        message={toast.message}
        tone={toast.tone}
        onDismiss={() => setToast((current) => ({ ...current, open: false }))}
      />
    </div>
  )
}
