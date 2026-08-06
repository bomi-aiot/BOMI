import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('BOMI 화면을 표시하는 중 오류가 발생했습니다.', error, info)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <main className="fatal-error" aria-labelledby="fatal-error-title">
        <span className="fatal-error__mark" aria-hidden="true">B</span>
        <p>화면 오류</p>
        <h1 id="fatal-error-title">보호자 화면을 표시하지 못했어요.</h1>
        <span>입력한 내용이 있다면 다시 불러오기 전에 별도로 기록해 주세요.</span>
        <button type="button" onClick={() => window.location.reload()}>
          화면 다시 불러오기
        </button>
      </main>
    )
  }
}
