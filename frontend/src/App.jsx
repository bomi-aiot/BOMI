const cards = [
  ['보호 대상자', '안정', '귀가 시나리오 대기 중'],
  ['BOMI 로봇', '온라인', '충전 스테이션 대기'],
  ['현관 센서', '정상', '마지막 이벤트 없음'],
]

export default function App() {
  return (
    <main>
      <header>
        <div className="brand">BOMI</div>
        <span>AIoT 개인 종합 돌봄 로봇</span>
      </header>
      <section className="hero">
        <p className="eyebrow">PROTECTOR DASHBOARD</p>
        <h1>오늘도 곁에서,<br />안전하게 돌봅니다.</h1>
        <p>현재는 팀 개발을 위한 초기 대시보드입니다. 실시간 데이터 연동은 다음 단계에서 구현합니다.</p>
      </section>
      <section className="grid" aria-label="시스템 상태">
        {cards.map(([name, status, detail]) => (
          <article key={name}>
            <div className="status"><span />{status}</div>
            <h2>{name}</h2>
            <p>{detail}</p>
          </article>
        ))}
      </section>
    </main>
  )
}
