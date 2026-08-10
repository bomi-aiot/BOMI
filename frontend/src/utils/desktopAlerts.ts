/**
 * 위급(T1) 알림을 화면 밖으로 내보낸다 — 브라우저 알림 + 짧은 경고음.
 *
 * 왜 필요한가
 *   지금까지 위급 알림이 도착했을 때 일어나는 일은 토스트 하나가 20초 떠 있다가
 *   사라지는 것이 전부였다. 보호자가 그 20초 동안 이 탭을 보고 있지 않았다면
 *   알린 적이 없는 것과 같다. 다른 탭에서 일하고 있거나, 자리를 비웠거나, 화면을
 *   잠가 뒀다면 — 즉 대부분의 시간에 — 아무것도 전달되지 않는다.
 *
 * 무엇을 하지 않는가
 *   서버 푸시(Web Push)가 아니다. 탭이 살아 있어야 동작한다. 탭을 닫으면 아무것도
 *   오지 않고, 브라우저가 백그라운드 탭의 타이머를 조이면(크롬은 5분 뒤부터
 *   분 단위로 느려진다) 그만큼 늦게 온다. 진짜 푸시는 서비스워커와 서버 키가
 *   필요하고 그건 별도 작업이다. 여기서 고치는 것은 "탭은 열려 있는데 보고 있지
 *   않은" 경우이며, 그것이 지금 가장 흔한 실패다.
 *
 * 권한은 왜 자동으로 요청하지 않는가
 *   화면에 들어오자마자 뜨는 권한 창은 대부분 반사적으로 거절당하고, 한 번 거절되면
 *   브라우저 설정을 직접 열기 전에는 되돌릴 수 없다. 위급 알림을 영구히 못 받는
 *   상태를 우리 손으로 만드는 셈이다. 그래서 보호자가 버튼을 눌렀을 때만 요청한다
 *   (사파리는 사용자 제스처 없는 요청을 아예 거절하기도 한다).
 */

export type DesktopAlertPermission =
  | 'unsupported'
  | 'default'
  | 'granted'
  | 'denied'

/**
 * 경고음용 오디오 컨텍스트.
 *
 * 사용자 제스처 안에서 만들어야 브라우저의 자동재생 정책을 통과한다. 그래서 권한을
 * 요청하는 그 클릭에서 함께 만들어 둔다 — 정작 위급이 왔을 때는 제스처가 없다.
 */
let audioContext: AudioContext | null = null

const notificationApi = (): typeof Notification | null =>
  typeof window !== 'undefined' && 'Notification' in window
    ? window.Notification
    : null

export function desktopAlertPermission(): DesktopAlertPermission {
  const api = notificationApi()
  if (!api) return 'unsupported'
  return api.permission as DesktopAlertPermission
}

/** 사용자 제스처(클릭) 안에서만 호출한다. */
export async function enableDesktopAlerts(): Promise<DesktopAlertPermission> {
  const api = notificationApi()
  if (!api) return 'unsupported'

  unlockAudio()

  if (api.permission !== 'default') {
    return api.permission as DesktopAlertPermission
  }

  try {
    return (await api.requestPermission()) as DesktopAlertPermission
  } catch {
    // 사파리의 구형 콜백 방식 등 — 권한 상태는 그대로 두고 현재 값을 돌려준다.
    return api.permission as DesktopAlertPermission
  }
}

function unlockAudio(): void {
  const AudioContextCtor =
    typeof window !== 'undefined'
      ? (window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext)
      : undefined
  if (!AudioContextCtor) return

  try {
    audioContext ??= new AudioContextCtor()
    void audioContext.resume()
  } catch {
    // 소리는 부가 신호다. 실패해도 알림 자체는 그대로 나가야 한다.
    audioContext = null
  }
}

/**
 * 짧은 두 번의 경고음.
 *
 * 음원 파일을 쓰지 않는 이유 — 운영 Nginx 의 CSP 가 외부 리소스를 막고, 번들에 넣으면
 * 용량만 늘어난다. 필요한 것은 "소리가 났다"는 사실뿐이라 사인파 두 번으로 충분하다.
 */
function playAlertTone(): void {
  if (!audioContext || audioContext.state !== 'running') return

  try {
    const now = audioContext.currentTime
    for (const [index, startAt] of [now, now + 0.28].entries()) {
      const oscillator = audioContext.createOscillator()
      const gain = audioContext.createGain()
      oscillator.type = 'sine'
      oscillator.frequency.value = index === 0 ? 880 : 1046
      // 뚝 끊기면 '틱' 하는 잡음이 난다. 짧게 올렸다 내린다.
      gain.gain.setValueAtTime(0.0001, startAt)
      gain.gain.exponentialRampToValueAtTime(0.22, startAt + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.22)
      oscillator.connect(gain)
      gain.connect(audioContext.destination)
      oscillator.start(startAt)
      oscillator.stop(startAt + 0.24)
    }
  } catch {
    // 소리는 부가 신호다.
  }
}

/**
 * 위급 알림 하나를 브라우저 알림으로 내보낸다.
 *
 * 건별로 하나씩 부른다 — 백엔드가 T1 을 사유별로 묶지 않는 것과 같은 이유다.
 * 응급은 사유가 같아도 건마다 별개의 사건이라, 뒤에 온 것이 앞의 것을 덮으면 안 된다.
 */
export function fireDesktopAlert(alertId: string, message: string): void {
  const api = notificationApi()
  if (!api || api.permission !== 'granted') return

  playAlertTone()

  try {
    const notification = new api('보미 · 위급 상황', {
      body: message,
      // 같은 알림이 폴링마다 다시 뜨지 않도록 건별로 고정한다.
      tag: `bomi-safety-${alertId}`,
      // 위급은 몇 초 뒤 사라지면 안 된다 — 자리를 비운 사이 지나가면 알린 적이
      // 없는 것과 같다. 화면 안 토스트를 20초로 둔 것과 같은 판단이다.
      requireInteraction: true,
    })
    notification.onclick = () => {
      window.focus()
      notification.close()
    }
  } catch {
    // 알림 생성 실패가 폴링 루프를 죽이면 안 된다. 화면 안 토스트와 안전 알림
    // 카드가 여전히 같은 내용을 들고 있다.
  }
}

/** 설정이 실제로 동작하는지 보호자가 직접 확인할 수 있게 한다(리허설용). */
export function fireTestDesktopAlert(): void {
  fireDesktopAlert('test', '테스트 알림입니다. 실제 위급 상황이 아닙니다.')
}
